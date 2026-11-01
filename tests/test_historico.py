import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from nucleo import historico as h
from nucleo import pipeline
from nucleo.config import carregar_config
from nucleo.modelo import Perda, Verba
from nucleo.normaliza import Normalizacao, carregar_retratos, normalizar

RAIZ = Path(__file__).resolve().parents[1]
DATA = date(2026, 10, 30)
ONTEM = DATA - timedelta(days=1)
SCHEMA = json.loads((RAIZ / "schemas" / "verba.schema.json").read_text(encoding="utf-8"))
VALIDADOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
FONTE = {"nome": "Transferegov", "url": "https://exemplo.gov.br", "data_coleta": "2026-10-29T18:00:00-03:00"}


@pytest.fixture
def config():
    return carregar_config()


def verba(id_="transferegov_discricionarias-1", status="execucao", fonte_status="Em execução", **kw) -> Verba:
    base = {
        "id": id_, "fonte": "transferegov_discricionarias", "id_fonte": id_.split("-")[1], "nome": "Obra", "tipo": "voluntaria", "valor_total": 100_000_00,
        "status_site": status, "status_fonte": fonte_status, "em_risco": False, "historico": [], "fontes": [FONTE],
    }
    return Verba.model_validate({**base, **kw})


def norm(*verbas) -> Normalizacao:
    return Normalizacao(DATA, list(verbas), [], [], {})


def rodar(verbas, anterior, config, tmp_path, retratos=None, data=DATA):
    n = norm(*verbas)
    return n, h.aplicar_historico(n, anterior, data, config, tmp_path, retratos)


def publicar(*verbas) -> dict[str, Verba]:
    """O que o publicado anterior teria: as verbas já com histórico e perda, relidas do JSON como a T2.5 fará."""
    return {v.id: Verba.model_validate(v.para_dict()) for v in verbas}


# --- primeira execução -------------------------------------------------------------------------


def test_primeira_execucao_cada_verba_nasce_com_uma_entrada_sem_estado_anterior(config, tmp_path):
    v = verba()
    _, res = rodar([v], None, config, tmp_path)
    assert res.primeira_execucao and res.novas == [v.id] and res.mudancas == []
    (e,) = v.historico
    assert (e.data, e.de, e.para, e.fonte, e.nota) == (DATA, None, "execucao", "transferegov_discricionarias", "Primeira coleta")


def test_a_nota_da_primeira_entrada_cita_a_data_em_que_a_fonte_registra_a_situacao(config, tmp_path):
    v = verba("transferegov_discricionarias-77")
    retrato = {"dados": {"historico_situacao": [
        {"ID_PROPOSTA": "77", "DIA_HISTORICO_SIT": "19/08/2025 15:18:12"},
        {"ID_PROPOSTA": "77", "DIA_HISTORICO_SIT": "05/03/2026 00:24:34"},
        {"ID_PROPOSTA": "88", "DIA_HISTORICO_SIT": "01/01/2020 00:00:00"},
    ]}}
    rodar([v], None, config, tmp_path, {"transferegov_discricionarias": retrato})
    assert v.historico[0].nota == "Primeira coleta; situação registrada na fonte desde 05/03/2026"  # o evento mais recente da proposta 77


def test_verba_sem_status_mapeado_usa_o_rotulo_do_selo(config, tmp_path):
    v = verba(status=None, fonte_status="Situação nova")
    rodar([v], None, config, tmp_path)
    assert v.historico[0].para == "situacao_em_analise"


# --- transições --------------------------------------------------------------------------------


def test_sem_mudanca_o_historico_nao_cresce_e_a_segunda_execucao_e_identica(config, tmp_path):
    v = verba()
    rodar([v], None, config, tmp_path)
    antes = v.para_dict()
    v2 = verba()
    _, res = rodar([v2], publicar(v), config, tmp_path, data=DATA + timedelta(days=1))
    assert res.mudancas == [] and res.novas == [] and not res.primeira_execucao
    assert v2.para_dict() == antes  # mesmo histórico, mesma data da primeira entrada


