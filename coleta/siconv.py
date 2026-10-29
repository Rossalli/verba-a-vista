"""Leitura dos CSV em lote do Siconv (zips em repositorio.dados.gov.br/seges/detru). Ver docs/fontes.md.

Formato: um CSV por zip, separador `;`, UTF-8 com BOM, tudo lido como texto (vazio é texto vazio, nada vira
número nem NaN). As tabelas grandes (`proposta` 751 MB, `programa` 353 MB, `historico_situacao` 579 MB)
são lidas em blocos e filtradas na leitura: só as linhas do município ficam em memória.
"""

import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pandas as pd

BLOCO = 200_000


def blocos(caminho_zip: Path) -> Iterator[pd.DataFrame]:
    with zipfile.ZipFile(caminho_zip) as zf:
        (nome,) = zf.namelist()
        with zf.open(nome) as f:
            yield from pd.read_csv(f, sep=";", dtype=str, encoding="utf-8-sig", chunksize=BLOCO, keep_default_na=False)


def ler_filtrado(caminho_zip: Path, coluna: str, valores: set[str]) -> pd.DataFrame:
    """Linhas cuja `coluna` está em `valores`. Sem linhas, devolve um DataFrame vazio COM as colunas."""
    partes = [b[b[coluna].isin(valores)] for b in blocos(caminho_zip)]
    return pd.concat(partes) if partes else pd.DataFrame()


def ler_se(caminho_zip: Path, mascara: Callable[[pd.DataFrame], pd.Series]) -> pd.DataFrame:
    """Linhas em que `mascara(bloco)` é verdadeira (para filtros com mais de uma coluna)."""
    partes = [b[mascara(b)] for b in blocos(caminho_zip)]
    return pd.concat(partes) if partes else pd.DataFrame()


def registros(df: pd.DataFrame, colunas: list[str] | None = None) -> list[dict]:
    """DataFrame -> lista de dicts de texto (JSON-nativo), opcionalmente só com `colunas`."""
    if df.empty:
        return []
    return (df[colunas] if colunas else df).to_dict("records")
