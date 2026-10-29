"""T1.6 POC das Transferências Constitucionais do Tesouro Nacional (FPM, ITR e outras).

Uso:
    python scripts/poc_tesouro.py [--sem-fixtures]

O que faz:
- resolve o código INTERNO do Tesouro do município (não é o IBGE; coincide com o código SIAFI do
  CAUC) pelo dicionário `/municipios` e confere pelo `CO_IBGE` das linhas devolvidas;
- busca as transferências do município por ano, desde o início do recorte, em
  `/por_estado_municipio` (paginado, parâmetros em minúsculas);
- confere a completude por mês, soma FPM e ITR por ano e olha o detalhe por decêndio do mês mais
  recente (`/por_estado_municipio_detalhe`, parâmetros em MAIÚSCULAS) para saber se o mês fechou;
- grava amostras em tests/fixtures/tesouro/.

ATENÇÃO: não há OpenAPI. Os nomes de endpoint e de parâmetro vêm do código do pacote de terceiros
`tesouror` (github.com/StrategicProjects/tesouror) e foram confirmados aqui por chamadas reais. A API
diferencia maiúsculas de minúsculas nos nomes dos parâmetros e, com nome errado, tenta devolver a
série inteira e estoura o tempo (HTTP 504); por isso o cliente só aceita os nomes da lista abaixo.
"""

import argparse
import io
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from nucleo.config import carregar_config

BASE = "https://apiapex.tesouro.gov.br/aria/v1/transferencias_constitucionais/custom"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tesouro"
MAX_AMOSTRA = 50
PAGINA = 500
PAUSA_S = 0.5

# Parâmetros aceitos por endpoint (nomes exatos, com a caixa que a API exige).
PARAMETROS = {
    "transferencias": set(),
    "estados": set(),
    "municipios": {"p_nome", "p_uf"},
    "por_estado_municipio": {"p_estado", "p_municipio", "p_ano", "p_mes", "p_transferencia", "p_sn_detalhar", "page", "pageSize"},
    "por_estado_municipio_detalhe": {"P_ESTADO", "P_MUNICIPIOS", "P_ANO", "P_MES", "P_TRANSFERENCIA"},
}


class Cliente:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "verba-a-vista/0.1"})
        self.requisicoes = 0

    def get(self, endpoint: str, **params) -> dict:
        desconhecidos = set(params) - PARAMETROS[endpoint]
        if desconhecidos:
            raise ValueError(f"{endpoint}: parâmetros fora da lista (caixa importa): {sorted(desconhecidos)}")
        for tentativa in range(5):
            self.requisicoes += 1
            time.sleep(PAUSA_S)
            try:
                resp = self.http.get(f"{BASE}/{endpoint}", params=params)
            except httpx.HTTPError:
                if tentativa == 4:
                    raise
                time.sleep(2**tentativa)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and tentativa < 4:
                time.sleep(2 ** (tentativa + 1))
                continue
            resp.raise_for_status()
            corpo = resp.json()
            if corpo.get("status") != "ok":
                raise RuntimeError(f"{endpoint}: status {corpo.get('status')!r}: {str(corpo)[:200]}")
            return corpo
        raise RuntimeError("inalcançável")

    def todos(self, endpoint: str, **params) -> list[dict]:
        """Pagina `page`/`pageSize` até vir uma página incompleta (o campo `next` vem sempre preenchido)."""
        registros: list[dict] = []
        pagina = 1
        while True:
            corpo = self.get(endpoint, **params, page=pagina, pageSize=PAGINA)
            registros += corpo["registros"]
            if len(corpo["registros"]) < PAGINA:
                return registros
            pagina += 1


def salvar(nome: str, dados, gravar: bool) -> None:
    if gravar:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def titulo(texto: str) -> None:
    print(f"\n=== {texto}")


