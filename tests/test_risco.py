import copy
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from nucleo import pipeline
from nucleo import risco as r
from nucleo.config import carregar_config
from nucleo.modelo import Verba
from nucleo.normaliza import ImpedimentoEmenda, Normalizacao, ObraLigada, carregar_retratos, normalizar

RAIZ = Path(__file__).resolve().parents[1]
DATA = date(2026, 10, 30)
SCHEMA = json.loads((RAIZ / "schemas" / "verba.schema.json").read_text(encoding="utf-8"))
VALIDADOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
FONTE = {"nome": "Transferegov", "url": "https://exemplo.gov.br", "data_coleta": "2026-10-29T18:00:00-03:00"}


@pytest.fixture
def config():
    return carregar_config()


def verba(**kw) -> Verba:
    base = {
        "id": "transferegov_discricionarias-1", "fonte": "transferegov_discricionarias", "id_fonte": "1", "nome": "Obra", "tipo": "voluntaria",
        "valor_total": 100000, "status_site": "aprovada", "status_fonte": "Assinado", "em_risco": False, "historico": [], "fontes": [FONTE],
    }
    return Verba.model_validate({**base, **kw})


def em(dias: int, nome: str = "fim_vigencia", **kw) -> Verba:
    return verba(prazos={nome: DATA + timedelta(days=dias)}, **kw)


# --- prazo_proximo -----------------------------------------------------------------------------


@pytest.mark.parametrize(("dias", "dispara"), [(59, True), (60, True), (61, False), (0, True), (-1, False), (1, True), (365, False), (-4000, False)])
def test_prazo_proximo_bordas_de_59_60_e_61_dias(config, dias, dispara):
    m = r.motivo_prazo(em(dias), DATA, config)
    assert (m is not None) is dispara
    if dispara:
        assert m.codigo == "prazo_proximo" and m.data_limite == DATA + timedelta(days=dias)


def test_prazo_proximo_texto_no_singular_e_no_plural(config):
    assert r.motivo_prazo(em(38), DATA, config).texto == "Prazo em 38 dias"  # o exemplo da spec
    assert r.motivo_prazo(em(1), DATA, config).texto == "Prazo em 1 dia"
    assert r.motivo_prazo(em(0), DATA, config).texto == "Prazo em 0 dias"


@pytest.mark.parametrize("nome", ["clausula_suspensiva", "fim_vigencia", "prestacao_contas", "adesao"])
def test_prazo_proximo_vale_para_os_quatro_prazos_monitorados(config, nome):
    assert r.motivo_prazo(em(10, nome), DATA, config) is not None


def test_prazo_proximo_so_olha_os_prazos_da_config_e_escolhe_o_mais_proximo(config):
    v = verba(prazos={"fim_vigencia": DATA + timedelta(days=40), "prestacao_contas": DATA + timedelta(days=20), "assinatura": DATA + timedelta(days=5), "proposta": DATA + timedelta(days=3)})
    m = r.motivo_prazo(v, DATA, config)
    assert m.texto == "Prazo em 20 dias" and m.data_limite == DATA + timedelta(days=20)  # assinatura e proposta não são monitorados
    config.regras.risco.prazos_monitorados = ["fim_vigencia"]
    assert r.motivo_prazo(v, DATA, config).texto == "Prazo em 40 dias"


def test_prazo_proximo_usa_o_limite_configurado_e_ignora_verba_sem_prazos(config):
    config.regras.risco.dias_alerta_prazo = 30
    assert r.motivo_prazo(em(30), DATA, config) is not None and r.motivo_prazo(em(31), DATA, config) is None
    assert r.motivo_prazo(verba(), DATA, config) is None  # sem `prazos`


# --- cauc_sem_comprovacao ----------------------------------------------------------------------

ITENS = [("4.2", "Regularidade Previdenciária")]