def test_transicao_aprovada_para_execucao(config, tmp_path):
    antes = verba(status="aprovada", fonte_status="Proposta/Plano de Trabalho Aprovado")
    rodar([antes], None, config, tmp_path, data=ONTEM)
    agora = verba(status="execucao", fonte_status="Em execução")
    _, res = rodar([agora], publicar(antes), config, tmp_path)
    assert res.mudancas == [agora.id] and res.perdas_novas == [] and agora.perda is None
    assert [(e.data, e.de, e.para) for e in agora.historico] == [(ONTEM, None, "aprovada"), (DATA, "aprovada", "execucao")]
    assert agora.historico[1].nota == "Situação na fonte: Proposta/Plano de Trabalho Aprovado → Em execução"


def test_transicao_execucao_para_perdida_cria_a_perda_o_valor_e_o_pedido_de_curadoria(config, tmp_path):
    antes = verba(status="execucao", valor_contrapartida=10_000_00, valor_liberado=30_000_00)
    rodar([antes], None, config, tmp_path, data=ONTEM)
    agora = verba(status="perdida", fonte_status="Convênio Anulado", valor_contrapartida=10_000_00, valor_liberado=30_000_00, valor_devolvido=5_000_00)
    _, res = rodar([agora], publicar(antes), config, tmp_path)
    assert res.mudancas == res.perdas_novas == res.precisam_curadoria == [agora.id]
    assert [(e.de, e.para) for e in agora.historico] == [(None, "execucao"), ("execucao", "perdida")]
    p = agora.perda
    # repasse = 100.000 - 10.000 de contrapartida = 90.000; não liberado = 90.000 - 30.000 = 60.000; mais 5.000 devolvidos
    assert p.valor_perdido == 65_000_00
    assert (p.categoria, p.evitavel, p.citacoes, p.gerado_por_ia, p.revisado_por, p.revisado_em) == ("em_apuracao", "indeterminado", [], False, None, None)
    assert p.texto == config.regras.curadoria.texto_em_apuracao and p.data == DATA  # sem data na fonte: a da detecção
    assert not list(VALIDADOR.iter_errors(agora.para_dict()))


def test_mudanca_so_na_situacao_da_fonte_registra_entrada_com_o_mesmo_status_do_site(config, tmp_path):
    antes = verba(status="proposta", fonte_status="Proposta/Plano de Trabalho Enviado para Análise")
    rodar([antes], None, config, tmp_path, data=ONTEM)
    agora = verba(status="proposta", fonte_status="Proposta/Plano de Trabalho em Análise")
    _, res = rodar([agora], publicar(antes), config, tmp_path)
    assert res.mudancas == [agora.id]
    e = agora.historico[-1]
    assert (e.de, e.para) == ("proposta", "proposta") and e.nota == "Situação na fonte: Proposta/Plano de Trabalho Enviado para Análise → Proposta/Plano de Trabalho em Análise"


def test_mapeamento_atualizado_sem_mudar_a_situacao_da_fonte_tem_nota_propria(config, tmp_path):
    antes = verba(status=None, fonte_status="Inadimplente")
    rodar([antes], None, config, tmp_path, data=ONTEM)
    agora = verba(status="perdida", fonte_status="Inadimplente")
    rodar([agora], publicar(antes), config, tmp_path)
    e = agora.historico[-1]
    assert (e.de, e.para, e.nota) == ("situacao_em_analise", "perdida", "Mapeamento da situação atualizado")


def perda_curada_publicada(verba_id: str) -> Perda:
    citacao = {"n": 1, "documento_id": "d", "titulo": "Documento", "url": "https://exemplo.gov.br/d", "trecho": "Convênio Anulado"}
    return Perda(categoria="cauc", texto="Texto revisado [1].", citacoes=[citacao], evitavel="sim", data=ONTEM, valor_perdido=1, gerado_por_ia=True, revisado_por="Revisora", revisado_em=ONTEM)


