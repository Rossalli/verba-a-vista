import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from coleta import transferegov_api as t
from coleta.base import ColetaErro, Http
from nucleo.config import carregar_config

RAIZ = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DIA = date(2026, 10, 29)


def amostra(nome):
    return json.loads((RAIZ / "transferegov_api" / f"{nome}.json").read_text(encoding="utf-8"))["amostra"]


@pytest.fixture
def config():
    return carregar_config()


def http_falso():
    return Http(tentativas=1, backoff_inicial_s=0, dormir=lambda _s: None)


def base_de_dados(extra=None):
    """Tabelas simuladas a partir das amostras reais do Marco 1; `extra` troca ou acrescenta tabelas."""
    tabelas = {
        ("parcerias", "proposta"): amostra("parcerias__proposta"),
        ("parcerias", "parceria"): amostra("parcerias__parceria"),
        ("parcerias", "programa"): [{"id_programa": i, "nm_programa": f"Programa {i}"} for i in range(1, 400)],
        ("parcerias", "beneficiario_emenda_parlamentar"): json.loads((RAIZ / "oportunidades" / "parcerias_emendas_indicadas.json").read_text(encoding="utf-8")),
        ("fundoafundo", "planos-acao"): amostra("fundoafundo__planos-acao"),
        ("fundoafundo", "termos-adesao"): amostra("fundoafundo__termos-adesao"),
        ("fundoafundo", "programas-beneficiarios"): amostra("fundoafundo__programas-beneficiarios"),
        ("fundoafundo", "programas"): [{"id_programa": i, "nome_programa": f"FaF {i}"} for i in range(1, 400)],
        ("especiais", "beneficiarios-especiais"): [],
        ("especiais", "planos-acao-especiais"): [],
        ("especiais", "planos-trabalho-especiais"): [],
    }
    tabelas.update(extra or {})
    return tabelas