def test_cauc_uma_verba_elegivel_recebe_um_motivo_por_item(config):
    itens = [("3.2.3", "RREO - Anexo 8 ao Siope"), ("4.2", "Regularidade Previdenciária")]
    motivos = r.motivos_cauc(verba(status_site="proposta"), itens, config)
    assert [m.texto for m in motivos] == ["CAUC: item 3.2.3 sem comprovação (RREO - Anexo 8 ao Siope)", "CAUC: item 4.2 sem comprovação (Regularidade Previdenciária)"]
    assert {m.codigo for m in motivos} == {"cauc_sem_comprovacao"}


@pytest.mark.parametrize("status", ["proposta", "aprovada"])
@pytest.mark.parametrize("tipo", ["voluntaria", "emenda_finalidade"])
def test_cauc_vale_para_voluntaria_e_emenda_nas_etapas_antes_da_liberacao(config, tipo, status):
    assert len(r.motivos_cauc(verba(tipo=tipo, status_site=status), ITENS, config)) == 1


@pytest.mark.parametrize(
    "kw",
    [
        {"status_site": "execucao"}, {"status_site": "prestacao"}, {"status_site": "perdida"}, {"status_site": "oportunidade"}, {"status_site": None},
        {"tipo": "fundo_a_fundo"}, {"tipo": "programa_adesao"}, {"tipo": "emenda_pix"}, {"tipo": "constitucional"},
        {"fonte": "transferegov_parcerias", "tipo": "emenda_finalidade"},  # fundo a fundo: sem alerta de CAUC (D13)
        {"fonte": "transferegov_fundoafundo"},
    ],
)
def test_cauc_nao_vale_fora_do_tipo_da_etapa_e_da_fonte(config, kw):
    assert r.motivos_cauc(verba(**{"status_site": "aprovada", **kw}), ITENS, config) == []


def test_cauc_sem_itens_sem_comprovacao_nao_alerta(config):
    assert r.motivos_cauc(verba(), [], config) == []


def retrato_cauc(linha: dict, legenda: dict[str, str]) -> dict:
    return {"dados": {"entes": [linha], "legenda": [{"codigo": c, "exigencia": e} for c, e in legenda.items()]}}


def test_itens_sem_comprovacao_so_conta_exclamacao_em_ordem_numerica():
    linha = {"UF": "SP", "Nome do Ente Federado": "X", "Código IBGE": "1", "1.1": "30/03/27", "1.3": "Desabilitado", "4.2": "!", "3.4.1": "!", "3.2.1": "!", "5.1": "", "3.2.4": "Desabilitado"}
    legenda = {"3.2.1": "RREO", "4.2": "Previdenciária"}  # 3.4.1 não está na legenda: o código serve de nome
    assert r.itens_sem_comprovacao(retrato_cauc(linha, legenda)) == [("3.2.1", "RREO"), ("3.4.1", "3.4.1"), ("4.2", "Previdenciária")]  # ordem numérica, não a da linha


# --- obra_parada -------------------------------------------------------------------------------


def obra(situacao="Em execução", ultima=None, paralisada=None) -> ObraLigada:
    return ObraLigada("123.45-67", situacao, ultima, paralisada)


@pytest.mark.parametrize(("dias", "dispara"), [(89, False), (90, False), (91, True), (500, True), (0, False)])
def test_obra_sem_atualizacao_dispara_so_acima_de_90_dias(config, dias, dispara):
    m = r.motivo_obra(verba(), obra(ultima=DATA - timedelta(days=dias)), DATA, config)
    assert (m is not None) is dispara
    if dispara:
        assert m.codigo == "obra_parada" and m.texto == f"Obra parada há {dias} dias"


def test_obra_sem_nenhum_registro_de_execucao_nao_dispara(config):
    for situacao in ("Em execução", "Cadastrada", None):
        assert r.motivo_obra(verba(), obra(situacao=situacao, ultima=None), DATA, config) is None  # ausência de dado não é obra parada


@pytest.mark.parametrize("situacao", ["Concluída", "Cancelada", "Inacabada"])
def test_obra_encerrada_nao_e_parada_mesmo_sem_atualizar_ha_anos(config, situacao):
    assert r.motivo_obra(verba(), obra(situacao=situacao, ultima=DATA - timedelta(days=2000)), DATA, config) is None


