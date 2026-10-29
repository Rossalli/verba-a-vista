"""T1.3 POC da API de dados abertos do Obrasgov (nova versão, FastAPI).

Uso:
    python scripts/poc_obrasgov.py [--sem-fixtures]

O que faz:
- baixa o OpenAPI (`/obras/openapi.json`) e valida cada nome de parâmetro antes de chamar (as APIs
  do governo costumam ignorar parâmetros desconhecidos e devolver tudo);
- acha as obras do município por duas rotas e compara: `geometria.cod_ibge` (onde a obra está) e
  `projeto-investimento.cnpj_organizacao_resp` (quem é o responsável);
- para cada projeto, busca execução física, histórico de situação (cancelada/paralisada, com
  justificativa), contratos e empenhos;
- imprime totais, campos, valores distintos e estruturas aninhadas; grava amostras em
  tests/fixtures/obrasgov/ (máx. 50 registros).
"""

import argparse
import csv
import io
import json
import sys
import time
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from nucleo.config import carregar_config

BASE = "https://api-publica.obrasgov.gestao.gov.br/obras"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "obrasgov"
MAX_AMOSTRA = 50
PAGINA = 200
PAUSA_S = 0.3


class Cliente:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "verba-a-vista/0.1"})
        self._spec: dict | None = None
        self.requisicoes = 0

    @property
    def spec(self) -> dict:
        if self._spec is None:
            self._spec = self._get(f"{BASE}/openapi.json", {}).json()
        return self._spec

    def _get(self, url: str, params: dict) -> httpx.Response:
        for tentativa in range(4):
            self.requisicoes += 1
            time.sleep(PAUSA_S)
            try:
                resp = self.http.get(url, params=params)
            except httpx.HTTPError:
                if tentativa == 3:
                    raise
                time.sleep(2**tentativa)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and tentativa < 3:
                time.sleep(2 ** (tentativa + 1))
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("inalcançável")

    def validar(self, endpoint: str, params: dict) -> None:
        validos = {p["name"] for p in self.spec["paths"][f"/{endpoint}"]["get"].get("parameters", [])}
        desconhecidos = set(params) - validos
        if desconhecidos:
            raise ValueError(f"{endpoint}: parâmetros fora do OpenAPI: {sorted(desconhecidos)}")

    def pagina(self, endpoint: str, params: dict, validar: bool = True) -> dict:
        if validar:
            self.validar(endpoint, params)
        return self._get(f"{BASE}/{endpoint}", params).json()

    def todos(self, endpoint: str, params: dict) -> tuple[list[dict], int]:
        registros: list[dict] = []
        pagina = 1
        while True:
            dados = self.pagina(endpoint, {**params, "pagina": pagina, "tamanho_da_pagina": PAGINA})
            registros += dados["data"]
            if pagina >= dados["total_pages"]:
                return registros, dados["total_items"]
            pagina += 1

    def total(self, endpoint: str, params: dict, validar: bool = True) -> int:
        return self.pagina(endpoint, {**params, "pagina": 1, "tamanho_da_pagina": 1}, validar)["total_items"]


PONTE_URL = "https://repositorio.dados.gov.br/seges/detru/siconv_dados_obrasgov_geral.zip"


def carregar_ponte(c: "Cliente") -> dict[str, str]:
    """id_projeto_investimento -> nr_instrumento (NR_CONVENIO do Siconv). Ignora link_transparencia (traz usuário/senha guest)."""
    resp = c._get(PONTE_URL, {})
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        (nome,) = zf.namelist()
        linhas = zf.read(nome).decode("utf-8-sig").splitlines()
    leitor = csv.DictReader(linhas, delimiter=";")
    return {r["id_projeto_investimento"]: r["nr_instrumento"] for r in leitor}


def salvar(nome: str, url: str, params: dict, registros: list[dict], total: int, gravar: bool) -> None:
    if not gravar:
        return
    FIXTURES.mkdir(parents=True, exist_ok=True)
    corpo = {
        "url": url,
        "params": params,
        "coletado_em": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
        "total_items": total,
        "amostra": registros[:MAX_AMOSTRA],
    }
    (FIXTURES / f"{nome}.json").write_text(json.dumps(corpo, ensure_ascii=False, indent=2), encoding="utf-8")


