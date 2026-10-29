import copy
import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from nucleo import normaliza as n
from nucleo.config import carregar_config

RAIZ = Path(__file__).resolve().parents[1]
DIA = date(2026, 10, 29)
CNPJ = "45145414000147"
SCHEMA = json.loads((RAIZ / "schemas" / "verba.schema.json").read_text(encoding="utf-8"))
VALIDADOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


@pytest.fixture(scope="module")
def reais():
    """Os retratos reais de 2026-10-29 (em dados/brutos/, que por regra nunca é editado)."""
    return n.carregar_retratos(RAIZ, DIA)


@pytest.fixture
def config():
    return carregar_config()


def real(reais):
    return copy.deepcopy(reais)


# --- utilidades --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("29/10/2026", date(2026, 10, 29)), ("2025-12-30", date(2025, 12, 30)), ("2025-12-30T00:00:00", date(2025, 12, 30)), ("", None), (None, None), ("  ", None)],
)
def test_data_br(texto, esperado):
    assert n.data_br(texto) == esperado


@pytest.mark.parametrize("texto", ["29-10-2026", "10/29/26", "ontem"])
def test_data_em_formato_desconhecido_e_erro(texto):
    with pytest.raises(ValueError, match="formato desconhecido"):
        n.data_br(texto)


def test_normalizar_numero_ignora_zeros_a_esquerda():
    assert n.normalizar_numero("04431/2016") == n.normalizar_numero("4431/2016") == "4431/2016"
    assert n.normalizar_numero("0044312016") == "44312016" and n.normalizar_numero(None) == ""


def test_resumo_corta_em_palavra_e_junta_espacos():
    assert n.resumo("  a   b\n c ") == "a b c"
    longo = "palavra " * 40
    r = n.resumo(longo, 30)
    assert len(r) <= 31 and r.endswith("…") and not r[:-1].endswith(" ") and "palavr…" not in r


# --- mapeamento de status ----------------------------------------------------------------------


def test_mapa_status_ignora_caixa_acento_e_espacos_extras(config):
    mapa = n.MapaStatus(config)
    assert mapa.mapear(n.CHAVE_SICONV_CONVENIO, "  PRESTACAO de   contas EM analise ", "x-1") == "prestacao"
    assert mapa.mapear(n.CHAVE_SICONV_PROPOSTA, "Proposta/Plano de Trabalho Rejeitados por Impedimento técnico", "x-2") == "perdida"
    assert mapa.nao_mapeadas() == []


def test_situacao_desconhecida_vira_none_e_entra_no_relatorio(config):
    mapa = n.MapaStatus(config)
    for i in range(5):
        assert mapa.mapear(n.CHAVE_SICONV_CONVENIO, "Inadimplente", f"v-{i}") is None
    assert mapa.mapear(n.CHAVE_SICONV_CONVENIO, "", "v-9") is None
    nao = mapa.nao_mapeadas()
    assert [(r.valor, len(r.verbas)) for r in nao] == [("(vazia)", 1), ("Inadimplente", 5)]
    texto = n.relatorio_nao_mapeadas(nao)
    assert "Situações não mapeadas: 2" in texto and "'Inadimplente': 5 verba(s) (v-0, v-1, v-2 e mais 2)" in texto
    assert n.relatorio_nao_mapeadas([]) == "Situações não mapeadas: nenhuma."


# --- leitura dos retratos ----------------------------------------------------------------------


def grava(raiz, fonte, dia, conteudo=None):
    pasta = raiz / "dados" / "brutos" / fonte
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{dia}.json").write_text(json.dumps(conteudo or {"data": dia, "marca": dia}), encoding="utf-8")


def test_carregar_retratos_usa_o_ultimo_valido_ate_a_data(tmp_path):
    for dia in ("2026-10-27", "2026-10-28", "2026-10-30"):
        grava(tmp_path, "cauc", dia)
    retratos = n.carregar_retratos(tmp_path, DIA)
    assert retratos["cauc"]["marca"] == "2026-10-28"  # o de 30/10 é do futuro; o do dia seguinte não vale
    assert retratos["obrasgov"] is None  # nunca coletada
    assert set(retratos) == set(n.FONTES_BRUTAS)


# --- dados reais -------------------------------------------------------------------------------


