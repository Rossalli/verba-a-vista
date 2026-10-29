"""T1.7 POC de oportunidades: programas e editais que o município pode pleitear.

Uso:
    python scripts/poc_oportunidades.py [--cache DIR] [--data AAAA-MM-DD] [--sem-fixtures]

Fontes verificadas (docs/fontes.md):
- Siconv em lote (`siconv_programa`, `siconv_programa_proponentes`, `siconv_proposta_selecao_pac`,
  `siconv_proponentes`): programas com janelas de recebimento, natureza jurídica elegível e UF; programas
  dirigidos a proponentes específicos; propostas do Novo PAC Seleções.
- Transferegov API: `parcerias/programa` (janelas por tipo de beneficiário),
  `parcerias/beneficiario_emenda_parlamentar` (emendas indicadas ao município).

O arquivo do Siconv é uma carga antiga (veja `data_carga_siconv.txt`): "aberto hoje" calculado sobre
ele é um MÍNIMO (programas criados depois da carga não aparecem).
"""

import argparse
import csv
import importlib.util
import io
import json
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from nucleo.config import carregar_config

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "tests" / "fixtures" / "oportunidades"
API = "https://api-publica.transferegov.gestao.gov.br/parcerias"
MAX_AMOSTRA = 50
JANELAS = {"RECEB_PROP": "propostas voluntárias", "EMENDA_PAR": "emendas parlamentares", "BENEF_ESP": "beneficiários específicos"}

# reaproveita baixar/ler_filtrado da POC das Discricionárias (mesmo servidor, mesmo formato)
_spec = importlib.util.spec_from_file_location("_disc", RAIZ / "scripts" / "poc_transferegov_discricionarias.py")
_disc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_disc)


def janela_aberta(inicio: str, fim: str, referencia: date) -> bool:
    """Janela `dd/mm/aaaa` aberta na data de referência. Sem data de fim, não conta como aberta."""
    ini = pd.to_datetime(inicio, format="%d/%m/%Y", errors="coerce")
    f = pd.to_datetime(fim, format="%d/%m/%Y", errors="coerce")
    ref = pd.Timestamp(referencia)
    if pd.isna(f):
        return False
    return bool((pd.isna(ini) or ini <= ref) and ref <= f)


def mascara_aberta(programas: pd.DataFrame, janela: str, referencia: date) -> pd.Series:
    """Máscara das linhas com a janela (RECEB_PROP, EMENDA_PAR ou BENEF_ESP) aberta em `referencia`.

    Vetorizado (a tabela tem 1,2 milhão de linhas); mesma regra de `janela_aberta`.
    """
    ini = pd.to_datetime(programas[f"DT_PROG_INI_{janela}"], format="%d/%m/%Y", errors="coerce")
    fim = pd.to_datetime(programas[f"DT_PROG_FIM_{janela}"], format="%d/%m/%Y", errors="coerce")
    ref = pd.Timestamp(referencia)
    return fim.notna() & (ini.isna() | (ini <= ref)) & (ref <= fim)


def abertos(programas: pd.DataFrame, janela: str, referencia: date) -> pd.DataFrame:
    """Linhas de `siconv_programa` com a janela aberta em `referencia`."""
    return programas[mascara_aberta(programas, janela, referencia)]


def elegiveis(programas: pd.DataFrame, uf: str) -> pd.DataFrame:
    """Programas para administração municipal, da UF do município (ou sem UF), sem repetir o mesmo programa."""
    municipal = programas["NATUREZA_JURIDICA_PROGRAMA"].str.contains("Municipal", na=False)
    da_uf = programas["UF_PROGRAMA"].isin([uf, ""])
    return programas[municipal & da_uf].drop_duplicates("ID_PROGRAMA")


def salvar_csv(nome: str, df: pd.DataFrame, gravar: bool) -> None:
    if gravar:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        df.head(MAX_AMOSTRA).to_csv(FIXTURES / nome, sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)


def salvar_json(nome: str, dados, gravar: bool) -> None:
    if gravar:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def titulo(texto: str) -> None:
    print(f"\n=== {texto}")


