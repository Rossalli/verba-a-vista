import importlib.util
import json
from pathlib import Path

import httpx
import pytest
import respx

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("poc_tesouro", RAIZ / "scripts" / "poc_tesouro.py")
poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc)

FIXTURES = RAIZ / "tests" / "fixtures" / "tesouro"


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(poc, "PAUSA_S", 0)
    monkeypatch.setattr(poc.time, "sleep", lambda _s: None)


def test_get_rejeita_parametro_com_caixa_errada():
    c = poc.Cliente()
    with pytest.raises(ValueError, match="P_ESTADO"):
        c.get("por_estado_municipio", P_ESTADO=26)  # este endpoint usa minúsculas
    with pytest.raises(ValueError, match="p_estado"):
        c.get("por_estado_municipio_detalhe", p_estado=26)  # este usa MAIÚSCULAS


@respx.mock
def test_get_aceita_nomes_corretos_e_exige_status_ok():
    respx.get(f"{poc.BASE}/estados").mock(return_value=httpx.Response(200, json={"registros": [], "status": "ok"}))
    assert poc.Cliente().get("estados") == {"registros": [], "status": "ok"}
    respx.get(f"{poc.BASE}/transferencias").mock(return_value=httpx.Response(200, json={"status": "erro"}))
    with pytest.raises(RuntimeError, match="status 'erro'"):
        poc.Cliente().get("transferencias")


@respx.mock
def test_todos_pagina_ate_vir_pagina_incompleta(monkeypatch):
    monkeypatch.setattr(poc, "PAGINA", 2)
    rota = respx.get(f"{poc.BASE}/por_estado_municipio").mock(
        side_effect=[
            httpx.Response(200, json={"registros": [{"n": 1}, {"n": 2}], "next": "x", "status": "ok"}),
            httpx.Response(200, json={"registros": [{"n": 3}], "next": "x", "status": "ok"}),  # `next` vem sempre preenchido
        ]
    )
    registros = poc.Cliente().todos("por_estado_municipio", p_estado=26, p_municipio=6751, p_ano=2026)
    assert [r["n"] for r in registros] == [1, 2, 3]
    assert rota.calls[1].request.url.params["page"] == "2"
    assert rota.calls[0].request.url.params["pageSize"] == "2"


@respx.mock
def test_get_repete_em_504_e_desiste_depois_de_cinco():
    rota = respx.get(f"{poc.BASE}/estados").mock(return_value=httpx.Response(504))
    with pytest.raises(httpx.HTTPStatusError):
        poc.Cliente().get("estados")
    assert rota.call_count == 5


@pytest.mark.parametrize(("reais", "esperado"), [(1000410.68, 100041068), (0.29, 29), (1.15, 115), (4.35, 435), (0, 0)])
def test_centavos_arredonda_em_vez_de_truncar(reais, esperado):
    assert poc.centavos(reais) == esperado
    # int(x*100) erra em alguns valores (0.29 -> 28): é por isso que a normalização não pode usá-lo
    assert esperado - int(reais * 100) in (0, 1)


def test_fixtures_do_municipio_sao_coerentes():
    municipio = json.loads((FIXTURES / "municipios_neves_paulista.json").read_text(encoding="utf-8"))
    assert municipio == [{"codigo": 6751, "codigo_uf": 26, "nome": "Neves Paulista"}]
    estados = json.loads((FIXTURES / "estados.json").read_text(encoding="utf-8"))
    assert {"codigo": 26, "nome": "São Paulo"} in estados
    tipos = {t["transferencia"]: t["codigo"] for t in json.loads((FIXTURES / "transferencias.json").read_text(encoding="utf-8"))}
    assert tipos["FPM"] == 3 and tipos["ITR"] == 4
    amostra = json.loads((FIXTURES / "por_estado_municipio.json").read_text(encoding="utf-8"))["amostra"]
    assert amostra and {r["CO_IBGE"] for r in amostra} == {3532504} and {r["codigo_siafi"] for r in amostra} == {6751}


def test_detalhe_do_mes_em_andamento_tem_terceiro_decendio_zerado():
    detalhe = json.loads((FIXTURES / "detalhe_fpm_2026_10.json").read_text(encoding="utf-8"))[0]
    soma = poc.centavos(detalhe["VA_PRIMEIRO_DEC"]) + poc.centavos(detalhe["VA_SEGUNDO_DEC"]) + poc.centavos(detalhe["VA_TERCEIRO_DEC"])
    assert soma == poc.centavos(detalhe["TOTAL"])  # TOTAL é a soma dos três decêndios
    assert detalhe["VA_TERCEIRO_DEC"] == 0  # mês ainda não fechado em 29/10/2026