def test_perda_ja_existente_mantem_data_e_valor_mas_o_motivo_so_vem_de_dados_curadoria(config, tmp_path):
    antes = verba(status="perdida", fonte_status="Convênio Anulado", perda=perda_curada_publicada("x").model_dump(mode="json"))  # publicada com motivo
    agora = verba(status="perdida", fonte_status="Convênio Anulado", valor_devolvido=99)
    _, res = rodar([agora], publicar(antes), config, tmp_path)  # sem arquivo em dados/curadoria/
    assert res.perdas_novas == [] and res.mudancas == [] and res.precisam_curadoria == [agora.id]
    assert (agora.perda.data, agora.perda.valor_perdido) == (ONTEM, 1)  # da detecção, não recalculados
    assert agora.perda.categoria == "em_apuracao" and agora.perda.citacoes == [] and agora.perda.revisado_por is None  # o motivo do JSON anterior não vale
    assert agora.perda.texto == config.regras.curadoria.texto_em_apuracao
    assert antes.perda is not None and agora.perda is not antes.perda  # cópia, não o mesmo objeto

    segunda = verba(status="perdida", fonte_status="Convênio Anulado")
    grava_curadoria(tmp_path, segunda.id, CURADORIA.format(id=segunda.id))
    _, res = rodar([segunda], publicar(antes), config, tmp_path)  # agora com o arquivo de curadoria
    assert res.precisam_curadoria == [] and segunda.perda.categoria == "cauc" and segunda.perda.revisado_por == "Revisora"
    assert (segunda.perda.data, segunda.perda.valor_perdido) == (ONTEM, 1)


def test_publicado_anterior_editado_a_mao_com_motivo_sem_citacao_para_o_pipeline(tmp_path):
    adulterada = verba(status="perdida", fonte_status="Convênio Anulado", perda=perda_curada_publicada("x").model_dump(mode="json")).para_dict()
    adulterada["perda"]["citacoes"] = []  # alguém apagou as citações do verbas.json versionado
    grava_publicado(tmp_path, json.dumps({"versao": 1, "verbas": [adulterada]}))
    with pytest.raises(ValueError, match="(?s)inválida no publicado anterior.*citação"):
        h.carregar_anterior(tmp_path)


def test_publicado_anterior_com_motivo_sem_revisao_tambem_para_o_pipeline(tmp_path):
    adulterada = verba(status="perdida", fonte_status="Convênio Anulado", perda=perda_curada_publicada("x").model_dump(mode="json")).para_dict()
    adulterada["perda"].update(revisado_por=None, revisado_em=None)  # "gerado por IA" sem revisão humana
    grava_publicado(tmp_path, json.dumps({"versao": 1, "verbas": [adulterada]}))
    with pytest.raises(ValueError, match="revisado_por"):
        h.carregar_anterior(tmp_path)


def test_perda_revertida_some_e_o_historico_registra_a_volta(config, tmp_path):
    antes = verba(status="perdida", fonte_status="Convênio Anulado")
    rodar([antes], None, config, tmp_path, data=ONTEM)
    agora = verba(status="execucao", fonte_status="Em execução")
    rodar([agora], publicar(antes), config, tmp_path)
    assert agora.perda is None and "perda" not in agora.para_dict()
    assert (agora.historico[-1].de, agora.historico[-1].para) == ("perdida", "execucao")


def test_verba_nova_depois_da_primeira_execucao_diz_que_apareceu(config, tmp_path):
    velha, nova = verba("transferegov_discricionarias-1"), verba("transferegov_discricionarias-2")
    rodar([velha], None, config, tmp_path, data=ONTEM)
    _, res = rodar([velha, nova], publicar(velha), config, tmp_path)
    assert res.novas == [nova.id] and not res.primeira_execucao
    assert nova.historico[0].nota == "Verba apareceu nas fontes" and nova.historico[0].de is None


def test_verba_que_some_das_fontes_vai_para_os_avisos_e_nao_e_publicada(config, tmp_path):
    a, b = verba("transferegov_discricionarias-1"), verba("transferegov_discricionarias-2")
    rodar([a, b], None, config, tmp_path, data=ONTEM)
    n, res = rodar([verba("transferegov_discricionarias-1")], publicar(a, b), config, tmp_path)
    assert res.desaparecidas == [b.id] and [v.id for v in n.verbas] == [a.id]
    assert any("não saíram das fontes" in x and b.id in x for x in res.avisos)