def api_todos(http: httpx.Client, endpoint: str, **params) -> list[dict]:
    registros, pagina = [], 1
    while True:
        time.sleep(0.3)
        resp = http.get(f"{API}/{endpoint}", params={**params, "pagina": pagina, "tamanho_da_pagina": 200})
        resp.raise_for_status()
        corpo = resp.json()
        registros += corpo["data"]
        if pagina >= corpo["total_pages"]:
            return registros
        pagina += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache", type=Path, default=RAIZ / ".cache" / "siconv")
    parser.add_argument("--data", type=date.fromisoformat, default=None, help="data de referência (padrão: hoje)")
    parser.add_argument("--sem-fixtures", action="store_true")
    args = parser.parse_args(argv)
    gravar = not args.sem_fixtures

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    config = carregar_config()
    cnpj, uf, nome = config.regras.municipio.cnpj_prefeitura, config.regras.municipio.uf, config.regras.municipio.nome
    hoje = args.data or datetime.now(ZoneInfo(config.regras.coleta.fuso)).date()
    print(f"Data de referência: {hoje.isoformat()}")

    titulo("Siconv: proponente e programas dirigidos ao município")
    zips = {n: _disc.baixar(n, args.cache) for n in ("proponentes", "programa", "programa_proponentes", "proposta_selecao_pac")}
    proponente = _disc.ler_filtrado(zips["proponentes"], "IDENTIF_PROPONENTE", {cnpj})[["ID_PROPONENTE", "IDENTIF_PROPONENTE", "NM_PROPONENTE"]]
    print(f"  proponente: {proponente.to_dict('records')}")
    ids_proponente = set(proponente["ID_PROPONENTE"])
    dirigidos = _disc.ler_filtrado(zips["programa_proponentes"], "ID_PROPONENTE", ids_proponente)
    print(f"  programas com o município como proponente específico: {len(dirigidos)}")

    titulo("Siconv: programas e janelas")
    programas = _disc.ler_filtrado(zips["programa"], "SIT_PROGRAMA", {"DISPONIBILIZADO", "CADASTRADO", "INATIVO"})
    print(f"  programas no arquivo: {len(programas)}; colunas: {list(programas.columns)}")
    print(f"  SIT_PROGRAMA: {dict(Counter(programas['SIT_PROGRAMA']))}")
    print(f"  programas distintos (ID_PROGRAMA): {programas['ID_PROGRAMA'].nunique()} (a tabela repete o programa por UF e natureza jurídica)")
    for janela, rotulo in JANELAS.items():
        aberta = abertos(programas, janela, hoje)
        print(f"  janela {rotulo} aberta em {hoje}: {aberta['ID_PROGRAMA'].nunique()} programas ({len(aberta)} linhas)")
    receb = abertos(programas, "RECEB_PROP", hoje)
    pri = elegiveis(receb, uf)
    print(f"  propostas voluntárias abertas e elegíveis (natureza municipal, UF {uf} ou sem UF): {len(pri)}")
    print(f"    SIT_PROGRAMA: {dict(Counter(pri['SIT_PROGRAMA']))}; modalidades: {dict(Counter(pri['MODALIDADE_PROGRAMA']))}")
    print(f"    órgãos: {dict(Counter(pri['DESC_ORGAO_SUP_PROGRAMA']).most_common(6))}")
    for linha in pri.itertuples():
        print(f"    {linha.ID_PROGRAMA} {linha.SIT_PROGRAMA} até {linha.DT_PROG_FIM_RECEB_PROP} | {linha.NOME_PROGRAMA[:80]}")
    print(f"  subtipos de programa: {dict(Counter(programas['NOME_SUBTIPO_PROGRAMA']).most_common(8))}")
    abertos_dirigidos = programas[programas["ID_PROGRAMA"].isin(set(dirigidos["ID_PROGRAMA"]))]
    alguma_aberta = pd.Series(False, index=abertos_dirigidos.index)
    for janela in JANELAS:
        alguma_aberta |= mascara_aberta(abertos_dirigidos, janela, hoje)
    print(f"  programas dirigidos ao município: {abertos_dirigidos['ID_PROGRAMA'].nunique()}; com alguma janela aberta em {hoje}: {abertos_dirigidos[alguma_aberta]['ID_PROGRAMA'].nunique()}")
    salvar_csv("siconv_programas_elegiveis_abertos.csv", pri, gravar)
    salvar_csv("siconv_programa_proponentes_municipio.csv", dirigidos, gravar)

    titulo("Siconv: Novo PAC Seleções (proposta_selecao_pac) do município")
    pac = _disc.ler_filtrado(zips["proposta_selecao_pac"], "ID_PROPONENTE", ids_proponente)
    print(f"  propostas: {len(pac)}; situações: {dict(Counter(pac['SITUACAO_PROPOSTA_SELECAO_PAC']))}")
    pac_programas = programas[programas["ID_PROGRAMA"].isin(set(pac["ID_PROGRAMA"]))][["ID_PROGRAMA", "NOME_PROGRAMA", "SIT_PROGRAMA", "NOME_SUBTIPO_PROGRAMA", "DT_PROG_FIM_RECEB_PROP"]]
    unicos = pac_programas.drop_duplicates("ID_PROGRAMA")
    print(f"  programas distintos dessas propostas: {len(unicos)}; subtipos: {dict(Counter(unicos['NOME_SUBTIPO_PROGRAMA']))}; SIT: {dict(Counter(unicos['SIT_PROGRAMA']))}")
    # a justificativa é texto longo livre: fica de fora da amostra
    salvar_csv("siconv_selecao_pac_municipio.csv", pac.drop(columns=["JUSTIFICATIVA_PROPOSTA_SELECAO_PAC"]), gravar)

    titulo("Transferegov API: parcerias/programa com janela aberta")
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "verba-a-vista/0.1"}) as http:
        disponiveis = api_todos(http, "programa", situacao_programa="Disponibilizado")
        print(f"  programas Disponibilizado (país): {len(disponiveis)}")
        abertos_api = []
        for p in disponiveis:
            for tipo in ("espontaneo", "especifico", "emenda"):
                ini, fim = p.get(f"dt_inicio_beneficiario_{tipo}"), p.get(f"dt_fim_beneficiario_{tipo}")
                if fim and (not ini or date.fromisoformat(ini[:10]) <= hoje) and hoje <= date.fromisoformat(fim[:10]):
                    abertos_api.append({"tipo_janela": tipo, "id_programa": p["id_programa"], "cd_programa": p["cd_programa"], "nm_programa": p["nm_programa"], "tp_instrumento": p["tp_instrumento"], "qualificacao_beneficiario": p["qualificacao_beneficiario"], "dt_fim": fim})
        print(f"  com janela aberta em {hoje}: {len(abertos_api)} -> {dict(Counter((a['tipo_janela'], a['qualificacao_beneficiario']) for a in abertos_api))}")
        print(f"  qualificações (todos os Disponibilizado): {dict(Counter(p['qualificacao_beneficiario'] for p in disponiveis))}")
        salvar_json("parcerias_programas_abertos.json", abertos_api, gravar)

        titulo("Transferegov API: parcerias/beneficiario_emenda_parlamentar do município")
        emendas = api_todos(http, "beneficiario_emenda_parlamentar", nm_municipio_beneficiario_emenda=nome.upper(), sg_uf_beneficiario_emenda=uf)
        print(f"  emendas indicadas: {len(emendas)}; por beneficiário: {dict(Counter(e['nm_beneficiario_emenda'] for e in emendas))}")
        print(f"  por ano e tipo: {dict(Counter((e['aa_emenda'], e['in_tipo_emenda_parlamentar']) for e in emendas))}; total R$ {sum(e['vl_total_emenda'] or 0 for e in emendas):,.2f}")
        salvar_json("parcerias_emendas_indicadas.json", emendas, gravar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
