"""T1.2 POC Transferegov Discricionárias e Legais (antigo Siconv), download em lote em CSV.

Uso:
    python scripts/poc_transferegov_discricionarias.py [--cache DIR] [--sem-fixtures]

O que faz:
- baixa (com cache em --cache, padrão .cache/siconv, fora do Git) os zips de
  https://repositorio.dados.gov.br/seges/detru/ necessários para o município;
- lê cada CSV em blocos e filtra pelo município: `siconv_proposta` por COD_MUNIC_IBGE; as demais
  tabelas por ID_PROPOSTA ou NR_CONVENIO das propostas do município;
- imprime totais, colunas, valores distintos de situação e contagens por recorte de data;
- grava amostras (máx. 50 linhas por tabela, mesmo formato do original) em
  tests/fixtures/transferegov_discricionarias/.
"""

import argparse
import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

import httpx
import pandas as pd

from nucleo.config import carregar_config

BASE = "https://repositorio.dados.gov.br/seges/detru"
RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "tests" / "fixtures" / "transferegov_discricionarias"
MAX_AMOSTRA = 50
BLOCO = 200_000
# arquivos usados; `contrato` e `proponentes` ficaram de fora (sem chave do município / contêm contatos)
ARQUIVOS = ["proposta", "proposta_cancelada", "convenio", "emenda", "historico_situacao", "desembolso", "prorroga_oficio"]


def baixar(nome: str, cache: Path) -> Path:
    """Baixa siconv_<nome>.csv.zip para o cache, pulando se já existe com o mesmo tamanho."""
    destino = cache / f"siconv_{nome}.csv.zip"
    url = f"{BASE}/siconv_{nome}.csv.zip"
    cache.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as http:
        tamanho = int(http.head(url).headers["content-length"])
        if destino.exists() and destino.stat().st_size == tamanho:
            return destino
        with http.stream("GET", url) as resp:
            resp.raise_for_status()
            with destino.open("wb") as f:
                for pedaco in resp.iter_bytes(1 << 20):
                    f.write(pedaco)
    return destino


def ler_filtrado(caminho_zip: Path, coluna: str, valores: set[str]) -> pd.DataFrame:
    """Linhas do (único) CSV do zip cuja `coluna` está em `valores`. Tudo como texto, sem converter."""
    with zipfile.ZipFile(caminho_zip) as zf:
        (nome,) = zf.namelist()
        with zf.open(nome) as f:
            blocos = pd.read_csv(f, sep=";", dtype=str, encoding="utf-8-sig", chunksize=BLOCO, keep_default_na=False)
            partes = [b[b[coluna].isin(valores)] for b in blocos]
    return pd.concat(partes) if partes else pd.DataFrame()


def salvar(nome: str, df: pd.DataFrame, gravar: bool) -> None:
    if not gravar:
        return
    FIXTURES.mkdir(parents=True, exist_ok=True)
    df.head(MAX_AMOSTRA).to_csv(FIXTURES / f"{nome}.csv", sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)


def priorizar(df: pd.DataFrame, coluna: str, prioritarios: set[str]) -> pd.DataFrame:
    """Põe primeiro as linhas cuja `coluna` está em `prioritarios` (ordem original preservada em cada grupo)."""
    return df.assign(_p=~df[coluna].isin(prioritarios)).sort_values("_p", kind="stable").drop(columns="_p")


def distintos(df: pd.DataFrame, *colunas: str) -> None:
    for c in colunas:
        if c in df:
            print(f"    {c}: {dict(Counter(df[c]).most_common())}")


def titulo(texto: str) -> None:
    print(f"\n=== {texto}")