def test_normaliza_os_retratos_reais(reais, config):
    res = n.normalizar(reais, config, DIA)
    assert len(res.verbas) == 46
    assert Counter(v.fonte for v in res.verbas) == {"transferegov_discricionarias": 22, "transferegov_parcerias": 12, "siconv_programa": 10, "transferegov_fundoafundo": 2}
    assert Counter(v.tipo for v in res.verbas) == {"voluntaria": 20, "emenda_finalidade": 14, "programa_adesao": 10, "fundo_a_fundo": 2}
    assert Counter(v.status_site for v in res.verbas) == {"aprovada": 15, "oportunidade": 10, "perdida": 8, "proposta": 7, "execucao": 3, "prestacao": 3}
    assert res.nao_mapeadas == [] and res.avisos == []  # os valores observados nas POCs estão todos no status_map
    assert all(d == date(2026, 10, 29) for d in res.retratos.values())


def test_todas_as_verbas_reais_validam_no_schema_e_tem_id_unico_e_ordenado(reais, config):
    res = n.normalizar(reais, config, DIA)
    for v in res.verbas:
        erros = [f"{list(e.path)}: {e.message}" for e in VALIDADOR.iter_errors(v.para_dict())]
        assert not erros, (v.id, erros)
    ids = [v.id for v in res.verbas]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_resultado_e_deterministico(reais, config):
    a = [v.para_json() for v in n.normalizar(reais, config, DIA).verbas]
    b = [v.para_json() for v in n.normalizar(real(reais), config, DIA).verbas]
    assert a == b


def test_recorte_do_siconv_na_spec(reais, config):
    verbas = {v.id: v for v in n.normalizar(reais, config, DIA).verbas if v.fonte == "transferegov_discricionarias"}
    # proposta de 2009 com convênio ainda ativo (prestação de contas em análise) entra; encerradas e antigas, não
    assert "transferegov_discricionarias-88432" in verbas and verbas["transferegov_discricionarias-88432"].status_site == "prestacao"
    assert "transferegov_discricionarias-1733967" in verbas  # assinado em 2023, em execução até 2026
    assert all(v.status_site != "concluida" for v in verbas.values())  # as concluídas são antigas e inativas


def test_tipo_e_instrumento_seguem_a_regra_da_d12(reais, config):
    verbas = {v.id: v for v in n.normalizar(reais, config, DIA).verbas}
    termo = verbas["transferegov_discricionarias-2113518"]
    assert (termo.tipo, termo.instrumento) == ("voluntaria", "TERMO DE COMPROMISSO")  # termo de compromisso sem emenda
    com_emenda = verbas["transferegov_discricionarias-2175551"]
    assert com_emenda.tipo == "emenda_finalidade" and com_emenda.parlamentar  # tem linha em siconv_emenda
    assert verbas["transferegov_discricionarias-1733967"].instrumento == "CONTRATO DE REPASSE"


def test_valores_em_centavos_e_portal_atualiza_o_liberado(reais, config):
    verbas = {v.id: v for v in n.normalizar(reais, config, DIA).verbas}
    v = verbas["transferegov_discricionarias-2031354"]
    assert v.valor_total == 341_125_000 and v.valor_contrapartida == 16_125_000  # R$ 3.411.250,00 e R$ 161.250,00
    assert v.valor_liberado == 93_875_879  # R$ 938.758,79: Portal (R$ 288.758,79 do Siconv + R$ 650.000,00 de 23/07/2026)
    assert [f.nome for f in v.fontes] == ["Transferegov — Discricionárias e Legais (carga de 17/07/2026)", "Portal da Transparência", "Obrasgov"]
    assert v.numero_instrumento == "970941"


def test_estorno_vira_valor_devolvido(reais, config):
    verbas = {v.id: v for v in n.normalizar(reais, config, DIA).verbas}
    assert verbas["transferegov_discricionarias-199153"].valor_devolvido == 125  # VL_SALDO_REMAN_TESOURO: valores devolvidos ao Tesouro
    assert verbas["transferegov_discricionarias-496746"].valor_devolvido == 21562


def test_prazos_do_convenio(reais, config):
    p = {v.id: v for v in n.normalizar(reais, config, DIA).verbas}["transferegov_discricionarias-2031354"].prazos
    assert (p.proposta, p.assinatura, p.fim_vigencia, p.prestacao_contas) == (date(2024, 11, 26), date(2024, 12, 13), date(2028, 9, 13), date(2028, 11, 12))


