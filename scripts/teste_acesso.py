"""T1.0: testa o acesso a cada base URL de config/fontes.yaml a partir do ambiente atual.

Uso:
    python scripts/teste_acesso.py [--ambiente local|actions]

Faz uma requisição GET simples por URL, sem credenciais. Qualquer resposta HTTP prova que o host é
alcançável; 401 no Portal da Transparência é esperado (sem chave). 403 é ambíguo: pode ser bloqueio
do ambiente ou da fonte, por isso o início do corpo da resposta aparece na nota.
Imprime uma tabela em markdown para colar em docs/fontes.md (§Acesso).
"""

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from nucleo.config import Config, carregar_config

TIMEOUT_S = 20


@dataclass
class Resultado:
    fonte: str
    url: str | None
    status: int | None = None
    ms: int | None = None
    nota: str = ""

    @property
    def alcancou(self) -> bool:
        return self.status is not None

    @property
    def veredito(self) -> str:
        if self.url is None:
            return "sem URL (A VERIFICAR)"
        if self.status is None:
            return "FALHOU"
        if self.status == 403:
            return "403 (possível bloqueio)"
        return f"HTTP {self.status}"


def alvos(config: Config) -> list[tuple[str, str | None]]:
    """(nome, url) de cada fonte ativa; uma URL por módulo quando a fonte tem módulos."""
    saida: list[tuple[str, str | None]] = []
    for nome, fonte in config.fontes.fontes.items():
        if not fonte.ativa:
            continue
        if fonte.base_url and fonte.modulos and fonte.docs:
            for modulo in fonte.modulos:
                saida.append((f"{nome}/{modulo}", fonte.docs.format(base_url=fonte.base_url, modulo=modulo)))
        else:
            saida.append((nome, fonte.base_url or fonte.url))
    return saida


def testar_url(cliente: httpx.Client, nome: str, url: str | None) -> Resultado:
    if url is None:
        return Resultado(nome, None)
    inicio = time.monotonic()
    try:
        resp = cliente.get(url)
    except httpx.HTTPError as e:
        return Resultado(nome, url, nota=f"{type(e).__name__}: {e}"[:120])
    ms = round((time.monotonic() - inicio) * 1000)
    nota = ""
    if resp.status_code == 403:
        nota = " ".join(resp.text.split())[:80]
    return Resultado(nome, url, resp.status_code, ms, nota)


def testar(config: Config, cliente: httpx.Client) -> list[Resultado]:
    return [testar_url(cliente, nome, url) for nome, url in alvos(config)]


def tabela_markdown(resultados: list[Resultado], ambiente: str, quando: datetime) -> str:
    linhas = [
        f"Ambiente: {ambiente} · {quando.isoformat(timespec='seconds')}",
        "",
        "| Fonte | URL | Resultado | Tempo | Nota |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in resultados:
        tempo = f"{r.ms} ms" if r.ms is not None else "-"
        linhas.append(f"| {r.fonte} | {r.url or '-'} | {r.veredito} | {tempo} | {r.nota or '-'} |")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ambiente", default="local", help="rótulo do ambiente (local, actions)")
    args = parser.parse_args(argv)

    config = carregar_config()
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True, headers={"User-Agent": "verba-a-vista/0.1"}) as cliente:
        resultados = testar(config, cliente)
    agora = datetime.now(ZoneInfo(config.regras.coleta.fuso))
    print(tabela_markdown(resultados, args.ambiente, agora))
    return 0 if all(r.alcancou for r in resultados if r.url) else 1


if __name__ == "__main__":
    sys.exit(main())
