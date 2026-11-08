"""D23: leitura e retrato da conferência semanal no Acesso Livre (sem rede, com amostras reais)."""

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from coleta import acesso_livre as al
from coleta.base import gravar_retrato
from nucleo.normaliza import carregar_retratos

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "tests" / "fixtures" / "transferegov_acesso_livre"
AGORA = datetime(2026, 11, 5, 21, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


@pytest.fixture(scope="module")
def lista():
    return [al.linha_da_lista(r) for r in json.loads((FIXTURES / "lista_pagina1.json").read_text(encoding="utf-8"))["rows"]]


@pytest.fixture(scope="module")
def siconv():
    return carregar_retratos(RAIZ, date(2026, 10, 30))["transferegov_discricionarias"]


def test_parecer_perde_telefone_e_contato_e_o_resto_fica_literal():
    bruto = json.loads((FIXTURES / "parecer_exemplo.json").read_text(encoding="utf-8"))["bruto"]["texto"]
    limpo = al.limpar_parecer(bruto)
    assert "99999" not in limpo and "Fulano" not in limpo and "Contato" not in limpo
    assert limpo.endswith("Prazo para atendimento: 14/09/2026.")
    assert "Diligência COCEL Nº 140/2026" in limpo and "saneados os apontamentos técnicos" in limpo  # o corpo não é alterado


@pytest.mark.parametrize(
    "frase, some",
    [
        ("Fale com o setor: (61) 3333-4444.", True),
        ("Ligue 61 99999-1234 para tirar dúvidas.", True),
        ("Envie para fulano.silva@orgao.gov.br até sexta.", True),
        ("Atenciosamente, Fulano de Tal.", True),
        ("Responsável: Fulano de Tal.", True),
        ("Prazo para atendimento: 14/09/2026.", False),  # data não é telefone
        ("Nota técnica nº 140/2026 e processo 25000.123456/2026-11.", False),  # número de processo também não
    ],
)
def test_so_some_o_que_identifica_pessoa(frase, some):
    assert (al.limpar_parecer(f"Texto antes. {frase} Texto depois.") == "Texto antes. Texto depois.") is some


def test_lista_real_vira_registros(lista):
    assert len(lista) == 20
    r = next(p for p in lista if p["numero"] == "002456/2026")
    assert r == {"id_proposta": "2175551", "numero": "002456/2026", "situacao": "Proposta/Plano de Trabalho Rejeitados por Impedimento técnico",
                 "orgao": "30000 - MINISTERIO DA JUSTICA E SEGURANCA PUBLICA", "possui_parecer": True}
    assert sum(p["possui_parecer"] for p in lista) == 4 and all(isinstance(p["possui_parecer"], bool) for p in lista)


def test_datas_e_parecer_do_retrato():
    assert al.data_br("25/08/2026") == "2026-08-25" and al.data_br("lixo") is None
    bruto = json.loads((FIXTURES / "parecer_exemplo.json").read_text(encoding="utf-8"))["bruto"]
    p = al.parecer_do_retrato("2175551", {**bruto, "responsavel": "NOME QUE NÃO PODE FICAR"})
    assert p["data"] == "2026-08-25" and p["id_parecer"] == "2040854" and "responsavel" not in p
    assert "NOME" not in json.dumps(p, ensure_ascii=False)


def test_o_lote_de_julho_ja_sabe_a_situacao_de_quase_tudo(lista, siconv):
    antes = al.situacoes_do_siconv(siconv)
    assert antes["2175551"] == "Proposta/Plano de Trabalho Complementado em Análise"  # a única que mudou desde 17/07
    assert antes["1981768"] == "Proposta/Plano de Trabalho Rejeitados"


def test_so_as_que_mudaram_novas_ou_perdidas_com_parecer_valem_a_leitura(lista, siconv):
    escolhidas = al.propostas_para_pareceres(lista, al.situacoes_do_siconv(siconv), perdidas=set())
    assert [p["numero"] for p in escolhidas] == ["002456/2026"]  # mudou e tem parecer
    # a mesma lista, mas dizendo que a 2113518 e a 2076013 (com parecer, sem mudança) são perdidas no site: entram, depois da que mudou
    mais = al.propostas_para_pareceres(lista, al.situacoes_do_siconv(siconv), perdidas={"2113518"})
    assert [p["numero"] for p in mais] == ["002456/2026", "041390/2025"]


def test_perdida_entra_mesmo_com_possui_parecer_nao(lista, siconv):
    antes = al.situacoes_do_siconv(siconv)
    assert next(p for p in lista if p["id_proposta"] == "2152082")["possui_parecer"] is False
    escolhidas = al.propostas_para_pareceres(lista, antes, perdidas={"2152082"})
    assert [p["numero"] for p in escolhidas] == ["002456/2026", "064413/2025"]  # a que mudou primeiro; a perdida sem "Sim" vem em seguida


def test_proposta_que_o_lote_nao_tem_conta_como_novidade(lista):
    escolhidas = al.propostas_para_pareceres(lista, {}, perdidas=set())  # sem lote nenhum: tudo é novo, mas só com parecer
    assert {p["numero"] for p in escolhidas} == {"002456/2026", "041390/2025", "017544/2025", "033961/2024"}
    assert len(al.propostas_para_pareceres(lista, {}, perdidas=set(), limite=2)) == 2


def test_comparacao_de_situacao_ignora_caixa(lista):
    mesmo = {p["id_proposta"]: p["situacao"].upper() for p in lista}
    assert al.propostas_para_pareceres(lista, mesmo, perdidas=set()) == []  # "enviado" e "Enviado" são a mesma situação


def test_retrato_grava_em_dados_brutos_sem_nome_e_sem_sobrescrever(lista, tmp_path):
    bruto = json.loads((FIXTURES / "parecer_exemplo.json").read_text(encoding="utf-8"))["bruto"]
    retrato = al.montar_retrato(lista, [al.parecer_do_retrato("2175551", bruto)], AGORA, {"cnpj": "45145414000147", "total_lista": 241})
    caminho = gravar_retrato(tmp_path, retrato)
    assert caminho == tmp_path / "dados" / "brutos" / "transferegov_acesso_livre" / "2026-11-05.json"
    lido = json.loads(caminho.read_text(encoding="utf-8"))
    assert lido["fonte"] == "transferegov_acesso_livre" and lido["metadados"]["origem"] == "manual local" and lido["data"] == "2026-11-05"
    assert [p["id_proposta"] for p in lido["dados"]["propostas"]] == sorted((p["id_proposta"] for p in lista), key=int)
    assert "Fulano" not in caminho.read_text(encoding="utf-8") and "99999" not in caminho.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        gravar_retrato(tmp_path, retrato)  # retratos nunca são editados


def test_paginacao_da_lista():
    assert al.ler_paginacao("Escolha a Proposta Página 1 de 13 (241 item(s)) [Primeira/Ant]") == (1, 13, 241)
    assert al.ler_paginacao("Pagina 13 de 13 (241 item(s))") == (13, 13, 241)
    assert al.ler_paginacao("sem paginação") is None


def test_o_retrato_nao_guarda_o_link_do_parecer_nem_o_nome():
    bruto = json.loads((FIXTURES / "parecer_exemplo.json").read_text(encoding="utf-8"))["bruto"]
    p = al.parecer_do_retrato("2175551", {**bruto, "href": "/voluntarias/x?idParecer=1&Usr=a&Pwd=b", "responsavel": "NOME"})
    assert set(p) == {"id_proposta", "id_parecer", "data", "parecer_do", "atribuicao", "texto"}


def test_dias_desde_a_ultima_conferencia():
    assert al.dias_desde(None, date(2026, 11, 5)) is None
    assert al.dias_desde({"data": "2026-10-29"}, date(2026, 11, 5)) == 7