def test_oportunidades_reais(reais, config):
    ops = [v for v in n.normalizar(reais, config, DIA).verbas if v.fonte == "siconv_programa"]
    assert len(ops) == 10
    for v in ops:
        assert (v.status_site, v.tipo, v.valor_total, v.status_fonte) == ("oportunidade", "programa_adesao", None, "DISPONIBILIZADO")
        assert v.prazos.adesao >= DIA and v.em_risco is False
        assert "carga de 17/07/2026" in v.fontes[0].nome


def test_parcerias_e_fundoafundo_reais(reais, config):
    verbas = n.normalizar(reais, config, DIA).verbas
    parcerias = [v for v in verbas if v.fonte == "transferegov_parcerias"]
    assert len(parcerias) == 12 and {(v.tipo, v.status_site, v.status_fonte) for v in parcerias} == {("emenda_finalidade", "aprovada", "Aprovada")}
    assert all(v.valor_total and v.numero_instrumento for v in parcerias)
    faf = [v for v in verbas if v.fonte == "transferegov_fundoafundo"]
    assert len(faf) == 2 and {(v.tipo, v.status_site, v.status_fonte) for v in faf} == {("fundo_a_fundo", "aprovada", "AUTORIZADO")}
    assert {v.id: (v.valor_total, v.prazos.fim_vigencia) for v in faf} == {
        "transferegov_fundoafundo-13785": (9_167_394, date(2024, 12, 31)),  # Lei Paulo Gustavo, R$ 91.673,94
        "transferegov_fundoafundo-27864": (32_084_028, date(2029, 12, 31)),  # Aldir Blanc 2025, R$ 320.840,28
    }
    assert {v.valor_total for v in parcerias} == {5_000_000, 10_000_000, 20_000_000}  # R$ 50 mil, 100 mil e 200 mil: os valores das emendas


def test_situacao_nova_no_siconv_vira_status_nulo_e_vai_ao_relatorio(reais, config):
    r = real(reais)
    for c in r["transferegov_discricionarias"]["dados"]["convenio"]:
        if c["ID_PROPOSTA"] == "2031354":
            c["SIT_CONVENIO"] = "Situação Criada Agora"
    res = n.normalizar(r, config, DIA)
    v = {x.id: x for x in res.verbas}["transferegov_discricionarias-2031354"]
    assert v.status_site is None and v.status_fonte == "Situação Criada Agora"  # o status original é preservado
    assert [(x.fonte, x.campo, x.valor, x.verbas) for x in res.nao_mapeadas] == [(n.CHAVE_SICONV_CONVENIO, "SIT_CONVENIO", "Situação Criada Agora", ["transferegov_discricionarias-2031354"])]
    assert not list(VALIDADOR.iter_errors(v.para_dict()))  # a verba segue válida, só sem status do site


# --- linha de comando --------------------------------------------------------------------------


def test_cli_imprime_resumo_e_relatorio_de_nao_mapeadas(capsys):
    assert n.main(["--data", "2026-10-29"]) == 0
    saida = capsys.readouterr().out
    assert "Normalização de 2026-10-29: 46 verbas" in saida
    assert "transferegov_discricionarias=2026-10-29" in saida and "SEM RETRATO" not in saida
    assert "por tipo: voluntaria=20" in saida and "por status: aprovada=15" in saida
    assert "Situações não mapeadas: nenhuma." in saida and "AVISO" not in saida


def test_cli_sem_retratos_avisa_em_vez_de_falhar(tmp_path, capsys):
    assert n.main(["--data", "2026-10-29", "--raiz", str(tmp_path)]) == 0
    saida = capsys.readouterr().out
    assert "0 verbas" in saida and "SEM RETRATO" in saida and saida.count("AVISO") == 2  # Siconv e Transferegov API


# --- fontes ausentes ---------------------------------------------------------------------------


def test_sem_siconv_nao_cria_verbas_do_siconv_nem_usa_o_portal_no_lugar(reais, config):
    r = real(reais)
    r["transferegov_discricionarias"] = None
    res = n.normalizar(r, config, DIA)
    assert Counter(v.fonte for v in res.verbas) == {"transferegov_parcerias": 12, "transferegov_fundoafundo": 2}
    assert any("Siconv sem nenhum retrato" in a for a in res.avisos)