# --- valor_perdido -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "esperado"),
    [
        ({}, 100_000_00),  # nada liberado: tudo
        ({"valor_contrapartida": 25_000_00}, 75_000_00),  # a contrapartida do município não é perda
        ({"valor_liberado": 40_000_00}, 60_000_00),
        ({"valor_liberado": 40_000_00, "valor_devolvido": 7_00}, 60_007_00),  # R$ 60.000,00 não liberados + R$ 7,00 devolvidos
        ({"valor_liberado": 100_000_00}, 0),  # liberou tudo e não devolveu: nada a perder
        ({"valor_liberado": 100_000_00, "valor_devolvido": 12_345}, 12_345),  # devolução soma mesmo sem saldo não liberado
        ({"valor_liberado": 150_000_00}, 0),  # liberado acima do repasse (arredondamento da fonte): nunca negativo
        ({"valor_contrapartida": 150_000_00}, 0),
    ],
)
def test_valor_perdido(kw, esperado):
    valor, aviso = h.valor_perdido(verba(status="perdida", **kw))
    assert valor == esperado and aviso is None


def test_valor_perdido_sem_valor_total_so_conta_o_devolvido_e_avisa(config, tmp_path):
    v = verba(status="perdida", valor_total=None, valor_devolvido=5_00)
    _, res = rodar([v], None, config, tmp_path)
    assert v.perda.valor_perdido == 5_00 and any("valor_total ausente" in a for a in res.avisos)


# --- pedidos de curadoria ----------------------------------------------------------------------


CITACAO_YAML = """  - n: 1
    documento_id: cauc-2026-10-29
    titulo: "CAUC: situação do município em 29/10/2026"
    url: https://exemplo.gov.br/cauc.csv
    trecho: "4.2 Regularidade"
"""
CURADORIA = (
    "verba_id: {id}\ncategoria: cauc\ntexto: A prefeitura não comprovou a regularidade exigida [1].\nevitavel: sim\n"
    "citacoes:\n" + CITACAO_YAML + "gerado_por_ia: true\nrevisado_por: Revisora\nrevisado_em: 2026-10-30\n"
)


def grava_curadoria(raiz: Path, verba_id: str, conteudo: str) -> None:
    (raiz / "dados" / "curadoria").mkdir(parents=True, exist_ok=True)
    (raiz / "dados" / "curadoria" / f"{verba_id}.yaml").write_text(conteudo, encoding="utf-8")


def test_so_perdas_sem_arquivo_de_curadoria_pedem_curadoria(config, tmp_path):
    a, b = verba("transferegov_discricionarias-1", status="perdida"), verba("transferegov_discricionarias-2", status="perdida")
    grava_curadoria(tmp_path, a.id, CURADORIA.format(id=a.id))
    _, res = rodar([a, b, verba("transferegov_discricionarias-3")], None, config, tmp_path)
    assert res.perdas_novas == [a.id, b.id] and res.precisam_curadoria == [b.id]  # a perda de `a` já foi curada
    assert (a.perda.categoria, a.perda.revisado_por, a.perda.gerado_por_ia) == ("cauc", "Revisora", True)
    assert a.perda.citacoes[0].documento_id == "cauc-2026-10-29"
    assert a.perda.data and a.perda.valor_perdido is not None  # data e valor continuam do pipeline
    assert b.perda.categoria == "em_apuracao" and b.perda.revisado_por is None


def test_curadoria_invalida_para_o_pipeline(config, tmp_path):
    from nucleo.curadoria_revisada import CuradoriaErro

    a = verba("transferegov_discricionarias-1", status="perdida")
    grava_curadoria(tmp_path, a.id, "categoria: cauc\n")
    with pytest.raises(CuradoriaErro):
        rodar([a], None, config, tmp_path)