def centavos(valor: float) -> int:
    """Reais (float da API) para centavos inteiros, com arredondamento (nunca int(x * 100))."""
    return round(valor * 100)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sem-fixtures", action="store_true")
    args = parser.parse_args(argv)
    gravar = not args.sem_fixtures

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    config = carregar_config()
    ibge = int(config.regras.municipio.codigo_ibge)
    nome = config.regras.municipio.nome
    ano_inicio = config.regras.municipio.inicio_recorte.year
    hoje = datetime.now(ZoneInfo(config.regras.coleta.fuso)).date()
    c = Cliente()

    titulo("Dicionários")
    tipos = c.get("transferencias")["registros"]
    estados = c.get("estados")["registros"]
    print(f"  transferências: {len(tipos)}: {[(t['codigo'], t['transferencia']) for t in tipos]}")
    print(f"  estados: {len(estados)} (ex.: {estados[:3]})")
    achados = c.get("municipios", p_nome=nome)["registros"]
    print(f"  /municipios p_nome={nome!r}: {achados}")
    (alvo,) = [m for m in achados if m["nome"] == nome]
    codigo_municipio, codigo_uf = alvo["codigo"], alvo["codigo_uf"]
    estado = next(e["nome"] for e in estados if e["codigo"] == codigo_uf)
    print(f"  código do Tesouro do município: {codigo_municipio}; estado: {codigo_uf} ({estado})")
    salvar("transferencias.json", tipos, gravar)
    salvar("estados.json", estados, gravar)
    salvar("municipios_neves_paulista.json", achados, gravar)
    codigo_fpm = next(t["codigo"] for t in tipos if t["transferencia"] == "FPM")
    codigo_itr = next(t["codigo"] for t in tipos if t["transferencia"] == "ITR")

    titulo(f"por_estado_municipio, {ano_inicio} a {hoje.year}")
    todas: list[dict] = []
    for ano in range(ano_inicio, hoje.year + 1):
        regs = c.todos("por_estado_municipio", p_estado=codigo_uf, p_municipio=codigo_municipio, p_ano=ano)
        print(f"  {ano}: {len(regs)} linhas")
        todas += regs
    print(f"  campos: {sorted(todas[0])}")
    print(f"  todas do município? codigo_siafi={ {r['codigo_siafi'] for r in todas} } CO_IBGE={ {r['CO_IBGE'] for r in todas} } UF={ {r['UF'] for r in todas} } (esperado {ibge})")
    print(f"  tipos de MES/ANO: {type(todas[0]['MES']).__name__}/{type(todas[0]['ANO']).__name__}; VALOR: {type(todas[0]['VALOR']).__name__}")
    print(f"  linhas por transferência: {dict(Counter(r['TRANSFERENCIA'] for r in todas))}")

    titulo("Completude e totais por ano (FPM, ITR)")
    meses: dict[tuple[str, str], list[str]] = defaultdict(list)
    soma: dict[tuple[str, str], int] = defaultdict(int)
    for r in todas:
        meses[(r["TRANSFERENCIA"], r["ANO"])].append(r["MES"])
        soma[(r["TRANSFERENCIA"], r["ANO"])] += centavos(r["VALOR"])
    for tipo in ("FPM", "ITR"):
        for ano in range(ano_inicio, hoje.year + 1):
            ms = sorted(meses[(tipo, str(ano))])
            repetidos = [m for m, n in Counter(ms).items() if n > 1]
            print(f"  {tipo} {ano}: {len(ms)} meses {ms[0] if ms else '-'}..{ms[-1] if ms else '-'}, soma R$ {soma[(tipo, str(ano))] / 100:,.2f}, meses repetidos: {repetidos or 'nenhum'}")
    ultimo = max((r["ANO"], r["MES"]) for r in todas if r["TRANSFERENCIA"] == "FPM")
    print(f"  último mês de FPM disponível: {ultimo[0]}-{ultimo[1]} (hoje é {hoje.isoformat()})")

    titulo(f"Detalhe por decêndio do último mês ({ultimo[0]}-{ultimo[1]})")
    for codigo, rotulo in ((codigo_fpm, "FPM"), (codigo_itr, "ITR")):
        det = c.get("por_estado_municipio_detalhe", P_ESTADO=codigo_uf, P_MUNICIPIOS=codigo_municipio, P_ANO=ultimo[0], P_MES=int(ultimo[1]), P_TRANSFERENCIA=codigo)["registros"]
        for linha in det:
            soma_dec = linha["VA_PRIMEIRO_DEC"] + linha["VA_SEGUNDO_DEC"] + linha["VA_TERCEIRO_DEC"]
            print(f"  {rotulo}: {linha}  soma dos decêndios={soma_dec:.2f}")
        salvar(f"detalhe_{rotulo.lower()}_{ultimo[0]}_{ultimo[1]}.json", det, gravar)

    # amostra: FPM, ITR e FPM 1% dos dois últimos anos, até 50 linhas
    recentes = [r for r in todas if r["TRANSFERENCIA"] in ("FPM", "ITR", "FPM 1%") and int(r["ANO"]) >= hoje.year - 1]
    recentes.sort(key=lambda r: (r["TRANSFERENCIA"], r["ANO"], r["MES"]))
    salvar("por_estado_municipio.json", {"parametros": {"p_estado": codigo_uf, "p_municipio": codigo_municipio, "p_ano": f"{ano_inicio}..{hoje.year}"}, "total_linhas": len(todas), "amostra": recentes[:MAX_AMOSTRA]}, gravar)
    print(f"\nRequisições feitas: {c.requisicoes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