def test_sem_portal_e_sem_obrasgov_so_avisa(reais, config):
    r = real(reais)
    r["portal_transparencia"] = r["obrasgov"] = None
    res = n.normalizar(r, config, DIA)
    assert len(res.verbas) == 46
    assert {v.id: v for v in res.verbas}["transferegov_discricionarias-2031354"].valor_liberado == 28_875_879  # volta ao do Siconv
    assert any("Portal" in a for a in res.avisos) and any("Obrasgov" in a for a in res.avisos)


def test_sem_transferegov_api_so_avisa(reais, config):
    r = real(reais)
    r["transferegov_api"] = None
    res = n.normalizar(r, config, DIA)
    assert Counter(v.fonte for v in res.verbas) == {"transferegov_discricionarias": 22, "siconv_programa": 10}
    assert any("Transferegov API sem nenhum retrato" in a for a in res.avisos)


def test_emenda_pix_com_registros_gera_aviso_porque_ainda_nao_e_tratada(reais, config):
    r = real(reais)
    r["transferegov_api"]["dados"]["especiais.planos_acao"] = [{"id_plano_acao": 1}]
    assert any("especiais.planos_acao tem 1 registro" in a for a in n.normalizar(r, config, DIA).avisos)


# --- junção com o Portal -----------------------------------------------------------------------


def convenio_portal(id_, numero, processo, liberado, **extra):
    return {"id": id_, "dimConvenio": {"numero": numero}, "numeroProcesso": processo, "valorLiberado": liberado, **extra}


def com_portal(reais, convenios):
    r = real(reais)
    r["portal_transparencia"]["dados"]["convenios"] = convenios
    return r


def verba_2031354(res):
    return {v.id: v for v in res.verbas}["transferegov_discricionarias-2031354"]


def test_portal_casa_so_pelo_processo_quando_o_numero_nao_bate(reais, config):
    # NR_PROPOSTA do Siconv é 33961/2024; o Portal chama de outro número, mas o processo é o mesmo
    r = com_portal(reais, [convenio_portal(1, "99999/2024", "0339612024", 111.11)])
    v = verba_2031354(n.normalizar(r, config, DIA))
    assert v.valor_liberado == 11_111 and [f.nome for f in v.fontes].count("Portal da Transparência") == 1


def test_portal_casa_so_pelo_numero_com_zeros_diferentes(reais, config):
    r = com_portal(reais, [convenio_portal(1, "033961/2024", "processo-diferente", 222.22)])
    assert verba_2031354(n.normalizar(r, config, DIA)).valor_liberado == 22_222


def test_portal_ambiguo_nao_e_usado_e_gera_aviso(reais, config):
    r = com_portal(reais, [convenio_portal(1, "33961/2024", "x", 1.0), convenio_portal(2, "outro", "339612024", 2.0)])
    res = n.normalizar(r, config, DIA)
    assert verba_2031354(res).valor_liberado == 28_875_879  # ficou o do Siconv
    assert any("2 convênios casam com transferegov_discricionarias-2031354" in a for a in res.avisos)


def test_portal_que_casa_com_duas_verbas_so_vale_para_a_primeira(reais, config):
    r = com_portal(reais, [convenio_portal(7, "33961/2024", "339612024", 5.0)])
    # a mesma chave também aparece em outra proposta do Siconv: duplica NR_PROPOSTA de 2113518 e o processo
    for c in r["transferegov_discricionarias"]["dados"]["convenio"]:
        if c["ID_PROPOSTA"] == "2113518":
            c["NR_PROCESSO"] = "339612024"
    res = n.normalizar(r, config, DIA)
    assert any("convênio 7 casa com" in a for a in res.avisos)
    assert [v.id for v in res.verbas if any(f.nome == "Portal da Transparência" for f in v.fontes)] == ["transferegov_discricionarias-2031354"]


def test_portal_com_liberado_menor_que_o_do_siconv_avisa_mas_usa_o_do_portal(reais, config):
    r = com_portal(reais, [convenio_portal(1, "33961/2024", "339612024", 1000.0)])
    res = n.normalizar(r, config, DIA)
    assert verba_2031354(res).valor_liberado == 100_000
    assert any("menor que o do Siconv" in a for a in res.avisos)


