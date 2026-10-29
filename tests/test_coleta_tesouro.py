import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from coleta import tesouro
from coleta.base import ColetaErro, Http
from nucleo.config import carregar_config

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tesouro"
DIA = date(2026, 10, 29)


def ler(nome):
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


LINHAS = ler("por_estado_municipio.json")["amostra"]


@pytest.fixture
def config():
    return carregar_config()


def http_falso():
    return Http(tentativas=1, backoff_inicial_s=0, dormir=lambda _s: None)


def mockar(config, *, linhas=LINHAS, municipios=None, detalhes=None):
    """Simula a API com as amostras reais; pagina `por_estado_municipio` como a API (page/pageSize)."""
    base = config.fontes.fontes["tesouro_constitucionais"].base_url
    chamadas = []

    def tratar(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        p = dict(request.url.params)
        chamadas.append((endpoint, p))
        if endpoint == "transferencias":
            corpo = ler("transferencias.json")
        elif endpoint == "estados":
            corpo = ler("estados.json")
        elif endpoint == "municipios":
            corpo = municipios if municipios is not None else ler("municipios_neves_paulista.json")
        elif endpoint == "por_estado_municipio":
            do_ano = [r for r in linhas if r["ANO"] == p["p_ano"]]
            pagina, tamanho = int(p["page"]), int(p["pageSize"])
            corpo = do_ano[(pagina - 1) * tamanho : pagina * tamanho]
        elif endpoint == "por_estado_municipio_detalhe":
            nome = {"3": "fpm", "4": "itr"}[p["P_TRANSFERENCIA"]]
            corpo = detalhes[nome] if detalhes else ler(f"detalhe_{nome}_2026_10.json")
        else:
            return httpx.Response(404)
        return httpx.Response(200, json={"registros": corpo, "status": "ok", "next": "sempre-preenchido"})

    respx.get(url__startswith=base).mock(side_effect=tratar)
    return chamadas


@respx.mock
def test_coleta_dicionarios_valores_e_detalhe_do_ultimo_mes(config):
    chamadas = mockar(config)
    retrato = tesouro.coletar(DIA, config=config, http=http_falso())
    assert retrato.fonte == "tesouro_constitucionais"
    assert retrato.metadados == {"codigo_tesouro": 6751, "codigo_uf": 26, "estado": "São Paulo", "anos": [2024, 2025, 2026], "ultimo_mes_fpm": "2026-10"}
    assert len(retrato.dados["por_estado_municipio"]) == len(LINHAS)
    assert {r["TRANSFERENCIA"] for r in retrato.dados["por_estado_municipio"]} >= {"FPM", "ITR"}
    assert len(retrato.dados["transferencias"]) == 18
    assert sorted(d["SG_DETALHE"] for d in retrato.dados["detalhe"]) == ["FPM", "ITR"]
    # 3º decêndio zerado: o mês corrente está em andamento e isso fica guardado no retrato
    assert {d["VA_TERCEIRO_DEC"] for d in retrato.dados["detalhe"]} == {0}
    # uma consulta de valores por ano do recorte, com os códigos do Tesouro (não o IBGE)
    valores = [p for e, p in chamadas if e == "por_estado_municipio"]
    assert [p["p_ano"] for p in valores] == ["2024", "2025", "2026"] and {p["p_municipio"] for p in valores} == {"6751"}
    assert {p["p_estado"] for p in valores} == {"26"}


@respx.mock
def test_detalhe_usa_os_nomes_em_maiusculas_e_o_mes_mais_recente(config):
    chamadas = mockar(config)
    tesouro.coletar(DIA, config=config, http=http_falso())
    detalhes = [p for e, p in chamadas if e == "por_estado_municipio_detalhe"]
    assert detalhes == [
        {"P_ESTADO": "26", "P_MUNICIPIOS": "6751", "P_ANO": "2026", "P_MES": "10", "P_TRANSFERENCIA": "3"},
        {"P_ESTADO": "26", "P_MUNICIPIOS": "6751", "P_ANO": "2026", "P_MES": "10", "P_TRANSFERENCIA": "4"},
    ]


@respx.mock
def test_pagina_ate_a_pagina_incompleta_mesmo_com_next_sempre_preenchido(config, monkeypatch):
    monkeypatch.setattr(tesouro, "PAGINA", 5)
    chamadas = mockar(config)
    retrato = tesouro.coletar(DIA, config=config, http=http_falso())
    assert len(retrato.dados["por_estado_municipio"]) == len(LINHAS)
    paginas_2026 = [p["page"] for e, p in chamadas if e == "por_estado_municipio" and p["p_ano"] == "2026"]
    assert paginas_2026 == [str(i) for i in range(1, len(paginas_2026) + 1)] and len(paginas_2026) > 1


@respx.mock
def test_linha_de_outro_municipio_e_erro(config):
    intruso = {**LINHAS[0], "CO_IBGE": 1200013, "codigo_siafi": 643}
    mockar(config, linhas=[intruso, *LINHAS])
    with pytest.raises(ColetaErro, match="não são do município"):
        tesouro.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_municipio_nao_encontrado_ou_ambiguo_e_erro(config):
    mockar(config, municipios=[])
    with pytest.raises(ColetaErro, match="achei 0"):
        tesouro.coletar(DIA, config=config, http=http_falso())
    respx.reset()
    ambiguo = [{"codigo": 1, "codigo_uf": 26, "nome": "Neves Paulista"}, {"codigo": 2, "codigo_uf": 11, "nome": "Neves Paulista"}]
    mockar(config, municipios=ambiguo)
    with pytest.raises(ColetaErro, match="achei 2"):
        tesouro.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_status_de_erro_no_corpo_e_erro_mesmo_com_http_200(config):
    base = config.fontes.fontes["tesouro_constitucionais"].base_url
    respx.get(f"{base}/transferencias").mock(return_value=httpx.Response(200, json={"status": "erro", "errorMessage": "Endpoint não encontrado"}))
    with pytest.raises(ColetaErro, match="status 'erro'"):
        tesouro.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_sem_nenhuma_transferencia_e_erro(config):
    mockar(config, linhas=[])
    with pytest.raises(ColetaErro, match="nenhuma transferência"):
        tesouro.coletar(DIA, config=config, http=http_falso())


def test_caixa_dos_parametros_e_validada_antes_de_chamar():
    http = http_falso()
    with pytest.raises(ValueError, match="P_ESTADO"):
        tesouro._chamar(http, "https://x", "por_estado_municipio", P_ESTADO=26)  # este usa minúsculas
    with pytest.raises(ValueError, match="p_estado"):
        tesouro._chamar(http, "https://x", "por_estado_municipio_detalhe", p_estado=26)  # este usa MAIÚSCULAS
    assert http.requisicoes == 0
