import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("poc_oportunidades", RAIZ / "scripts" / "poc_oportunidades.py")
poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc)

FIXTURES = RAIZ / "tests" / "fixtures" / "oportunidades"
HOJE = date(2026, 10, 29)


@pytest.mark.parametrize(
    ("inicio", "fim", "esperado"),
    [
        ("01/01/2026", "31/12/2026", True),
        ("29/10/2026", "29/10/2026", True),  # extremos contam
        ("30/10/2026", "31/12/2026", False),  # ainda não abriu
        ("01/01/2026", "28/10/2026", False),  # já fechou
        ("", "31/12/2026", True),  # sem início: vale até o fim
        ("01/01/2026", "", False),  # sem fim: não conta como aberta
        ("", "", False),
    ],
)
def test_janela_aberta(inicio, fim, esperado):
    assert poc.janela_aberta(inicio, fim, HOJE) is esperado


def test_mascara_vetorizada_igual_a_regra_escalar():
    df = pd.DataFrame(
        {
            "DT_PROG_INI_RECEB_PROP": ["01/01/2026", "29/10/2026", "30/10/2026", "01/01/2026", "", "01/01/2026"],
            "DT_PROG_FIM_RECEB_PROP": ["31/12/2026", "29/10/2026", "31/12/2026", "28/10/2026", "31/12/2026", ""],
        }
    )
    esperado = [poc.janela_aberta(i, f, HOJE) for i, f in zip(df.iloc[:, 0], df.iloc[:, 1])]
    assert list(poc.mascara_aberta(df, "RECEB_PROP", HOJE)) == esperado == [True, True, False, False, True, False]
    assert len(poc.abertos(df, "RECEB_PROP", HOJE)) == 3


def test_elegiveis_filtra_natureza_municipal_uf_e_repeticoes():
    df = pd.DataFrame(
        {
            "ID_PROGRAMA": ["1", "1", "2", "3", "4", "5"],
            "NATUREZA_JURIDICA_PROGRAMA": [
                "Administração Pública Municipal",
                "Administração Pública Municipal",
                "Administração Pública Estadual ou do Distrito Federal",
                "Administração Pública Municipal",
                "Administração Pública Municipal",
                "Consórcio Público",
            ],
            "UF_PROGRAMA": ["SP", "SP", "SP", "MG", "", "SP"],
        }
    )
    resultado = poc.elegiveis(df, "SP")
    assert list(resultado["ID_PROGRAMA"]) == ["1", "4"]  # 1 sem repetir; 4 sem UF; 2 (estadual), 3 (MG) e 5 (consórcio) fora


def test_fixture_de_programas_elegiveis_so_tem_programas_municipais_de_sp():
    df = pd.read_csv(FIXTURES / "siconv_programas_elegiveis_abertos.csv", sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    assert len(df) > 0 and df["ID_PROGRAMA"].is_unique
    assert df["NATUREZA_JURIDICA_PROGRAMA"].str.contains("Municipal").all()
    assert set(df["UF_PROGRAMA"]) <= {"SP", ""}
    assert poc.mascara_aberta(df, "RECEB_PROP", HOJE).all()  # abertos em 29/10/2026, data da POC


def test_fixture_do_novo_pac_do_municipio_sem_justificativa():
    df = pd.read_csv(FIXTURES / "siconv_selecao_pac_municipio.csv", sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    assert len(df) == 10 and set(df["ID_PROPONENTE"]) == {"15310"}
    assert "JUSTIFICATIVA_PROPOSTA_SELECAO_PAC" not in df.columns  # texto longo livre não vai para a amostra
    assert set(df["SITUACAO_PROPOSTA_SELECAO_PAC"]) == {"SELECIONADA", "ENVIADA", "HABILITADA", "NAO_HABILITADA"}