# --- junção com o Obrasgov ---------------------------------------------------------------------


def com_execucao(reais, registros):
    r = real(reais)
    r["obrasgov"]["dados"]["execucao_fisica"] = registros
    return r


def test_obrasgov_usa_o_percentual_da_atualizacao_mais_recente(reais, config):
    id_projeto = "47960.35-00"  # ligado ao convênio 970941 (verba 2031354) pela ponte
    r = com_execucao(reais, [
        {"id_projeto_investimento": id_projeto, "percentual_execucao_fisica": 10.0, "dt_atualizacao_execucao": "2026-01-10", "dt_cadastro_execucao": "2025-01-01"},
        {"id_projeto_investimento": id_projeto, "percentual_execucao_fisica": 35.5, "dt_atualizacao_execucao": "2026-06-30", "dt_cadastro_execucao": "2025-01-01"},
        {"id_projeto_investimento": id_projeto, "percentual_execucao_fisica": 20.0, "dt_atualizacao_execucao": "2026-03-01", "dt_cadastro_execucao": "2025-01-01"},
    ])
    assert verba_2031354(n.normalizar(r, config, DIA)).execucao_fisica_pct == 35.5


def test_obrasgov_sem_registro_de_execucao_nao_inventa_percentual(reais, config):
    v = verba_2031354(n.normalizar(reais, config, DIA))
    assert v.execucao_fisica_pct is None and "execucao_fisica_pct" not in v.para_dict()  # ausência de dado não é 0%
    assert "Obrasgov" in [f.nome for f in v.fontes]  # a obra foi ligada, só não tem medição


def test_obrasgov_projeto_de_outro_executor_e_ignorado_com_aviso(reais, config):
    r = real(reais)
    for p in r["obrasgov"]["dados"]["projeto_investimento"]:
        if p["id_projeto_investimento"] == "47960.35-00":
            p["executores"] = [{"cnpj_executor": "11111111000111"}]
    res = n.normalizar(r, config, DIA)
    assert "Obrasgov" not in [f.nome for f in verba_2031354(res).fontes]
    assert any("não tem a prefeitura como executora" in a for a in res.avisos)


# --- oportunidades -----------------------------------------------------------------------------


def linha_programa(id_, **kw):
    base = {
        "ID_PROGRAMA": id_, "COD_PROGRAMA": f"COD{id_}", "NOME_PROGRAMA": f"Programa {id_}", "SIT_PROGRAMA": "DISPONIBILIZADO",
        "DESC_ORGAO_SUP_PROGRAMA": "MINISTERIO TESTE", "MODALIDADE_PROGRAMA": "CONVENIO",
        "DT_PROG_INI_RECEB_PROP": "", "DT_PROG_FIM_RECEB_PROP": "", "DT_PROG_INI_EMENDA_PAR": "", "DT_PROG_FIM_EMENDA_PAR": "",
        "DT_PROG_INI_BENEF_ESP": "", "DT_PROG_FIM_BENEF_ESP": "",
    }
    return {**base, **kw}


def oportunidades(reais, config, linhas, dirigidos=()):
    r = real(reais)
    r["transferegov_discricionarias"]["dados"]["programa"] = linhas
    r["transferegov_discricionarias"]["dados"]["programa_proponentes"] = [{"ID_PROGRAMA": i, "ID_PROPONENTE": "15310"} for i in dirigidos]
    return [v for v in n.normalizar(r, config, DIA).verbas if v.fonte == "siconv_programa"]


def test_oportunidade_so_com_janela_de_propostas_aberta(reais, config):
    ops = oportunidades(reais, config, [
        linha_programa("1", DT_PROG_FIM_RECEB_PROP="31/12/2026"),  # entra
        linha_programa("2", DT_PROG_FIM_RECEB_PROP="28/10/2026"),  # encerrou ontem
        linha_programa("3", DT_PROG_INI_RECEB_PROP="30/10/2026", DT_PROG_FIM_RECEB_PROP="31/12/2026"),  # ainda não abriu
        linha_programa("4", DT_PROG_FIM_EMENDA_PAR="31/12/2026"),  # só emenda: precisa de emenda indicada, fora
        linha_programa("5", SIT_PROGRAMA="CADASTRADO", DT_PROG_FIM_RECEB_PROP="31/12/2026"),
        linha_programa("6", SIT_PROGRAMA="INATIVO", DT_PROG_FIM_RECEB_PROP="31/12/2026"),
    ])
    assert [v.id_fonte for v in ops] == ["1"]