def test_obra_paralisada_conta_os_dias_do_registro_de_paralisacao(config):
    m = r.motivo_obra(verba(), obra("Paralisada", ultima=DATA - timedelta(days=5), paralisada=DATA - timedelta(days=30)), DATA, config)
    assert m.texto == "Obra parada há 30 dias"  # a paralisação vale mais que a última atualização
    assert r.motivo_obra(verba(), obra("Paralisada", paralisada=DATA - timedelta(days=1)), DATA, config).texto == "Obra parada há 1 dia"


def test_obra_paralisada_sem_registro_usa_a_ultima_atualizacao_e_sem_data_nao_cita_dias(config):
    assert r.motivo_obra(verba(), obra("Paralisada", ultima=DATA - timedelta(days=10)), DATA, config).texto == "Obra parada há 10 dias"
    assert r.motivo_obra(verba(), obra("Paralisada"), DATA, config).texto == "Obra paralisada no Obrasgov"


def test_obra_paralisada_dispara_mesmo_com_atualizacao_recente(config):
    assert r.motivo_obra(verba(), obra("Paralisada", ultima=DATA), DATA, config) is not None


def test_obra_usa_o_limite_configurado(config):
    config.regras.risco.dias_obra_parada = 10
    assert r.motivo_obra(verba(), obra(ultima=DATA - timedelta(days=11)), DATA, config) is not None
    assert r.motivo_obra(verba(), obra(ultima=DATA - timedelta(days=10)), DATA, config) is None


# --- impedimento_emenda ------------------------------------------------------------------------


def test_impedimento_so_enquanto_a_situacao_atual_e_impedido(config):
    assert r.motivo_impedimento(verba(), ImpedimentoEmenda("IMPEDIDO", "Beneficiário sem conta"), config).texto == "Impedimento técnico"
    assert r.motivo_impedimento(verba(), ImpedimentoEmenda("CIENTE", "Beneficiário sem conta"), config) is None  # superado


# --- aplicar_risco -----------------------------------------------------------------------------


def normalizacao(*verbas, obras=None, impedimentos=None) -> Normalizacao:
    return Normalizacao(DATA, list(verbas), [], [], {}, obras or {}, impedimentos or {})


CAUC_REAL = retrato_cauc({"UF": "SP", "Código IBGE": "3532504", "4.2": "!", "1.3": "Desabilitado", "1.1": "30/03/27"}, {"4.2": "Regularidade Previdenciária"})


def aplicar(norm, config, retratos=None):
    return r.aplicar_risco(norm, {"cauc": CAUC_REAL, "obrasgov": {"dados": {}}, **(retratos or {})}, config, DATA)


def test_so_as_etapas_da_config_recebem_em_risco(config):
    verbas = [em(10, id=f"transferegov_discricionarias-{s}", status_site=s) for s in ("proposta", "aprovada", "execucao", "prestacao")]
    fora = [em(10, id=f"transferegov_discricionarias-x{i}", status_site=s) for i, s in enumerate(["oportunidade", "concluida", "perdida", None])]
    res = aplicar(normalizacao(*verbas, *fora), config, {"cauc": None})
    assert [v.em_risco for v in verbas] == [True] * 4 and [v.em_risco for v in fora] == [False] * 4
    assert all("motivos_risco" not in v.para_dict() for v in fora)
    assert res.verbas_em_risco == 4


def test_oportunidade_com_adesao_proxima_nao_entra_no_em_risco(config):
    v = verba(id="siconv_programa-1", fonte="siconv_programa", tipo="programa_adesao", status_site="oportunidade", valor_total=None, prazos={"adesao": DATA + timedelta(days=1)})
    aplicar(normalizacao(v), config)
    assert v.em_risco is False  # D13: o prazo de adesão aparece no cartão da oportunidade, não em "Em risco agora"


