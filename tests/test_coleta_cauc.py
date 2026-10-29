import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from coleta import cauc
from coleta.base import ColetaErro, Http
from nucleo.config import carregar_config

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cauc"
CSV = FIXTURES / "municipios_amostra.csv"
RECURSO = json.loads((FIXTURES / "recurso.json").read_text(encoding="utf-8"))
DIA = date(2026, 10, 29)


@pytest.fixture
def config():
    return carregar_config()


def http_falso():
    return Http(tentativas=1, backoff_inicial_s=0, dormir=lambda _s: None)


def pacote(extra_recursos=()):
    return {
        "result": {
            "resources": [
                {"name": "Metadados CAUC Municípios", "format": "PDF", "url": "https://exemplo/meta.pdf"},
                {"name": cauc.NOME_RECURSO, "format": "CSV", "url": RECURSO["url"], "last_modified": RECURSO["last_modified"], "size": RECURSO["size"]},
                *extra_recursos,
            ]
        }
    }


def mockar(config, corpo_csv: bytes | None = None, pacote_json: dict | None = None):
    respx.get(config.fontes.fontes["cauc"].url).mock(return_value=httpx.Response(200, json=pacote_json or pacote()))
    respx.get(RECURSO["url"]).mock(
        return_value=httpx.Response(200, content=corpo_csv if corpo_csv is not None else CSV.read_bytes(), headers={"etag": '"abc"', "last-modified": "Thu, 29 Oct 2026 11:11:06 GMT"})
    )


@respx.mock
def test_coleta_so_a_linha_do_municipio_e_a_legenda(config):
    mockar(config)
    retrato = cauc.coletar(DIA, config=config, http=http_falso())
    assert retrato.fonte == "cauc" and retrato.data == DIA
    (linha,) = retrato.dados["entes"]
    assert linha["Nome do Ente Federado"] == "Neves Paulista" and linha["Código IBGE"] == "3532504" and linha["Código SIAFI"] == "6751"
    assert linha["4.2"] == "!" and linha["1.3"] == "Desabilitado" and linha["1.1"] == "30/03/27"
    legenda = {x["codigo"]: x["exigencia"] for x in retrato.dados["legenda"]}
    assert legenda["4.2"] == "Regularidade Previdenciária" and legenda["5.8"].startswith("Regularidade na destinação mínima")
    assert retrato.contagens() == {"entes": 1, "legenda": len(legenda)}


@respx.mock
def test_metadados_trazem_a_data_do_dado_e_a_origem_do_arquivo(config):
    mockar(config)
    meta = cauc.coletar(DIA, config=config, http=http_falso()).metadados
    assert meta["data_pesquisa"] == "2026-10-29" and meta["tipo_ente"] == "Municípios"
    assert meta["abrangencia"] == "CNPJ principal dos Entes Federados" and meta["entes_no_arquivo"] == 2
    assert meta["http"] == {"last_modified": "Thu, 29 Oct 2026 11:11:06 GMT", "etag": '"abc"'}
    assert meta["recurso"]["url"] == RECURSO["url"]


@respx.mock
def test_municipio_ausente_do_arquivo_e_erro(config):
    mockar(config)
    config.regras.municipio.codigo_ibge = "1200013"
    with pytest.raises(ColetaErro, match="esperava 1 linha para o IBGE 1200013, achei 0"):
        cauc.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_valor_novo_na_celula_e_erro_e_nao_e_interpretado(config):
    linhas = CSV.read_bytes().decode("cp1252").splitlines()
    alvo = next(i for i, linha in enumerate(linhas) if linha.startswith('"SP";"Neves Paulista"'))
    linhas[alvo] = linhas[alvo].replace('"!"', '"Regular"', 1)  # a célula `!` do item 4.2 vira um valor que o CAUC não define
    assert "Regular" in linhas[alvo]
    mockar(config, corpo_csv=("\n".join(linhas) + "\n").encode("cp1252"))
    with pytest.raises(ColetaErro, match="valor não reconhecido no item"):
        cauc.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_data_impossivel_na_celula_e_erro(config):
    ruim = CSV.read_bytes().replace(b'"30/03/27"', b'"31/02/27"', 1)
    mockar(config, corpo_csv=ruim)
    with pytest.raises(ColetaErro, match="data inválida no item 1.1"):
        cauc.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_arquivo_de_outro_tipo_de_ente_e_erro(config):
    estados = CSV.read_bytes().replace("Tipo de Ente: Municípios".encode("cp1252"), "Tipo de Ente: Estados e DF".encode("cp1252"))
    mockar(config, corpo_csv=estados)
    with pytest.raises(ColetaErro, match="esperava 'Municípios'"):
        cauc.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_recurso_do_municipio_ausente_ou_duplicado_e_erro(config):
    sem = {"result": {"resources": [{"name": "Metadados CAUC Municípios", "format": "PDF", "url": "x"}]}}
    mockar(config, pacote_json=sem)
    with pytest.raises(ColetaErro, match="achei 0"):
        cauc.coletar(DIA, config=config, http=http_falso())
    respx.reset()
    duplicado = pacote([{"name": cauc.NOME_RECURSO, "format": "CSV", "url": "https://exemplo/outro.csv"}])
    mockar(config, pacote_json=duplicado)
    with pytest.raises(ColetaErro, match="achei 2"):
        cauc.coletar(DIA, config=config, http=http_falso())


def test_linha_curta_fora_da_legenda_e_erro():
    texto = (
        '"Data da Pesquisa: 29/10/2026"\n"Tipo de Ente: Municípios"\n"Abrangência: CNPJ principal dos Entes Federados"\n'
        '"UF";"Nome do Ente Federado";"Código IBGE";"1.1"\n"SP";"A";"1";"!"\n"SP";"B"\n"SP";"C";"3";"!"\n'
    )
    with pytest.raises(ColetaErro, match="fora da legenda"):
        cauc.ler_cauc(texto.encode("cp1252"))


def test_cauc_esta_registrado_com_a_opcao_vazia_e_o_nome_da_config():
    assert cauc.FONTE == "cauc" and cauc.OPCOES == ()
