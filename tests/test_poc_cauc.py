import importlib.util
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("poc_cauc", RAIZ / "scripts" / "poc_cauc.py")
poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc)

FIXTURE = RAIZ / "tests" / "fixtures" / "cauc" / "municipios_amostra.csv"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("!", (poc.SEM_COMPROVACAO, None)),
        ("Desabilitado", (poc.DESABILITADO, None)),
        ("", (poc.SEM_DADO, None)),
        ("30/04/27", (poc.REGULAR_ATE, date(2027, 4, 30))),
        ("29/10/26", (poc.REGULAR_ATE, date(2026, 10, 29))),
    ],
)
def test_classificar_celula(valor, esperado):
    assert poc.classificar_celula(valor) == esperado


@pytest.mark.parametrize("valor", ["Regular", "2026-10-29", "31/02/27", "?"])
def test_classificar_celula_desconhecida_levanta_erro(valor):
    with pytest.raises(ValueError, match="não reconhecido"):
        poc.classificar_celula(valor)


def test_escolher_recurso_pelo_nome_e_formato():
    pacote = {
        "resources": [
            {"name": "Metadados CAUC Municípios", "format": "PDF"},
            {"name": poc.NOME_RECURSO, "format": "CSV", "url": "https://exemplo/m.csv"},
            {"name": "Relatório da situação dos estados e do DF no CAUC", "format": "CSV"},
        ]
    }
    assert poc.escolher_recurso(pacote)["url"] == "https://exemplo/m.csv"
    with pytest.raises(LookupError):
        poc.escolher_recurso({"resources": []})


def test_ler_cauc_da_amostra_real_separa_dados_e_legenda():
    meta, cabecalho, entes, legenda = poc.ler_cauc(FIXTURE.read_bytes())
    assert meta["data_pesquisa"] == date(2026, 10, 29)
    assert meta["tipo_ente"] == "Municípios"
    assert cabecalho[:3] == ["UF", "Nome do Ente Federado", "Código IBGE"]
    assert len(cabecalho) == 35
    assert all(len(e) == 35 for e in entes)
    assert "3532504" in {e[2] for e in entes}
    assert legenda["4.2"] == "Regularidade Previdenciária"
    assert legenda["II"].startswith("Adimplemento na Prestação de Contas")  # grupos em romanos fazem parte da legenda
    assert legenda["5.8"].startswith("Regularidade na destinação mínima")  # item da legenda sem coluna


def test_amostra_do_municipio_tem_item_42_sem_comprovacao_e_nenhuma_data_vencida():
    meta, cabecalho, entes, _ = poc.ler_cauc(FIXTURE.read_bytes())
    idx = {c: i for i, c in enumerate(cabecalho)}
    linha = next(e for e in entes if e[idx["Código IBGE"]] == "3532504")
    assert poc.classificar_celula(linha[idx["4.2"]]) == (poc.SEM_COMPROVACAO, None)
    assert poc.classificar_celula(linha[idx["1.3"]])[0] == poc.DESABILITADO
    itens = [c for c in cabecalho if poc.COLUNA_ITEM.fullmatch(c)]
    datas = [d for i in itens for t, d in [poc.classificar_celula(linha[idx[i]])] if t == poc.REGULAR_ATE]
    assert datas and min(datas) >= meta["data_pesquisa"]


def test_ler_cauc_linha_curta_fora_da_legenda_e_erro():
    texto = (
        '"Data da Pesquisa: 29/10/2026"\n"Tipo de Ente: Municípios"\n"Abrangência: CNPJ principal dos Entes Federados"\n'
        '"UF";"Nome do Ente Federado";"Código IBGE";"1.1"\n'
        '"SP";"A";"1";"!"\n'
        '"SP";"B"\n'
        '"SP";"C";"3";"!"\n'
    )
    with pytest.raises(ValueError, match="fora da legenda"):
        poc.ler_cauc(texto.encode("cp1252"))
