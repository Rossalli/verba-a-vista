"""Infraestrutura comum dos coletores (spec §9 e §11; plano T2.1).

Cada fonte tem um módulo em `coleta/` com:
- `FONTE`: o nome da pasta em `dados/brutos/` (as chaves de config/fontes.yaml);
- `criar_http(config) -> Http`: cliente com os limites e as paradas da fonte;
- `coletar(data, *, config=None, http=None) -> RetratoBruto`.

Regras de `dados/brutos/` (CLAUDE.md): o retrato do dia nunca é editado nem apagado. Se ele já existe,
a coleta do dia é reaproveitada (cache, spec §11); `forcar` não sobrescreve, grava uma nova execução no log.
"""

import importlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from nucleo.config import Config, carregar_config

RAIZ = Path(__file__).resolve().parents[1]
STATUS_REPETIVEIS = frozenset({429, 500, 502, 503, 504})

# fonte -> módulo (importado só quando a fonte roda: cada uma traz dependências próprias)
FONTES = {
    "transferegov_api": "coleta.transferegov_api",
    "transferegov_discricionarias": "coleta.transferegov_discricionarias",
    "obrasgov": "coleta.obrasgov",
    "portal_transparencia": "coleta.portal_transparencia",
    "cauc": "coleta.cauc",
    "tesouro_constitucionais": "coleta.tesouro",
}


class ColetaErro(Exception):
    """A coleta de uma fonte falhou. Nenhum retrato parcial é gravado."""


class AcessoNegadoErro(ColetaErro):
    """401, 403 ou 429 onde repetir é perigoso (ex.: a chave do Portal é suspensa por 8 h)."""


@dataclass
class RetratoBruto:
    """O que a fonte devolveu para o município em `data`, sem interpretação."""

    fonte: str
    data: date
    coletado_em: datetime
    metadados: dict[str, Any] = field(default_factory=dict)
    dados: dict[str, list[dict]] = field(default_factory=dict)

    def contagens(self) -> dict[str, int]:
        return {recurso: len(registros) for recurso, registros in self.dados.items()}

    def para_dict(self) -> dict:
        return {
            "fonte": self.fonte,
            "data": self.data.isoformat(),
            "coletado_em": self.coletado_em.isoformat(timespec="seconds"),
            "metadados": self.metadados,
            "dados": self.dados,
        }