def test_programa_dirigido_a_prefeitura_entra_com_qualquer_janela_aberta(reais, config):
    linhas = [linha_programa("7", DT_PROG_FIM_BENEF_ESP="15/11/2026"), linha_programa("8", DT_PROG_FIM_BENEF_ESP="15/11/2026")]
    assert [v.id_fonte for v in oportunidades(reais, config, linhas, dirigidos=["7"])] == ["7"]


def test_prazo_de_adesao_e_o_fim_da_janela_aberta_mais_proxima_e_programa_repetido_vale_um(reais, config):
    linhas = [
        linha_programa("9", DT_PROG_FIM_RECEB_PROP="31/12/2026", DT_PROG_FIM_BENEF_ESP="20/11/2026"),
        linha_programa("9", DT_PROG_FIM_RECEB_PROP="31/12/2026"),  # a tabela repete o programa por UF/natureza
    ]
    (v,) = oportunidades(reais, config, linhas, dirigidos=["9"])
    assert v.prazos.adesao == date(2026, 11, 20)  # a janela de beneficiário específico acaba antes


def test_programa_sem_valor_publica_valor_nulo_e_nao_zero(reais, config):
    (v,) = oportunidades(reais, config, [linha_programa("10", DT_PROG_FIM_RECEB_PROP="31/12/2026")])
    assert v.valor_total is None and v.para_dict()["valor_total"] is None
    assert not list(VALIDADOR.iter_errors(v.para_dict()))


# --- parcerias e fundo a fundo -----------------------------------------------------------------


def test_parceria_mais_adiantada_define_o_status_e_o_tipo_vem_do_programa(reais, config):
    r = real(reais)
    d = r["transferegov_api"]["dados"]
    proposta = d["parcerias.proposta"][0]
    proposta["situacao_proposta"] = "Em Análise"  # proposta ainda não mapeada...
    for p in d["parcerias.parceria"]:
        if p["id_proposta"] == proposta["id_proposta"]:
            p["in_situacao_parceria"] = "Aprovada"  # ...mas a parceria já foi aprovada
    for programa in d["parcerias.programa"]:
        if programa["id_programa"] == proposta["id_programa"]:
            programa["qualificacao_beneficiario"] = "Beneficiário Espontâneo"
    res = n.normalizar(r, config, DIA)
    v = {x.id: x for x in res.verbas}[f"transferegov_parcerias-{proposta['id_proposta']}"]
    assert (v.status_site, v.status_fonte, v.tipo) == ("aprovada", "Aprovada", "fundo_a_fundo")
    assert res.nao_mapeadas == []


def test_parcerias_anteriores_ao_recorte_ficam_de_fora(reais, config):
    r = real(reais)
    r["transferegov_api"]["dados"]["parcerias.proposta"][0]["dt_proposta"] = "2023-12-31"
    res = n.normalizar(r, config, DIA)
    assert sum(1 for v in res.verbas if v.fonte == "transferegov_parcerias") == 11


def test_plano_do_fundoafundo_so_entra_se_a_vigencia_toca_o_recorte(reais, config):
    r = real(reais)
    plano = r["transferegov_api"]["dados"]["fundoafundo.planos_acao"][0]
    plano["data_inicio_vigencia_plano_acao"], plano["data_fim_vigencia_plano_acao"] = "2020-01-01", "2023-12-31"
    res = n.normalizar(r, config, DIA)
    assert sum(1 for v in res.verbas if v.fonte == "transferegov_fundoafundo") == 1


def test_id_repetido_e_erro(reais, config):
    r = real(reais)
    r["transferegov_discricionarias"]["dados"]["proposta"].append(copy.deepcopy(r["transferegov_discricionarias"]["dados"]["proposta"][0]))
    r["transferegov_discricionarias"]["dados"]["proposta"][-1]["DIA_PROPOSTA"] = "01/06/2025"
    r["transferegov_discricionarias"]["dados"]["proposta"][0]["DIA_PROPOSTA"] = "01/06/2025"
    with pytest.raises(ValueError, match="ids de verba repetidos"):
        n.normalizar(r, config, DIA)