def data_iso(serie: pd.Series) -> pd.Series:
    """Datas do CSV vêm como dd/mm/aaaa (ou aaaa-mm-dd); devolve datetime, NaT se vazio."""
    return pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce").fillna(pd.to_datetime(serie, format="%Y-%m-%d", errors="coerce"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache", type=Path, default=RAIZ / ".cache" / "siconv")
    parser.add_argument("--sem-fixtures", action="store_true")
    args = parser.parse_args(argv)
    gravar = not args.sem_fixtures

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    config = carregar_config()
    ibge = config.regras.municipio.codigo_ibge
    inicio = pd.Timestamp(config.regras.municipio.inicio_recorte)

    titulo("Data da carga")
    (args.cache).mkdir(parents=True, exist_ok=True)
    print(f"  data_carga_siconv.txt: {httpx.get(f'{BASE}/data_carga_siconv.txt', timeout=60).text.strip()!r}")

    zips = {n: baixar(n, args.cache) for n in ARQUIVOS}

    titulo(f"siconv_proposta  filtro COD_MUNIC_IBGE={ibge}")
    prop = ler_filtrado(zips["proposta"], "COD_MUNIC_IBGE", {ibge})
    print(f"  propostas do município: {len(prop)}")
    print(f"  colunas: {list(prop.columns)}")
    distintos(prop, "MUNIC_PROPONENTE", "UF_PROPONENTE", "NATUREZA_JURIDICA", "MODALIDADE", "SIT_PROPOSTA", "SITUACAO_PROJETO_BASICO", "SITUACAO_CONTA", "ANO_PROP", "DESC_ORGAO_SUP")
    print(f"  proponentes (CNPJ, nome): {dict(Counter(zip(prop['IDENTIF_PROPONENTE'], prop['NM_PROPONENTE'])).most_common())}")
    ids = set(prop["ID_PROPOSTA"])

    titulo("siconv_proposta_cancelada  filtro COD_MUNIC_IBGE (propostas canceladas ficam em arquivo à parte)")
    canc = ler_filtrado(zips["proposta_cancelada"], "COD_MUNIC_IBGE", {ibge})
    print(f"  propostas canceladas do município: {len(canc)}; ids também em siconv_proposta: {len(set(canc['ID_PROPOSTA']) & ids)}")
    distintos(canc, "SIT_PROPOSTA", "MODALIDADE", "ANO_PROP", "NM_PROPONENTE")
    salvar("proposta_cancelada", canc, gravar)
    todas = pd.concat([prop.assign(ORIGEM="proposta"), canc.assign(ORIGEM="proposta_cancelada")])
    ids |= set(canc["ID_PROPOSTA"])

    titulo("siconv_convenio  por ID_PROPOSTA (a tabela não tem município)")
    conv = ler_filtrado(zips["convenio"], "ID_PROPOSTA", ids)
    print(f"  convênios/contratos de repasse: {len(conv)}")
    print(f"  colunas: {list(conv.columns)}")
    distintos(conv, "SIT_CONVENIO", "SUBSITUACAO_CONV", "SITUACAO_PUBLICACAO", "INSTRUMENTO_ATIVO", "SITUACAO_CONTRATACAO", "IND_ASSINADO", "MOTIVO_SUSPENSAO", "ANO")
    print(f"  com DATA_SUSPENSIVA preenchida: {(conv['DATA_SUSPENSIVA'] != '').sum()}; com DATA_RETIRADA_SUSPENSIVA: {(conv['DATA_RETIRADA_SUSPENSIVA'] != '').sum()}")
    print(f"  exemplos de valores: {conv[['VL_GLOBAL_CONV', 'VL_REPASSE_CONV', 'VL_DESEMBOLSADO_CONV', 'VL_SALDO_REMAN_TESOURO']].head(6).values.tolist()}")
    salvar("convenio", conv, gravar)
    nrs = set(conv["NR_CONVENIO"])
    # a amostra (máx. 50 linhas) prioriza o que importa: propostas do recorte e as que viraram convênio
    recentes = set(todas.loc[data_iso(todas["DIA_PROPOSTA"]) >= inicio, "ID_PROPOSTA"])
    prioritarios = recentes | set(conv["ID_PROPOSTA"])
    salvar("proposta", priorizar(prop, "ID_PROPOSTA", prioritarios), gravar)

    titulo("siconv_emenda  por ID_PROPOSTA")
    em = ler_filtrado(zips["emenda"], "ID_PROPOSTA", ids)
    print(f"  linhas de emenda: {len(em)}; propostas com emenda: {em['ID_PROPOSTA'].nunique() if len(em) else 0}")
    distintos(em, "QUALIF_PROPONENTE", "IND_IMPOSITIVO", "TIPO_PARLAMENTAR")
    salvar("emenda", em, gravar)

    titulo("siconv_historico_situacao  por ID_PROPOSTA")
    hist = ler_filtrado(zips["historico_situacao"], "ID_PROPOSTA", ids)
    print(f"  linhas de histórico: {len(hist)}")
    distintos(hist, "HISTORICO_SIT")
    salvar("historico_situacao", priorizar(hist, "ID_PROPOSTA", prioritarios), gravar)

    titulo("siconv_desembolso  por NR_CONVENIO")
    des = ler_filtrado(zips["desembolso"], "NR_CONVENIO", nrs)
    print(f"  desembolsos: {len(des)}")
    salvar("desembolso", des, gravar)

    titulo("siconv_prorroga_oficio  por NR_CONVENIO")
    pro = ler_filtrado(zips["prorroga_oficio"], "NR_CONVENIO", nrs)
    print(f"  prorrogações de ofício: {len(pro)}")
    distintos(pro, "SIT_PRORROGA")
    salvar("prorroga_oficio", pro, gravar)

    titulo(f"Recorte desde {inicio.date()} (spec: 'desde 01/01/2024'): contagens por critério de data")
    dp = data_iso(todas["DIA_PROPOSTA"])
    print(f"  propostas (incl. canceladas) com DIA_PROPOSTA >= recorte: {(dp >= inicio).sum()} de {len(todas)}")
    assin = data_iso(conv["DIA_ASSIN_CONV"])
    fim = data_iso(conv["DIA_FIM_VIGENC_CONV"])
    print(f"  convênios com DIA_ASSIN_CONV >= recorte: {(assin >= inicio).sum()} de {len(conv)}")
    print(f"  convênios com vigência terminando >= recorte (ainda vivos ou vencidos depois): {(fim >= inicio).sum()}")
    antigos_vivos = conv[(assin < inicio) & (fim >= inicio)]
    print(f"  assinados antes do recorte mas com vigência dentro dele: {len(antigos_vivos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
