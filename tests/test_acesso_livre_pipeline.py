"""D23: a conferência semanal no Acesso Livre corrige a situação de proposta sem convênio (sem rede)."""

import json
from datetime import date
from pathlib import Path

import pytest

from nucleo import avisos
from nucleo.config import carregar_config
from nucleo.normaliza import carregar_retratos, normalizar
from nucleo.publica import montar_fontes

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "tests" / "fixtures" / "transferegov_acesso_livre"
PROPOSTA = "transferegov_discricionarias-2175551"  # 002456/2026, rejeitada por impedimento técnico em 04/11/2026


def _acesso(data: str = "2026-11-05", propostas: list[dict] | None = None) -> dict:
    lista = json.loads((FIXTURES / "lista_pagina1.json").read_text(encoding="utf-8"))["rows"]
    propostas = propostas if propostas is not None else [{**r, "possui_parecer": r["possui_parecer"] == "Sim"} for r in lista]
    return {"fonte": "transferegov_acesso_livre", "data": data, "coletado_em": f"{data}T21:00:00-03:00", "metadados": {"origem": "manual local"}, "dados": {"propostas": propostas, "pareceres": []}}


@pytest.fixture(scope="module")
def retratos():
    return carregar_retratos(RAIZ, date(2026, 10, 30))


def _verba(norm, verba_id):
    return next(v for v in norm.verbas if v.id == verba_id)


def test_sem_conferencia_a_situacao_e_a_do_lote(retratos):
    norm = normalizar({**retratos, "transferegov_acesso_livre": None}, carregar_config(), date(2026, 11, 5))
    v = _verba(norm, PROPOSTA)
    assert v.status_fonte == "Proposta/Plano de Trabalho Complementado em Análise" and v.status_site != "perdida"
    assert norm.conferidas == {}


def test_conferencia_mais_nova_corrige_a_situacao_e_cita_a_fonte(retratos):
    norm = normalizar({**retratos, "transferegov_acesso_livre": _acesso()}, carregar_config(), date(2026, 11, 5))
    v = _verba(norm, PROPOSTA)
    assert v.status_fonte == "Proposta/Plano de Trabalho Rejeitados por Impedimento técnico" and v.status_site == "perdida"
    assert norm.conferidas == {PROPOSTA: date(2026, 11, 5)}
    assert any("Acesso Livre (conferido em 05/11/2026, coleta manual)" in f.nome for f in v.fontes)
    assert len(v.fontes) == 2 and all(f.url and f.data_coleta for f in v.fontes)


def test_so_muda_proposta_sem_convenio(retratos):
    # 041390/2025 e 033961/2024 aparecem como "Em execução" na lista e já são convênios no lote: nada muda neles
    sem = normalizar({**retratos, "transferegov_acesso_livre": None}, carregar_config(), date(2026, 11, 5))
    com = normalizar({**retratos, "transferegov_acesso_livre": _acesso()}, carregar_config(), date(2026, 11, 5))
    mudaram = {a.id for a, b in zip(sem.verbas, com.verbas, strict=True) if (a.status_fonte, a.status_site) != (b.status_fonte, b.status_site)}
    assert mudaram == {PROPOSTA}


def test_conferencia_mais_velha_que_a_carga_nao_vale(retratos):
    norm = normalizar({**retratos, "transferegov_acesso_livre": _acesso("2026-07-10")}, carregar_config(), date(2026, 11, 5))
    assert _verba(norm, PROPOSTA).status_fonte == "Proposta/Plano de Trabalho Complementado em Análise" and norm.conferidas == {}


def test_proposta_que_o_lote_nao_tem_so_vira_aviso(retratos):
    nova = {"id_proposta": "9999999", "numero": "000001/2026", "situacao": "Proposta/Plano de Trabalho enviado para Análise", "orgao": "X", "possui_parecer": False}
    base = _acesso()["dados"]["propostas"]
    sem = normalizar({**retratos, "transferegov_acesso_livre": None}, carregar_config(), date(2026, 11, 5))
    com = normalizar({**retratos, "transferegov_acesso_livre": _acesso(propostas=[*base, nova])}, carregar_config(), date(2026, 11, 5))
    assert len(com.verbas) == len(sem.verbas)
    assert any("000001/2026" in a and "não tem" in a for a in com.avisos)


def test_fonte_manual_nunca_e_defasada_e_nao_entra_no_aviso_diario(retratos):
    cfg = carregar_config()
    fontes = montar_fontes({**retratos, "transferegov_acesso_livre": _acesso("2026-11-01")}, cfg, date(2026, 11, 5))
    f = fontes["transferegov_acesso_livre"]
    assert f["situacao"] == "manual" and f["retrato"] == "2026-11-01"
    assert avisos.aviso_fontes({"transferegov_acesso_livre": {**f, "situacao": "sem_retrato"}}, date(2026, 11, 5)) is None


def test_aviso_de_conferencia_atrasada():
    fonte = lambda dia: {"transferegov_acesso_livre": {"retrato": dia, "situacao": "manual"}}  # noqa: E731
    assert avisos.aviso_acesso_livre(fonte("2026-10-29"), date(2026, 11, 5), 8) is None  # 7 dias
    atrasado = avisos.aviso_acesso_livre(fonte("2026-10-20"), date(2026, 11, 5), 8)
    assert atrasado and atrasado.titulo == avisos.TITULO_ACESSO_LIVRE and "16 dias" in atrasado.corpo
    assert "Ainda não houve nenhuma" in avisos.aviso_acesso_livre({"transferegov_acesso_livre": {"retrato": None, "situacao": "sem_retrato"}}, date(2026, 11, 5), 8).corpo