def test_varios_motivos_na_ordem_da_spec_e_contagem_por_codigo(config):
    v = verba(status_site="aprovada", prazos={"fim_vigencia": DATA + timedelta(days=10)})
    res = aplicar(normalizacao(v, obras={v.id: obra("Paralisada", paralisada=DATA - timedelta(days=7))}), config)
    assert [m.codigo for m in v.motivos_risco] == ["prazo_proximo", "cauc_sem_comprovacao", "obra_parada"]
    assert v.em_risco is True and res.por_codigo == Counter({"prazo_proximo": 1, "cauc_sem_comprovacao": 1, "obra_parada": 1}) and res.verbas_em_risco == 1


def test_obra_parada_so_com_obra_ligada_a_verba(config):
    v = verba(status_site="execucao")
    aplicar(normalizacao(v), config, {"cauc": None})
    assert v.em_risco is False
    aplicar(normalizacao(v, obras={v.id: obra(ultima=DATA - timedelta(days=200))}), config, {"cauc": None})
    assert [m.codigo for m in v.motivos_risco] == ["obra_parada"]


def test_impedimento_esta_desligado_por_padrao_mesmo_com_dado(config):
    v = verba(status_site="aprovada", tipo="emenda_pix")
    imp = {v.id: ImpedimentoEmenda("IMPEDIDO", "x")}
    assert "impedimento_emenda" in config.regras.risco.desligadas
    aplicar(normalizacao(v, impedimentos=imp), config, {"cauc": None})
    assert v.em_risco is False  # a regra existe, mas só liga quando um registro real confirmar o campo (D13)
    config.regras.risco.desligadas = []
    aplicar(normalizacao(v, impedimentos=imp), config, {"cauc": None})
    assert [m.codigo for m in v.motivos_risco] == ["impedimento_emenda"] and v.em_risco is True


def test_regra_desligada_nao_roda(config):
    config.regras.risco.desligadas = ["impedimento_emenda", "prazo_proximo", "cauc_sem_comprovacao"]
    v = em(5, status_site="proposta")
    res = aplicar(normalizacao(v), config)
    assert v.em_risco is False and res.verbas_em_risco == 0 and res.avisos == []


def test_sem_retrato_do_cauc_ou_do_obrasgov_avisa_em_vez_de_calar(config):
    res = aplicar(normalizacao(verba()), config, {"cauc": None, "obrasgov": None})
    assert any("CAUC sem retrato" in a for a in res.avisos) and any("Obrasgov sem retrato" in a for a in res.avisos)


def test_aplicar_duas_vezes_da_o_mesmo_resultado_e_limpa_o_que_deixou_de_valer(config):
    v = em(10, status_site="aprovada")
    norm = normalizacao(v)
    aplicar(norm, config, {"cauc": None})
    antes = v.para_dict()
    aplicar(norm, config, {"cauc": None})
    assert v.para_dict() == antes
    r.aplicar_risco(norm, {"cauc": None, "obrasgov": {"dados": {}}}, config, DATA + timedelta(days=40))  # o prazo agora está vencido
    assert v.em_risco is False and v.motivos_risco == []
    assert not list(VALIDADOR.iter_errors(v.para_dict()))


def test_verba_em_risco_valida_no_schema_com_data_limite_em_iso(config):
    v = em(10, status_site="aprovada")
    aplicar(normalizacao(v), config)
    saida = v.para_dict()
    assert saida["em_risco"] is True
    assert [m["codigo"] for m in saida["motivos_risco"]] == ["prazo_proximo", "cauc_sem_comprovacao"]
    assert saida["motivos_risco"][0]["data_limite"] == (DATA + timedelta(days=10)).isoformat() and "data_limite" not in saida["motivos_risco"][1]
    assert not list(VALIDADOR.iter_errors(saida))


# --- dados reais -------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reais():
    return carregar_retratos(RAIZ, DATA)