def distintos(registros: list[dict], *campos: str) -> None:
    for campo in campos:
        print(f"    {campo}: {dict(Counter(r.get(campo) for r in registros).most_common())}")


def titulo(texto: str) -> None:
    print(f"\n=== {texto}")


def curto(valor, n: int = 160):
    texto = json.dumps(valor, ensure_ascii=False)
    return texto if len(texto) <= n else texto[:n] + "…"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sem-fixtures", action="store_true")
    args = parser.parse_args(argv)
    gravar = not args.sem_fixtures

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    config = carregar_config()
    ibge = int(config.regras.municipio.codigo_ibge)
    cnpj = config.regras.municipio.cnpj_prefeitura
    uf = config.regras.municipio.uf
    c = Cliente()

    titulo("Data de atualização dos dados")
    print(f"  {c.pagina('data-atualizacao', {})}")

    titulo(f"geometria  filtro cod_ibge={ibge}")
    params = {"cod_ibge": ibge}
    geos, total = c.todos("geometria", params)
    sem_filtro = c.total("geometria", {})
    falso = c.total("geometria", {"cod_ibgex": ibge}, validar=False)
    print(f"  geometrias do município: {len(geos)} (total_items={total}); sem filtro: {sem_filtro}")
    print(f"  controle: parâmetro falso devolve {falso} (== sem filtro? {falso == sem_filtro})")
    print(f"  todas com o IBGE pedido: {all(g['cod_ibge'] == ibge for g in geos)}")
    if geos:
        print(f"  campos: {sorted(geos[0])}")
        distintos(geos, "no_municipio", "sg_uf", "origem_geometria")
    salvar("geometria", f"{BASE}/geometria", params, geos, total, gravar)
    ids_geo = {g["id_projeto_investimento"] for g in geos}
    print(f"  projetos distintos pela geometria: {len(ids_geo)}")

    titulo(f"projeto-investimento  filtro cnpj_organizacao_resp={cnpj}")
    params = {"cnpj_organizacao_resp": cnpj}
    por_cnpj, total = c.todos("projeto-investimento", params)
    print(f"  projetos com a prefeitura como responsável: {len(por_cnpj)} (total_items={total}); total SP: {c.total('projeto-investimento', {'uf_principal': uf})}")
    ids_cnpj = {p["id_projeto_investimento"] for p in por_cnpj}
    print(f"  só pela geometria: {len(ids_geo - ids_cnpj)}; só pelo CNPJ: {len(ids_cnpj - ids_geo)}; nos dois: {len(ids_geo & ids_cnpj)}")

    ids = sorted(ids_geo | ids_cnpj)
    titulo(f"projeto-investimento  por id_projeto_investimento ({len(ids)} projetos)")
    projetos: list[dict] = []
    for i in ids:
        regs, _ = c.todos("projeto-investimento", {"id_projeto_investimento": i})
        projetos += regs
    print(f"  projetos carregados: {len(projetos)}")
    if projetos:
        print(f"  campos: {sorted(projetos[0])}")
        distintos(projetos, "situacao", "natureza_intervencao", "especie_intervencao", "uf_principal", "organizacao_resp", "cnpj_organizacao_resp", "sistema_resp", "ano_cadastro", "projeto_estruturante")
        for campo in ("repassadores", "tomadores", "executores", "investimentos_previstos"):
            exemplo = next((p[campo] for p in projetos if p.get(campo)), None)
            print(f"    exemplo de {campo}: {curto(exemplo)}")
    salvar("projeto-investimento", f"{BASE}/projeto-investimento", {"id_projeto_investimento": "<ids>"}, projetos, len(projetos), gravar)

    titulo("execucao-fisica  por id_projeto_investimento")
    execucoes: list[dict] = []
    for i in ids:
        regs, _ = c.todos("execucao-fisica", {"id_projeto_investimento": i})
        execucoes += regs
    print(f"  registros de execução física: {len(execucoes)}")
    if execucoes:
        print(f"  campos: {sorted(execucoes[0])}")
        distintos(execucoes, "tipo_instrumento", "tipo_forma_execucao")
        for campo in ("indicativos", "motivos"):
            exemplo = [e[campo] for e in execucoes if e.get(campo)][:3]
            print(f"    exemplos de {campo} (não vazios: {sum(1 for e in execucoes if e.get(campo))}): {curto(exemplo, 500)}")
        atual = [e["dt_atualizacao_execucao"] for e in execucoes if e.get("dt_atualizacao_execucao")]
        print(f"  dt_atualizacao_execucao: mais antiga {min(atual) if atual else None}, mais recente {max(atual) if atual else None}")
    salvar("execucao-fisica", f"{BASE}/execucao-fisica", {"id_projeto_investimento": "<ids>"}, execucoes, len(execucoes), gravar)

    titulo("historico-situacao-cancelada-paralisada  por id_projeto_investimento")
    historico: list[dict] = []
    for i in ids:
        regs, _ = c.todos("historico-situacao-cancelada-paralisada", {"id_projeto_investimento": i})
        historico += regs
    print(f"  registros de histórico: {len(historico)}")
    if historico:
        print(f"  campos: {sorted(historico[0])}")
        distintos(historico, "descricao_historico_situacao_investimento", "possui_tratativas_situacao_investimento", "fase_tratativas_situacao_investimento")
        print(f"  justificativas (primeiras 5): {curto([h['justificativa_cancelada_paralisada'] for h in historico][:5], 900)}")
    salvar("historico-situacao-cancelada-paralisada", f"{BASE}/historico-situacao-cancelada-paralisada", {"id_projeto_investimento": "<ids>"}, historico, len(historico), gravar)

    for endpoint in ("contrato", "empenho"):
        titulo(f"{endpoint}  por id_projeto_investimento")
        regs_todos: list[dict] = []
        for i in ids:
            regs, _ = c.todos(endpoint, {"id_projeto_investimento": i})
            regs_todos += regs
        print(f"  registros: {len(regs_todos)}")
        if regs_todos:
            print(f"  campos: {sorted(regs_todos[0])}")
        salvar(endpoint, f"{BASE}/{endpoint}", {"id_projeto_investimento": "<ids>"}, regs_todos, len(regs_todos), gravar)

    titulo("Ponte Obrasgov <-> Siconv (siconv_dados_obrasgov_geral): id_projeto_investimento -> nr_instrumento")
    ponte = carregar_ponte(c)
    print(f"  linhas na ponte: {len(ponte)}")
    for i in ids:
        print(f"  {i} -> nr_instrumento {ponte.get(i)!r}")
    salvar("ponte_siconv", PONTE_URL, {}, [{"id_projeto_investimento": i, "nr_instrumento": ponte.get(i)} for i in ids], len(ids), gravar)

    titulo("Executores dos projetos (a prefeitura é executora, não 'organização responsável')")
    for p in projetos:
        cnpjs = [e.get("cnpj_executor") for e in (p.get("executores") or [])]
        print(f"  {p['id_projeto_investimento']}: executores={cnpjs}; do município? {cnpj in cnpjs}; sistema_resp={p['sistema_resp']}")

    titulo(f"Controle: projetos de {uf} por situação (total_items)")
    for situacao in ("Cadastrada", "Em execução", "Paralisada", "Cancelada", "Inacabada", "Concluída"):
        print(f"  {situacao}: {c.total('projeto-investimento', {'uf_principal': uf, 'situacao': situacao})}")

    titulo("Controle: os endpoints de execução física e de histórico têm dados em outros lugares? (1ª página, qualquer município)")
    for endpoint, campos in (("execucao-fisica", ("tipo_instrumento", "tipo_forma_execucao")), ("historico-situacao-cancelada-paralisada", ("descricao_historico_situacao_investimento", "fase_tratativas_situacao_investimento"))):
        pagina = c.pagina(endpoint, {"pagina": 1, "tamanho_da_pagina": PAGINA})
        regs = pagina["data"]
        print(f"  {endpoint}: total_items={pagina['total_items']}")
        distintos(regs, *campos)
        com_motivos = [r for r in regs if r.get("motivos")] or [r for r in regs if r.get("justificativa_cancelada_paralisada")]
        print(f"    exemplo com motivo/justificativa (outro município): {curto(com_motivos[:2], 700)}")
        salvar(f"exemplo_outros_municipios__{endpoint}", f"{BASE}/{endpoint}", {"pagina": 1}, (com_motivos or regs)[:5], pagina["total_items"], gravar)

    print(f"\nRequisições feitas: {c.requisicoes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