def mockar(config, tabelas):
    base = config.fontes.fontes["transferegov_api"].base_url
    chamadas = []

    def tratar(request: httpx.Request) -> httpx.Response:
        modulo, endpoint = request.url.path.split("/")[-2:]
        p = dict(request.url.params)
        chamadas.append((modulo, endpoint, p))
        if endpoint == "data-atualizacao":
            return httpx.Response(200, json={"data_ultima_atualizacao": "2026-10-29T00:00:00"})
        filtros = {k: v for k, v in p.items() if k not in t._PAG}
        linhas = [r for r in tabelas[(modulo, endpoint)] if all(str(r.get(k)) == v for k, v in filtros.items())]
        tamanho, n = int(p["tamanho_da_pagina"]), int(p["pagina"])
        return httpx.Response(200, json={"data": linhas[(n - 1) * tamanho : n * tamanho], "total_pages": max(1, -(-len(linhas) // tamanho)), "total_items": len(linhas)})

    respx.get(url__startswith=base).mock(side_effect=tratar)
    return chamadas


@respx.mock
def test_coleta_os_tres_modulos_para_o_municipio(config):
    mockar(config, base_de_dados())
    retrato = t.coletar(DIA, config=config, http=http_falso())
    c = retrato.contagens()
    assert retrato.fonte == "transferegov_api"
    assert c["parcerias.proposta"] == 12 and c["parcerias.parceria"] == 12
    assert c["parcerias.beneficiario_emenda_parlamentar"] == 14
    assert c["fundoafundo.planos_acao"] == 2 and c["fundoafundo.termos_adesao"] == 2 and c["fundoafundo.programas_beneficiarios"] == 6
    assert c["especiais.beneficiarios"] == 0 and c["especiais.planos_acao"] == 0 and c["especiais.planos_trabalho"] == 0
    assert retrato.metadados["cnpjs_consultados"] == ["45145414000147", "13921776000196", "14513724000143"]
    assert set(retrato.metadados["data_atualizacao"]) == {"parcerias", "fundoafundo", "especiais"}


@respx.mock
def test_programas_vem_so_dos_ids_referenciados(config):
    mockar(config, base_de_dados())
    retrato = t.coletar(DIA, config=config, http=http_falso())
    ids_propostas = {p["id_programa"] for p in retrato.dados["parcerias.proposta"]}
    assert {p["id_programa"] for p in retrato.dados["parcerias.programa"]} == ids_propostas
    ids_faf = {r["id_programa"] for r in [*retrato.dados["fundoafundo.planos_acao"], *retrato.dados["fundoafundo.programas_beneficiarios"]]}
    assert {p["id_programa"] for p in retrato.dados["fundoafundo.programas"]} == ids_faf


@respx.mock
def test_fundoafundo_filtra_por_cnpj_e_nunca_por_codigo_ibge(config):
    chamadas = mockar(config, base_de_dados())
    t.coletar(DIA, config=config, http=http_falso())
    planos = [p for m, e, p in chamadas if (m, e) == ("fundoafundo", "planos-acao")]
    assert {p["cnpj_ente_recebedor_plano_acao"] for p in planos} == {"45145414000147", "13921776000196", "14513724000143"}
    assert all("codigo_ibge_municipio_ente_recebedor_plano_acao" not in p for p in planos)  # essa dá HTTP 500 na API
    proposta = [p for m, e, p in chamadas if (m, e) == ("parcerias", "proposta")]
    assert proposta[0]["cd_ibge_recebedor"] == "3532504"


@respx.mock
def test_nunca_envia_parametro_fora_da_lista(config):
    chamadas = mockar(config, base_de_dados())
    t.coletar(DIA, config=config, http=http_falso())
    for modulo, endpoint, params in chamadas:
        assert set(params) <= t.PARAMETROS[(modulo, endpoint)], (modulo, endpoint, params)


@respx.mock
def test_remove_dados_bancarios_e_email_de_todos_os_recursos(config):
    benef = [{"id_beneficiario": 1, "cnpj_beneficiario": "45145414000147", "nome_beneficiario": "MUNICIPIO DE NEVES PAULISTA"}]
    plano = [{"id_plano_acao": 9, "id_beneficiario": 1, "numero_conta_plano_acao": "123", "numero_agencia_plano_acao": "45", "dv_conta_plano_acao": "6", "email_camara": "a@b.gov.br", "nome_banco_plano_acao": "BB", "motivo_impedimento_plano_acao": None}]
    trabalho = [{"id_plano_trabalho": 5, "id_plano_acao": 9, "situacao_plano_trabalho": "APROVADO"}]
    mockar(config, base_de_dados({("especiais", "beneficiarios-especiais"): benef, ("especiais", "planos-acao-especiais"): plano, ("especiais", "planos-trabalho-especiais"): trabalho}))
    retrato = t.coletar(DIA, config=config, http=http_falso())
    assert retrato.dados["especiais.planos_acao"] == [{"id_plano_acao": 9, "id_beneficiario": 1, "nome_banco_plano_acao": "BB", "motivo_impedimento_plano_acao": None}]
    assert retrato.dados["especiais.planos_trabalho"] == trabalho
    texto = json.dumps(retrato.dados, ensure_ascii=False)
    assert "numero_conta" not in texto and "email" not in texto and "a@b.gov.br" not in texto


@respx.mock
def test_proposta_de_outro_ibge_e_erro(config):
    intruso = {**amostra("parcerias__proposta")[0], "cd_ibge_recebedor": 3550308}
    # a API "devolve" a linha mesmo com o filtro: o coletor confere e recusa
    base = config.fontes.fontes["transferegov_api"].base_url
    respx.get(f"{base}/parcerias/data-atualizacao").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{base}/fundoafundo/data-atualizacao").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{base}/especiais/data-atualizacao").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{base}/parcerias/proposta").mock(return_value=httpx.Response(200, json={"data": [intruso], "total_pages": 1, "total_items": 1}))
    with pytest.raises(ColetaErro, match="propostas de outro IBGE"):
        t.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_plano_do_fundoafundo_de_outro_ibge_e_erro(config):
    planos = [{**amostra("fundoafundo__planos-acao")[0], "codigo_ibge_municipio_ente_recebedor_plano_acao": 3550308}]
    mockar(config, base_de_dados({("fundoafundo", "planos-acao"): planos}))
    with pytest.raises(ColetaErro, match="planos de outro IBGE"):
        t.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_pagina_ate_o_fim(config, monkeypatch):
    monkeypatch.setattr(t, "PAGINA", 5)
    chamadas = mockar(config, base_de_dados())
    retrato = t.coletar(DIA, config=config, http=http_falso())
    assert retrato.contagens()["parcerias.proposta"] == 12
    paginas = [p["pagina"] for m, e, p in chamadas if (m, e) == ("parcerias", "proposta")]
    assert paginas == ["1", "2", "3"]


def test_limpar_so_tira_campos_sensiveis():
    assert t.limpar({"a": 1, "numero_agencia_x": 2, "dv_agencia_y": 3, "nome_agencia_z": 4, "email_camara": "x", "nome_banco": "BB"}) == {"a": 1, "nome_banco": "BB"}
