import importlib.util
from pathlib import Path

import httpx
import pytest
import respx

_spec = importlib.util.spec_from_file_location(
    "poc_transferegov_api", Path(__file__).resolve().parents[1] / "scripts" / "poc_transferegov_api.py"
)
poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc)

OPENAPI = {"paths": {"/proposta": {"get": {"parameters": [{"name": "cd_ibge_recebedor"}, {"name": "pagina"}, {"name": "tamanho_da_pagina"}]}}}}


@respx.mock
def test_validar_rejeita_parametro_fora_do_openapi():
    respx.get(f"{poc.BASE}/parcerias/openapi.json").mock(return_value=httpx.Response(200, json=OPENAPI))
    c = poc.Cliente()
    c.validar("parcerias", "proposta", {"cd_ibge_recebedor": 3532504})
    with pytest.raises(ValueError, match="cd_ibge_recebedorx"):
        c.validar("parcerias", "proposta", {"cd_ibge_recebedorx": 3532504})


@respx.mock
def test_todos_pagina_ate_o_fim(monkeypatch):
    monkeypatch.setattr(poc, "PAUSA_S", 0)
    respx.get(f"{poc.BASE}/parcerias/openapi.json").mock(return_value=httpx.Response(200, json=OPENAPI))
    rota = respx.get(f"{poc.BASE}/parcerias/proposta").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"id": 1}], "total_pages": 2, "total_items": 2}),
            httpx.Response(200, json={"data": [{"id": 2}], "total_pages": 2, "total_items": 2}),
        ]
    )
    registros, total = poc.Cliente().todos("parcerias", "proposta", {"cd_ibge_recebedor": 3532504})
    assert [r["id"] for r in registros] == [1, 2] and total == 2
    assert rota.calls[0].request.url.params["tamanho_da_pagina"] == "200"
    assert rota.calls[1].request.url.params["pagina"] == "2"


@respx.mock
def test_get_repete_em_erro_5xx_e_desiste_depois_de_quatro(monkeypatch):
    monkeypatch.setattr(poc, "PAUSA_S", 0)
    monkeypatch.setattr(poc.time, "sleep", lambda _s: None)
    rota = respx.get(f"{poc.BASE}/x").mock(return_value=httpx.Response(500, json={"detail": "erro"}))
    with pytest.raises(httpx.HTTPStatusError):
        poc.Cliente()._get(f"{poc.BASE}/x", {})
    assert rota.call_count == 4


def test_limpar_remove_dados_bancarios_e_email():
    registro = {"id": 1, "numero_conta_plano_acao": "123", "email_camara": "a@b", "nome_banco_plano_acao": "BB", "numero_agencia_x": "1"}
    assert poc.limpar(registro) == {"id": 1, "nome_banco_plano_acao": "BB"}


def test_eh_prefeitura():
    assert poc.eh_prefeitura("MUNICIPIO DE NEVES PAULISTA", "Neves Paulista")
    assert not poc.eh_prefeitura("FUNDO MUNICIPAL DE SAUDE DE NEVES PAULISTA", "Neves Paulista")
    assert not poc.eh_prefeitura(None, "Neves Paulista")
