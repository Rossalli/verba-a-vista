"""T3.1: montagem do dossiê das perdas reais (retratos de 29/10/2026)."""

from datetime import date

import pytest

from curadoria.dossie import Documento, montar_dossie
from nucleo.config import carregar_config
from nucleo.pipeline import processar

IDS_PERDAS = [
    "transferegov_discricionarias-1981768",
    "transferegov_discricionarias-2065616",
    "transferegov_discricionarias-2079956",
    "transferegov_discricionarias-2113195",
    "transferegov_discricionarias-2113259",
    "transferegov_discricionarias-2113295",
    "transferegov_discricionarias-2152076",
    "transferegov_discricionarias-2152082",
]


@pytest.fixture(scope="module")
def proc(raiz_sem_publicado):
    return processar(raiz_sem_publicado, date(2026, 10, 30))


@pytest.fixture(scope="module")
def urls():
    fontes = carregar_config().fontes.fontes
    return {chave: fontes[chave].url or fontes[chave].base_url for chave in ("transferegov_discricionarias", "cauc", "obrasgov")}


def dossie_de(proc, raiz, urls, verba_id):
    verba = next(v for v in proc.normalizacao.verbas if v.id == verba_id)
    return montar_dossie(verba, proc.retratos, raiz, urls)


def test_as_oito_perdas_reais_tem_dossie(proc, raiz_sem_publicado, urls):
    perdidas = sorted(v.id for v in proc.normalizacao.verbas if v.status_site == "perdida")
    assert perdidas == IDS_PERDAS
    for verba_id in IDS_PERDAS:
        dossie = dossie_de(proc, raiz_sem_publicado, urls, verba_id)
        ids = [d.id for d in dossie.documentos]
        assert dossie.verba_id == verba_id
        assert ids[0].startswith("instrumento-")
        assert ids[1].startswith("historico-situacao-")
        assert ids[2].startswith("cauc-")


def test_documentos_trazem_todos_os_campos_exigidos(proc, raiz_sem_publicado, urls):
    dossie = dossie_de(proc, raiz_sem_publicado, urls, IDS_PERDAS[0])
    for doc in dossie.documentos:
        assert isinstance(doc, Documento)
        assert doc.titulo and doc.url.startswith("http") and doc.texto
        assert doc.data_coleta.startswith("2026-10-")
    assert len({d.id for d in dossie.documentos}) == len(dossie.documentos)


def test_instrumento_cita_situacao_e_valores_em_reais(proc, raiz_sem_publicado, urls):
    texto = dossie_de(proc, raiz_sem_publicado, urls, IDS_PERDAS[0]).por_id("instrumento-1981768").texto
    assert "Situação da proposta: Proposta/Plano de Trabalho Rejeitados" in texto
    assert "Número da proposta: 12684/2024" in texto
    assert "Valor do repasse: R$ 700.000,00" in texto


def test_historico_vem_em_ordem_cronologica_e_sem_motivo(proc, raiz_sem_publicado, urls):
    texto = dossie_de(proc, raiz_sem_publicado, urls, IDS_PERDAS[0]).por_id("historico-situacao-1981768").texto
    linhas = texto.splitlines()
    assert linhas[0] == "13/05/2024: PROPOSTA_CADASTRADA"
    datas = [date(int(x[6:10]), int(x[3:5]), int(x[:2])) for x in (l.split(":")[0] for l in linhas)]
    assert datas == sorted(datas)
    assert "21/01/2025" in texto


def test_cauc_escolhe_o_retrato_mais_proximo_da_perda(proc, raiz_sem_publicado, urls):
    doc = next(d for d in dossie_de(proc, raiz_sem_publicado, urls, IDS_PERDAS[0]).documentos if d.id.startswith("cauc-"))
    assert doc.id == "cauc-2026-10-29"  # único retrato existente
    assert "4.2" in doc.texto


def test_dossie_nao_vaza_dados_pessoais_nem_bancarios(proc, raiz_sem_publicado, urls):
    for verba_id in IDS_PERDAS:
        for doc in dossie_de(proc, raiz_sem_publicado, urls, verba_id).documentos:
            for proibido in ("AVENIDA RIO BRANCO", "CAIXA ECONOMICA", "0321-2", "NOME_PARLAMENTAR", "CEP"):
                assert proibido not in doc.texto


def test_verba_que_nao_e_do_siconv_volta_sem_documentos(proc, raiz_sem_publicado, urls):
    outra = next(v for v in proc.normalizacao.verbas if v.fonte != "transferegov_discricionarias")
    assert montar_dossie(outra, proc.retratos, raiz_sem_publicado, urls).documentos == []


def test_sem_retrato_do_siconv_o_dossie_vem_vazio(proc, raiz_sem_publicado, urls):
    verba = next(v for v in proc.normalizacao.verbas if v.id == IDS_PERDAS[0])
    retratos = {**proc.retratos, "transferegov_discricionarias": None}
    assert montar_dossie(verba, retratos, raiz_sem_publicado, urls).documentos == []


def test_pareceres_do_acesso_livre_entram_no_dossie_sem_contato(proc, raiz_sem_publicado, urls):
    """D23: cada parecer lido na conferência semanal vira um documento citável (`parecer-<proposta>-<data>`)."""
    import json
    from pathlib import Path

    exemplo = json.loads((Path(__file__).parent / "fixtures" / "transferegov_acesso_livre" / "parecer_exemplo.json").read_text(encoding="utf-8"))["bruto"]
    from coleta import acesso_livre as al

    pareceres = [al.parecer_do_retrato("1981768", exemplo), al.parecer_do_retrato("1981768", {**exemplo, "id_parecer": "2", "data": "26/08/2026"}), al.parecer_do_retrato("2065616", exemplo)]
    acesso = {"fonte": "transferegov_acesso_livre", "data": "2026-11-05", "coletado_em": "2026-11-05T21:00:00-03:00", "metadados": {}, "dados": {"propostas": [], "pareceres": pareceres}}
    com_urls = {**urls, "transferegov_acesso_livre": "https://exemplo.gov.br/acesso-livre"}
    verba = next(v for v in proc.normalizacao.verbas if v.id == IDS_PERDAS[0])
    dossie = montar_dossie(verba, {**proc.retratos, "transferegov_acesso_livre": acesso}, raiz_sem_publicado, com_urls)
    docs = [d for d in dossie.documentos if d.id.startswith("parecer-")]
    assert [d.id for d in docs] == ["parecer-1981768-2026-08-25", "parecer-1981768-2026-08-26"]  # só os desta proposta, em ordem de data
    assert all(d.url == "https://exemplo.gov.br/acesso-livre" and d.data_coleta == "2026-11-05T21:00:00-03:00" for d in docs)
    assert "saneados os apontamentos técnicos" in docs[0].texto and "99999" not in docs[0].texto and "Fulano" not in docs[0].texto
    sem = montar_dossie(verba, {**proc.retratos, "transferegov_acesso_livre": None}, raiz_sem_publicado, com_urls)
    assert not [d for d in sem.documentos if d.id.startswith("parecer-")]
