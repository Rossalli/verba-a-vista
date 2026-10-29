import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from coleta import portal_transparencia as portal
from coleta.base import AcessoNegadoErro, ColetaErro, Http
from nucleo.config import carregar_config

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "portal_transparencia"
DIA = date(2026, 10, 29)
CHAVE = "chave-de-teste-nao-e-real"


def amostra(nome):
    return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))["amostra"]


@pytest.fixture
def config():
    return carregar_config()


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv(portal.VARIAVEL_CHAVE, CHAVE)


def http_falso(**kw):
    return Http(tentativas=1, backoff_inicial_s=0, dormir=lambda _s: None, parar_em=frozenset({401, 403, 429}), **kw)


def mockar(config, *, convenios=None, recursos=None, documentos=None):
    base = config.fontes.fontes["portal_transparencia"].base_url
    todos_convenios = convenios if convenios is not None else amostra("convenios__codigoIBGE")
    todos_recursos = recursos if recursos is not None else amostra("recursos_recebidos__codigoFavorecido")
    todos_documentos = documentos if documentos is not None else sum((amostra(f"documentos_pagamento__{c}") for c in ("13921776000196", "14513724000143", "45145414000147")), [])
    chamadas = []

    def pagina(linhas, n):  # 15 por página, como a API
        return httpx.Response(200, json=linhas[(n - 1) * 15 : n * 15])

    def tratar(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.split("/api-de-dados/")[-1]
        p = dict(request.url.params)
        chamadas.append((endpoint, p, request.headers.get("chave-api-dados")))
        n = int(p["pagina"])
        if endpoint == "convenios":
            return pagina(todos_convenios, n)
        if endpoint == "despesas/recursos-recebidos":
            cnpj = p["codigoFavorecido"]
            ano = int(p["mesAnoInicio"][-4:])
            return pagina([r for r in todos_recursos if r["codigoPessoa"].replace(".", "").replace("/", "").replace("-", "") == cnpj and r["anoMes"] // 100 == ano], n)
        if endpoint == "despesas/documentos-por-favorecido":
            cnpj, ano = p["codigoPessoa"], p["ano"]
            return pagina([d for d in todos_documentos if d["codigoFavorecido"].replace(".", "").replace("/", "").replace("-", "") == cnpj and d["data"].endswith(ano)], n)
        return httpx.Response(404)

    respx.get(url__startswith=base).mock(side_effect=tratar)
    return chamadas


@respx.mock
def test_coleta_convenios_recursos_e_pagamentos(config, com_chave):
    mockar(config)
    retrato = portal.coletar(DIA, config=config, http=http_falso())
    assert retrato.fonte == "portal_transparencia"
    assert retrato.metadados["cnpjs"] == ["45145414000147", "13921776000196", "14513724000143"]
    assert retrato.metadados["janelas_recursos_recebidos"] == [["01/2024", "12/2024"], ["01/2025", "12/2025"], ["01/2026", "10/2026"]]
    c = retrato.contagens()
    assert c["convenios"] == 50  # a amostra tem 50 dos 63 convênios reais (a API pagina até acabar)
    assert c["recursos_recebidos"] == len(amostra("recursos_recebidos__codigoFavorecido")) == 50
    assert c["documentos_pagamento"] == 10  # 5 + 2 + 3 pagamentos, como na POC


@respx.mock
def test_recursos_recebidos_vai_por_cnpj_nunca_por_codigo_ibge_e_em_janelas_de_12_meses(config, com_chave):
    chamadas = mockar(config)
    portal.coletar(DIA, config=config, http=http_falso())
    recursos = [p for e, p, _ in chamadas if e == "despesas/recursos-recebidos"]
    assert all("codigoIBGE" not in p for p in recursos)  # esse filtro devolve vazio (T1.4)
    assert {p["codigoFavorecido"] for p in recursos} == {"45145414000147", "13921776000196", "14513724000143"}
    assert {(p["mesAnoInicio"], p["mesAnoFim"]) for p in recursos} == {("01/2024", "12/2024"), ("01/2025", "12/2025"), ("01/2026", "10/2026")}
    convenios = [p for e, p, _ in chamadas if e == "convenios"]
    assert all(p["codigoIBGE"] == "3532504" for p in convenios) and [p["pagina"] for p in convenios] == ["1", "2", "3", "4", "5"]  # 50 itens: 15+15+15+5; a página 5, vazia, é o sinal de parada
    documentos = [p for e, p, _ in chamadas if e == "despesas/documentos-por-favorecido"]
    assert {p["fase"] for p in documentos} == {"3"} and {p["ano"] for p in documentos} == {"2024", "2025", "2026"}


@respx.mock
def test_envia_a_chave_no_header_em_toda_requisicao(config, com_chave):
    chamadas = mockar(config)
    http = portal.criar_http(config)
    http.dormir = lambda _s: None  # o intervalo real (0,2 s) não precisa passar no teste
    portal.coletar(DIA, config=config, http=http)
    assert chamadas and {chave for _, _, chave in chamadas} == {CHAVE}


@respx.mock
def test_nunca_envia_parametro_fora_da_lista(config, com_chave):
    chamadas = mockar(config)
    portal.coletar(DIA, config=config, http=http_falso())
    for endpoint, params, _ in chamadas:
        assert set(params) <= portal.PARAMETROS[endpoint]


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 429])
def test_para_na_hora_em_401_403_429_sem_repetir_e_sem_vazar_a_chave(config, com_chave, status):
    base = config.fontes.fontes["portal_transparencia"].base_url
    rota = respx.get(f"{base}/convenios").mock(return_value=httpx.Response(status, text="negado"))
    http = portal.criar_http(config)
    http.dormir = lambda _s: None
    with pytest.raises(AcessoNegadoErro) as e:
        portal.coletar(DIA, config=config, http=http)
    assert rota.call_count == 1 and str(status) in str(e.value) and CHAVE not in str(e.value)


def test_sem_a_chave_na_variavel_de_ambiente_a_fonte_falha_com_mensagem_clara(config, monkeypatch):
    monkeypatch.delenv(portal.VARIAVEL_CHAVE, raising=False)
    with pytest.raises(ColetaErro, match="PORTAL_TRANSPARENCIA_KEY não definida"):
        portal.criar_http(config)


def test_http_do_portal_respeita_o_limite_e_o_teto(config, com_chave):
    http = portal.criar_http(config)
    assert http.intervalo_minimo_s == pytest.approx(60 / 300)  # regras.yaml: 300/min, abaixo dos 400/min da API
    assert http.max_requisicoes == 400 and http.parar_em == frozenset({401, 403, 429})
    config.regras.coleta.portal_transparencia_req_por_min = 400
    config.fontes.fontes["portal_transparencia"].limite_req_min = 200
    assert portal.criar_http(config).intervalo_minimo_s == pytest.approx(60 / 200)  # nunca acima do limite da fonte


@respx.mock
def test_convenio_de_outro_ibge_e_erro(config, com_chave):
    intruso = json.loads(json.dumps(amostra("convenios__codigoIBGE")[0]))
    intruso["municipioConvenente"]["codigoIBGE"] = "3550308"
    mockar(config, convenios=[intruso])
    with pytest.raises(ColetaErro, match="convênios de outro IBGE"):
        portal.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_mais_de_40_paginas_e_erro(config, com_chave, monkeypatch):
    monkeypatch.setattr(portal, "MAX_PAGINAS", 2)
    base = config.fontes.fontes["portal_transparencia"].base_url
    respx.get(f"{base}/convenios").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    with pytest.raises(ColetaErro, match="mais de 2 páginas"):
        portal.coletar(DIA, config=config, http=http_falso())


def test_janelas_de_um_ano():
    assert portal.janelas_de_um_ano(date(2024, 1, 1), date(2026, 10, 29)) == [("01/2024", "12/2024"), ("01/2025", "12/2025"), ("01/2026", "10/2026")]
    assert portal.janelas_de_um_ano(date(2024, 1, 1), date(2024, 1, 31)) == [("01/2024", "01/2024")]
    assert all(int(f[:2]) - int(i[:2]) + 1 <= 12 for i, f in portal.janelas_de_um_ano(date(2024, 1, 1), date(2027, 3, 1)))