def test_motivo_de_perda_sem_citacao_so_vale_como_em_apuracao(config, tmp_path):
    from nucleo.curadoria_revisada import CuradoriaErro

    a = verba("transferegov_discricionarias-1", status="perdida")
    grava_curadoria(tmp_path, a.id, CURADORIA.format(id=a.id).replace(CITACAO_YAML, "").replace("citacoes:\n", "citacoes: []\n"))
    with pytest.raises(CuradoriaErro, match="sem citação"):
        rodar([a], None, config, tmp_path)


def curadoria_em_apuracao(verba_id: str, texto: str, evitavel: str = "indeterminado", citacoes: str = "citacoes: []\n") -> str:
    return f"verba_id: {verba_id}\ncategoria: em_apuracao\ntexto: {texto}\nevitavel: {evitavel}\n{citacoes}gerado_por_ia: false\nrevisado_por: Revisora\nrevisado_em: 2026-10-30\n"


@pytest.mark.parametrize(
    "texto, evitavel, citacoes",
    [
        ("A prefeitura foi omissa e deixou o prazo vencer.", "indeterminado", "citacoes: []\n"),  # texto livre sem documento
        ("Motivo em apuração. Ainda não encontramos documento oficial que explique esta perda.", "sim", "citacoes: []\n"),  # acusa sem documento
        ("Motivo em apuração. Ainda não encontramos documento oficial que explique esta perda.", "indeterminado", "citacoes:\n" + CITACAO_YAML),  # texto padrão com citação solta
    ],
)
def test_em_apuracao_so_publica_o_texto_padrao_sem_citacao_e_indeterminado(config, tmp_path, texto, evitavel, citacoes):
    from nucleo.curadoria_revisada import CuradoriaErro

    a = verba("transferegov_discricionarias-1", status="perdida")
    grava_curadoria(tmp_path, a.id, curadoria_em_apuracao(a.id, texto, evitavel, citacoes))
    with pytest.raises(CuradoriaErro, match="em_apuracao"):
        rodar([a], None, config, tmp_path)


def test_em_apuracao_com_o_texto_padrao_e_aceita_e_continua_em_apuracao(config, tmp_path):
    a = verba("transferegov_discricionarias-1", status="perdida")
    padrao = config.regras.curadoria.texto_em_apuracao
    grava_curadoria(tmp_path, a.id, curadoria_em_apuracao(a.id, f'"{padrao}"'))
    _, res = rodar([a], None, config, tmp_path)
    assert res.precisam_curadoria == [] and a.perda.categoria == "em_apuracao" and a.perda.texto == padrao and a.perda.citacoes == []


# --- leitura do publicado anterior -------------------------------------------------------------


def grava_publicado(raiz: Path, conteudo: str) -> Path:
    caminho = raiz / h.ARQUIVO_PUBLICADO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_sem_publicado_anterior_e_primeira_execucao(tmp_path):
    assert h.carregar_anterior(tmp_path) is None


def test_carrega_o_publicado_anterior_por_id(tmp_path):
    v = verba()
    grava_publicado(tmp_path, json.dumps({"gerado_em": "2026-10-29", "verbas": [v.para_dict()]}))
    anterior = h.carregar_anterior(tmp_path)
    assert set(anterior) == {v.id} and anterior[v.id].status_site == "execucao"


@pytest.mark.parametrize("conteudo", ["{ nao e json", json.dumps({"sem_verbas": []}), json.dumps([1, 2]), ""])
def test_publicado_ilegivel_para_o_pipeline_em_vez_de_recomecar_o_historico(tmp_path, conteudo):
    grava_publicado(tmp_path, conteudo)
    with pytest.raises(ValueError, match="o histórico não será recomeçado"):
        h.carregar_anterior(tmp_path)


def test_verba_invalida_no_publicado_para_e_diz_qual(tmp_path):
    ruim = verba().para_dict()
    ruim["tipo"] = "inventado"
    grava_publicado(tmp_path, json.dumps({"verbas": [ruim]}))
    with pytest.raises(ValueError, match="transferegov_discricionarias-1.*inválida"):
        h.carregar_anterior(tmp_path)