class Http:
    """GET com tentativas, backoff exponencial, intervalo mínimo e paradas por status.

    `dormir` e `relogio` são injetáveis para os testes não esperarem de verdade.
    """

    def __init__(
        self,
        *,
        tentativas: int,
        backoff_inicial_s: float,
        intervalo_minimo_s: float = 0.0,
        parar_em: frozenset[int] = frozenset(),
        max_requisicoes: int | None = None,
        cabecalhos: dict[str, str] | None = None,
        cliente: httpx.Client | None = None,
        timeout_s: float = 120.0,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.tentativas = tentativas
        self.backoff_inicial_s = backoff_inicial_s
        self.intervalo_minimo_s = intervalo_minimo_s
        self.parar_em = parar_em
        self.max_requisicoes = max_requisicoes
        self.dormir = dormir
        self.relogio = relogio
        self.cliente = cliente or httpx.Client(
            timeout=timeout_s, follow_redirects=True, headers={"User-Agent": "verba-a-vista/0.1", **(cabecalhos or {})}
        )
        if cliente is not None and cabecalhos:
            self.cliente.headers.update(cabecalhos)
        self.requisicoes = 0
        self._ultima = None

    @classmethod
    def da_config(cls, config: Config, **kw) -> "Http":
        coleta = config.regras.coleta
        return cls(tentativas=coleta.tentativas, backoff_inicial_s=coleta.backoff_inicial_s, **kw)

    def _esperar_intervalo(self) -> None:
        if self.intervalo_minimo_s and self._ultima is not None:
            falta = self.intervalo_minimo_s - (self.relogio() - self._ultima)
            if falta > 0:
                self.dormir(falta)
        self._ultima = self.relogio()

    def _contar(self) -> None:
        if self.max_requisicoes is not None and self.requisicoes >= self.max_requisicoes:
            raise ColetaErro(f"teto de {self.max_requisicoes} requisições por execução atingido")
        self._esperar_intervalo()
        self.requisicoes += 1

    def _falhou(self, tentativa: int) -> None:
        if tentativa < self.tentativas:
            self.dormir(self.backoff_inicial_s * 2 ** (tentativa - 1))

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        ultimo = ""
        for tentativa in range(1, self.tentativas + 1):
            self._contar()
            try:
                resp = self.cliente.get(url, params=params)
            except httpx.HTTPError as e:
                ultimo = f"{type(e).__name__}: {e}"[:200]
            else:
                if resp.status_code in self.parar_em:
                    raise AcessoNegadoErro(f"{url}: HTTP {resp.status_code} ({resp.text[:100]!r}); sem nova tentativa")
                if resp.is_success:
                    return resp
                if resp.status_code not in STATUS_REPETIVEIS:
                    raise ColetaErro(f"{url}: HTTP {resp.status_code} ({resp.text[:200]!r})")
                ultimo = f"HTTP {resp.status_code}"
            self._falhou(tentativa)
        raise ColetaErro(f"{url}: {self.tentativas} tentativas falharam (último erro: {ultimo})")

    def get_json(self, url: str, params: dict | None = None) -> Any:
        resp = self.get(url, params)
        try:
            return resp.json()
        except ValueError as e:
            raise ColetaErro(f"{url}: resposta não é JSON válido ({e})") from e

    def tamanho_remoto(self, url: str) -> int | None:
        """Content-Length via HEAD, ou None se o servidor não informar (não conta como falha)."""
        try:
            resp = self.cliente.head(url)
        except httpx.HTTPError:
            return None
        self.requisicoes += 1
        if resp.is_success and resp.headers.get("content-length", "").isdigit():
            return int(resp.headers["content-length"])
        return None

    def baixar(self, url: str, destino: Path) -> Path:
        """Baixa para `destino`; pula se já existe com o mesmo tamanho do servidor."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        tamanho = self.tamanho_remoto(url)
        if tamanho is not None and destino.exists() and destino.stat().st_size == tamanho:
            return destino
        parcial = destino.with_suffix(destino.suffix + ".parte")
        ultimo = ""
        for tentativa in range(1, self.tentativas + 1):
            self._contar()
            try:
                with self.cliente.stream("GET", url) as resp:
                    if not resp.is_success:
                        if resp.status_code not in STATUS_REPETIVEIS:
                            raise ColetaErro(f"{url}: HTTP {resp.status_code}")
                        ultimo = f"HTTP {resp.status_code}"
                    else:
                        with parcial.open("wb") as f:
                            for pedaco in resp.iter_bytes(1 << 20):
                                f.write(pedaco)
                        if tamanho is not None and parcial.stat().st_size != tamanho:
                            ultimo = f"tamanho {parcial.stat().st_size} diferente de {tamanho}"
                        else:
                            os.replace(parcial, destino)
                            return destino
            except httpx.HTTPError as e:
                ultimo = f"{type(e).__name__}: {e}"[:200]
            self._falhou(tentativa)
        parcial.unlink(missing_ok=True)
        raise ColetaErro(f"{url}: download falhou após {self.tentativas} tentativas (último erro: {ultimo})")


# --- gravação ----------------------------------------------------------------------------------


def pasta_fonte(raiz: Path, fonte: str) -> Path:
    return raiz / "dados" / "brutos" / fonte


def caminho_retrato(raiz: Path, fonte: str, data: date) -> Path:
    return pasta_fonte(raiz, fonte) / f"{data:%Y-%m-%d}.json"


def caminho_log(raiz: Path, fonte: str, data: date) -> Path:
    return pasta_fonte(raiz, fonte) / f"{data:%Y-%m-%d}.log.json"


def _gravar_atomico(caminho: Path, conteudo: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(conteudo, encoding="utf-8", newline="\n")
    os.replace(temporario, caminho)


def gravar_retrato(raiz: Path, retrato: RetratoBruto) -> Path:
    """Grava `dados/brutos/<fonte>/<data>.json`. Nunca sobrescreve um retrato existente."""
    caminho = caminho_retrato(raiz, retrato.fonte, retrato.data)
    if caminho.exists():
        raise FileExistsError(f"{caminho} já existe: retratos em dados/brutos/ nunca são editados")
    # chaves ordenadas e recuo fixo: o diff do Git mostra só o que mudou na fonte
    _gravar_atomico(caminho, json.dumps(retrato.para_dict(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return caminho


def registrar_log(raiz: Path, fonte: str, data: date, execucao: dict) -> Path:
    """Acrescenta uma execução a `<data>.log.json` (várias tentativas no mesmo dia ficam todas registradas)."""
    caminho = caminho_log(raiz, fonte, data)
    atual = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {"fonte": fonte, "data": data.isoformat(), "execucoes": []}
    atual["execucoes"].append(execucao)
    _gravar_atomico(caminho, json.dumps(atual, ensure_ascii=False, indent=1) + "\n")
    return caminho


def carregar_dotenv(raiz: Path = RAIZ) -> list[str]:
    """Põe as linhas `CHAVE=valor` do `.env` em os.environ (sem sobrescrever o que já existe).

    Devolve só os NOMES carregados: os valores (chaves de API) nunca são impressos nem registrados.
    """
    arquivo = raiz / ".env"
    carregadas: list[str] = []
    if not arquivo.exists():
        return carregadas
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        nome, valor = nome.strip(), valor.strip().strip('"').strip("'")
        if valor and nome not in os.environ:
            os.environ[nome] = valor
            carregadas.append(nome)
    return carregadas


# --- execução ----------------------------------------------------------------------------------


@dataclass
class Resultado:
    fonte: str
    status: str  # "ok", "reaproveitado" ou "erro"
    erro: str | None = None
    caminho: Path | None = None
    registros: dict[str, int] = field(default_factory=dict)
    requisicoes: int = 0
    duracao_s: float = 0.0


def agora(config: Config) -> datetime:
    return datetime.now(ZoneInfo(config.regras.coleta.fuso))


def executar(
    fontes: list[str] | None = None,
    data: date | None = None,
    *,
    raiz: Path = RAIZ,
    config: Config | None = None,
    forcar: bool = False,
    relogio: Callable[[Config], datetime] = agora,
    **opcoes,
) -> list[Resultado]:
    """Roda cada fonte isoladamente: a falha de uma não derruba as outras (spec §9).

    `opcoes` vão para o `coletar` de cada fonte que as aceita (ex.: `cache` do Siconv).
    """
    config = config or carregar_config()
    desconhecidas = set(fontes or []) - set(FONTES)
    if desconhecidas:
        raise ValueError(f"fontes desconhecidas: {sorted(desconhecidas)}; válidas: {sorted(FONTES)}")
    resultados = []
    for fonte in fontes or list(FONTES):
        inicio = relogio(config)
        dia = data or inicio.date()
        caminho = caminho_retrato(raiz, fonte, dia)
        if caminho.exists() and not forcar:
            resultado = Resultado(fonte, "reaproveitado", caminho=caminho)
            _registrar(raiz, fonte, dia, inicio, relogio(config), resultado)
            resultados.append(resultado)
            continue
        resultado = _coletar_uma(fonte, dia, raiz, config, relogio, opcoes)
        resultados.append(resultado)
    return resultados


def _coletar_uma(fonte: str, dia: date, raiz: Path, config: Config, relogio, opcoes: dict) -> Resultado:
    inicio = relogio(config)
    http = None
    try:
        modulo = importlib.import_module(FONTES[fonte])
        http = modulo.criar_http(config)
        retrato = modulo.coletar(dia, config=config, http=http, **{k: v for k, v in opcoes.items() if k in getattr(modulo, "OPCOES", ())})
        caminho = caminho_retrato(raiz, fonte, dia)
        if caminho.exists():  # `forcar` com retrato existente: não sobrescreve, só registra a execução
            resultado = Resultado(fonte, "ok", caminho=caminho, registros=retrato.contagens(), requisicoes=http.requisicoes)
            resultado.erro = "retrato do dia já existia e foi mantido; esta execução só foi registrada no log"
        else:
            resultado = Resultado(fonte, "ok", caminho=gravar_retrato(raiz, retrato), registros=retrato.contagens(), requisicoes=http.requisicoes)
        metadados = retrato.metadados
    except Exception as e:  # noqa: BLE001 - uma fonte nunca derruba as outras; o erro vai para o log
        resultado = Resultado(fonte, "erro", erro=f"{type(e).__name__}: {e}"[:500], requisicoes=getattr(http, "requisicoes", 0))
        metadados = {}
    _registrar(raiz, fonte, dia, inicio, relogio(config), resultado, metadados)
    return resultado


def _registrar(raiz: Path, fonte: str, dia: date, inicio: datetime, fim: datetime, resultado: Resultado, metadados: dict | None = None) -> None:
    resultado.duracao_s = round((fim - inicio).total_seconds(), 2)
    registrar_log(
        raiz,
        fonte,
        dia,
        {
            "iniciado_em": inicio.isoformat(timespec="seconds"),
            "terminado_em": fim.isoformat(timespec="seconds"),
            "duracao_s": resultado.duracao_s,
            "status": resultado.status,
            "erro": resultado.erro,
            "requisicoes": resultado.requisicoes,
            "registros": resultado.registros,
            "metadados": metadados or {},
        },
    )
