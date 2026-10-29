import importlib.util
import json
from decimal import InvalidOperation
from pathlib import Path

import httpx
import pytest
import respx

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("poc_portal", RAIZ / "scripts" / "poc_portal_transparencia.py")
poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc)

FIXTURES = RAIZ / "tests" / "fixtures" / "portal_transparencia"
CHAVE_FALSA = "chave-de-teste-nao-e-real"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("650.000,00", 65000000),
        ("1.234,56", 123456),
        ("0,29", 29),
        ("0,00", 0),
        ("- 7.174,10", -717410),  # estorno: sinal e espaço
        ("-7.174,10", -717410),
        ("", None),
        (None, None),
    ],
)
def test_centavos(texto, esperado):
    assert poc.centavos(texto) == esperado


@pytest.mark.parametrize("texto", ["R$ 10,00", "abc", "1,2,3"])
def test_centavos_formato_desconhecido_levanta_erro(texto):
    with pytest.raises(InvalidOperation):
        poc.centavos(texto)


@pytest.mark.parametrize(
    ("numero", "esperado"),
    [("04431/2016", "4431/2016"), ("4431/2016", "4431/2016"), ("00361/2011", "361/2011"), ("33961/2024", "33961/2024"), ("1586/1999", "1586/1999")],
)
def test_normalizar_numero_ignora_zeros_a_esquerda(numero, esperado):
    assert poc.normalizar_numero(numero) == esperado


def test_ler_chave_prefere_a_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_KEY", CHAVE_FALSA)
    assert poc.ler_chave() == CHAVE_FALSA


def test_ler_chave_sem_chave_levanta_erro_claro(monkeypatch, tmp_path):
    monkeypatch.delenv("PORTAL_TRANSPARENCIA_KEY", raising=False)
    monkeypatch.setattr(poc, "RAIZ", tmp_path)  # sem .env
    with pytest.raises(poc.PortalErro, match="PORTAL_TRANSPARENCIA_KEY"):
        poc.ler_chave()


OPENAPI = {"paths": {"/api-de-dados/convenios": {"get": {"parameters": [{"name": "codigoIBGE"}, {"name": "pagina"}]}}}}


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(poc.time, "sleep", lambda _s: None)
    c = poc.Cliente(CHAVE_FALSA, 300)
    c._params = {"convenios": {"codigoIBGE", "pagina"}}
    return c


@respx.mock
def test_get_envia_a_chave_no_header_e_valida_parametros(cliente):
    rota = respx.get(f"{poc.BASE}/convenios").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    assert cliente.get("convenios", codigoIBGE="3532504", pagina=1) == [{"id": 1}]
    assert rota.calls[0].request.headers["chave-api-dados"] == CHAVE_FALSA
    with pytest.raises(ValueError, match="codigoIBGEx"):
        cliente.get("convenios", codigoIBGEx="3532504", pagina=1)


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 429])
def test_get_para_na_hora_em_401_403_429_sem_repetir(cliente, status):
    rota = respx.get(f"{poc.BASE}/convenios").mock(return_value=httpx.Response(status, text="negado"))
    with pytest.raises(poc.PortalErro, match=str(status)):
        cliente.get("convenios", codigoIBGE="3532504", pagina=1)
    assert rota.call_count == 1  # nunca insiste: 429 pode suspender a chave por 8 h


@respx.mock
def test_todas_as_paginas_vai_ate_a_pagina_vazia(cliente):
    respx.get(f"{poc.BASE}/convenios").mock(
        side_effect=[httpx.Response(200, json=[{"id": 1}, {"id": 2}]), httpx.Response(200, json=[{"id": 3}]), httpx.Response(200, json=[])]
    )
    assert [i["id"] for i in cliente.todas_as_paginas("convenios", codigoIBGE="3532504")] == [1, 2, 3]


@respx.mock
def test_teto_de_requisicoes(cliente, monkeypatch):
    monkeypatch.setattr(poc, "MAX_REQUISICOES", 2)
    respx.get(f"{poc.BASE}/convenios").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    cliente.get("convenios", codigoIBGE="1", pagina=1)
    cliente.get("convenios", codigoIBGE="1", pagina=2)
    with pytest.raises(poc.PortalErro, match="teto"):
        cliente.get("convenios", codigoIBGE="1", pagina=3)


def test_intervalo_minimo_respeita_o_limite_configurado():
    assert poc.Cliente(CHAVE_FALSA, 300).intervalo == pytest.approx(0.2)
    assert poc.Cliente(CHAVE_FALSA, 400).intervalo == pytest.approx(0.15)


def test_amostras_nao_contem_a_chave_nem_dados_pessoais_de_cidadaos():
    for arquivo in FIXTURES.glob("*.json"):
        texto = arquivo.read_text(encoding="utf-8")
        assert "chave-api-dados" not in texto
        corpo = json.loads(texto)
        assert len(corpo["amostra"]) <= poc.MAX_AMOSTRA


def test_fixture_de_convenios_do_municipio_so_tem_o_codigo_ibge_pedido():
    corpo = json.loads((FIXTURES / "convenios__codigoIBGE.json").read_text(encoding="utf-8"))
    assert corpo["params"] == {"codigoIBGE": "3532504"}
    assert {i["municipioConvenente"]["codigoIBGE"] for i in corpo["amostra"]} == {"3532504"}


def test_fixture_de_emendas_mostra_que_a_emenda_vem_agregada():
    corpo = json.loads((FIXTURES / "emendas__codigoEmenda.json").read_text(encoding="utf-8"))
    assert corpo["amostra"] and {e["localidadeDoGasto"] for e in corpo["amostra"]} == {"MÚLTIPLO"}
    # valor da emenda inteira (R$ milhões), muito acima dos R$ 100 mil que o município recebe
    assert max(poc.centavos(e["valorEmpenhado"]) for e in corpo["amostra"]) > 100_000_000