def test_dados_reais_de_hoje(reais, config):
    res = normalizar(reais, config, DATA)
    risco = r.aplicar_risco(res, reais, config, DATA)
    em_risco = {v.id: v for v in res.verbas if v.em_risco}
    assert len(em_risco) == 9 == risco.verbas_em_risco
    assert risco.por_codigo == Counter({"cauc_sem_comprovacao": 8, "prazo_proximo": 1}) and risco.avisos == []
    prazo = em_risco["transferegov_discricionarias-1733967"]  # recapeamento, vigência até 20/12/2026
    assert [m.texto for m in prazo.motivos_risco] == ["Prazo em 51 dias"] and prazo.motivos_risco[0].data_limite == date(2026, 12, 20)
    cauc = [v for v in em_risco.values() if v.motivos_risco[0].codigo == "cauc_sem_comprovacao"]
    assert len(cauc) == 8 and {v.fonte for v in cauc} == {"transferegov_discricionarias"} and {v.status_site for v in cauc} == {"proposta", "aprovada"}
    assert {m.texto for v in cauc for m in v.motivos_risco} == {"CAUC: item 4.2 sem comprovação (Regularidade Previdenciária)"}


def test_dados_reais_as_de_fundo_a_fundo_e_as_oportunidades_ficam_sem_alerta(reais, config):
    res = normalizar(reais, config, DATA)
    r.aplicar_risco(res, reais, config, DATA)
    sem = [v for v in res.verbas if v.fonte in ("transferegov_parcerias", "transferegov_fundoafundo", "siconv_programa")]
    assert len(sem) == 24 and not any(v.em_risco for v in sem)


def test_dados_reais_obra_sem_execucao_fisica_nao_vira_obra_parada(reais, config):
    res = normalizar(reais, config, DATA)
    assert len(res.obras) == 3 and all(o.ultima_atualizacao is None for o in res.obras.values())  # as 3 obras da prefeitura, sem medição
    risco = r.aplicar_risco(res, reais, config, DATA)
    assert risco.por_codigo["obra_parada"] == 0


def test_dados_reais_todas_as_verbas_continuam_validas_no_schema(reais, config):
    res = normalizar(reais, config, DATA)
    r.aplicar_risco(res, reais, config, DATA)
    for v in res.verbas:
        assert not list(VALIDADOR.iter_errors(v.para_dict())), v.id


def test_dados_reais_em_01_de_novembro_nao_entram_as_oportunidades(reais, config):
    # as 10 oportunidades passam a menos de 60 dias do fim (31/12) em 01/11: D13 as mantém fora do em_risco
    dia = date(2026, 11, 1)
    res = normalizar(carregar_retratos(RAIZ, dia), config, dia)
    r.aplicar_risco(res, reais, config, dia)
    assert [v for v in res.verbas if v.status_site == "oportunidade" and v.prazos.adesao - dia <= timedelta(days=60)]  # estão na janela
    assert not any(v.em_risco for v in res.verbas if v.status_site == "oportunidade")


# --- pipeline ----------------------------------------------------------------------------------


def test_pipeline_encadeia_normalizacao_e_risco(config, raiz_sem_publicado):
    p = pipeline.processar(raiz_sem_publicado, DATA, config)
    assert len(p.normalizacao.verbas) == 46 and p.risco.verbas_em_risco == 9


def test_pipeline_imprime_resumo_do_risco(capsys, raiz_sem_publicado):
    assert pipeline.main(["--data", "2026-10-30", "--raiz", str(raiz_sem_publicado), "--sem-publicar"]) == 0
    saida = capsys.readouterr().out
    assert "Normalização de 2026-10-30: 46 verbas" in saida
    assert "Em risco: 9 verba(s); motivos: prazo_proximo=1, cauc_sem_comprovacao=8" in saida
    assert "transferegov_discricionarias-1733967 (execucao): Prazo em 51 dias" in saida


def test_config_de_risco_valida_os_campos_novos(config):
    risco = config.regras.risco
    assert risco.status == ["proposta", "aprovada", "execucao", "prestacao"] and risco.cauc_fontes == ["transferegov_discricionarias"]
    assert risco.desligadas == ["impedimento_emenda"] and risco.textos.obra_paralisada
    assert copy.deepcopy(risco.textos).prazo_proximo.format(dias=1, dias_unidade="dia") == "Prazo em 1 dia"