# --- dados reais -------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reais():
    return carregar_retratos(RAIZ, DATA)


def test_dados_reais_primeira_execucao(reais, config, tmp_path):
    res = normalizar(reais, config, DATA)
    r = h.aplicar_historico(res, None, DATA, config, tmp_path, reais)
    assert r.primeira_execucao and len(r.novas) == 46 and r.mudancas == [] and r.desaparecidas == [] and r.avisos == []
    assert all(len(v.historico) == 1 and v.historico[0].de is None for v in res.verbas)
    assert len(r.perdas_novas) == 8 == len(r.precisam_curadoria)


def test_dados_reais_as_oito_perdas_tem_a_data_e_o_valor_da_fonte(reais, config, tmp_path):
    res = normalizar(reais, config, DATA)
    h.aplicar_historico(res, None, DATA, config, tmp_path, reais)
    perdas = {v.id.split("-")[1]: v.perda for v in res.verbas if v.perda}
    assert {k: (p.data.isoformat(), p.valor_perdido) for k, p in perdas.items()} == {
        "1981768": ("2025-01-21", 70_000_000), "2065616": ("2026-01-14", 70_000_000), "2079956": ("2026-01-14", 85_000_000),
        "2113195": ("2026-03-05", 37_342_860), "2113259": ("2026-03-05", 54_950_000), "2113295": ("2026-03-05", 34_800_000),
        "2152076": ("2026-03-24", 58_000_000), "2152082": ("2026-03-24", 56_000_000),
    }  # data do evento no Siconv e repasse sem a contrapartida (R$ 700.750,00 de valor total -> R$ 700.000,00)
    assert sum(p.valor_perdido for p in perdas.values()) == 466_092_860
    assert all(p.categoria == "em_apuracao" and p.texto.startswith("Motivo em apuração") for p in perdas.values())


def test_dados_reais_todas_as_verbas_validam_no_schema_com_perda_e_historico(reais, config, tmp_path):
    res = normalizar(reais, config, DATA)
    h.aplicar_historico(res, None, DATA, config, tmp_path, reais)
    for v in res.verbas:
        assert not list(VALIDADOR.iter_errors(v.para_dict())), v.id


def test_dados_reais_segunda_execucao_a_partir_do_publicado_nao_muda_nada(reais, config, tmp_path):
    primeira = normalizar(reais, config, DATA)
    h.aplicar_historico(primeira, None, DATA, config, tmp_path, reais)
    grava_publicado(tmp_path, json.dumps({"verbas": [v.para_dict() for v in primeira.verbas]}))
    segunda = normalizar(reais, config, DATA + timedelta(days=1))
    r = h.aplicar_historico(segunda, h.carregar_anterior(tmp_path), DATA + timedelta(days=1), config, tmp_path, reais)
    assert r.novas == [] and r.mudancas == [] and r.perdas_novas == [] and not r.primeira_execucao
    assert [v.para_dict() for v in segunda.verbas] == [v.para_dict() for v in primeira.verbas]


# --- pipeline ----------------------------------------------------------------------------------


def test_pipeline_aplica_o_historico_e_imprime_as_perdas(capsys, raiz_sem_publicado):
    assert pipeline.main(["--data", "2026-10-30", "--raiz", str(raiz_sem_publicado), "--sem-publicar"]) == 0
    saida = capsys.readouterr().out
    assert "Histórico: primeira execução (sem publicado anterior); novas=46, com mudança=0, desaparecidas=0" in saida
    assert "Perdas novas: 8, valor perdido R$ 4,660,928.60; pedidos de curadoria: 8" in saida
    assert "transferegov_discricionarias-2113259 em 2026-03-05: R$ 549,500.00" in saida


def test_pipeline_processar_devolve_o_historico(config, raiz_sem_publicado):
    p = pipeline.processar(raiz_sem_publicado, DATA, config)
    assert p.historico.primeira_execucao and len(p.historico.perdas_novas) == 8
