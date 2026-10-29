import importlib.util
import zipfile
from pathlib import Path

import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "poc_discricionarias", Path(__file__).resolve().parents[1] / "scripts" / "poc_transferegov_discricionarias.py"
)
poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc)

CSV = "﻿ID_PROPOSTA;COD_MUNIC_IBGE;VL\n1;3532504;1134,75\n2;3505401;10\n3;3532504;\n"


def zip_de(tmp_path: Path, conteudo: str = CSV) -> Path:
    caminho = tmp_path / "siconv_x.csv.zip"
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr("siconv_x.csv", conteudo.encode("utf-8"))
    return caminho


def test_ler_filtrado_filtra_por_coluna_e_preserva_texto(tmp_path, monkeypatch):
    monkeypatch.setattr(poc, "BLOCO", 2)  # força mais de um bloco
    df = poc.ler_filtrado(zip_de(tmp_path), "COD_MUNIC_IBGE", {"3532504"})
    assert list(df["ID_PROPOSTA"]) == ["1", "3"]
    assert list(df["VL"]) == ["1134,75", ""]  # sem converter número nem virar NaN
    assert "ID_PROPOSTA" in df.columns  # BOM removido do cabeçalho


def test_ler_filtrado_sem_correspondencia_devolve_vazio(tmp_path):
    assert len(poc.ler_filtrado(zip_de(tmp_path), "COD_MUNIC_IBGE", {"0000000"})) == 0


def test_data_iso_aceita_os_dois_formatos_e_vazio():
    datas = poc.data_iso(pd.Series(["31/12/2019", "2024-05-13", ""]))
    assert datas.iloc[0] == pd.Timestamp("2019-12-31")
    assert datas.iloc[1] == pd.Timestamp("2024-05-13")
    assert pd.isna(datas.iloc[2])


def test_priorizar_poe_os_prioritarios_primeiro_sem_perder_a_ordem():
    df = pd.DataFrame({"ID": ["a", "b", "c", "d"]})
    assert list(poc.priorizar(df, "ID", {"c", "d"})["ID"]) == ["c", "d", "a", "b"]
    assert list(poc.priorizar(df, "ID", set())["ID"]) == ["a", "b", "c", "d"]


def test_salvar_grava_no_maximo_50_linhas(tmp_path, monkeypatch):
    monkeypatch.setattr(poc, "FIXTURES", tmp_path)
    poc.salvar("t", pd.DataFrame({"A": [str(i) for i in range(80)]}), gravar=True)
    saida = pd.read_csv(tmp_path / "t.csv", sep=";", dtype=str, encoding="utf-8-sig")
    assert len(saida) == poc.MAX_AMOSTRA
