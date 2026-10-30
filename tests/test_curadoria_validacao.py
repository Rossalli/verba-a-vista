"""T3.3: validação de citações (spec §7.4)."""

from datetime import date

import pytest

from curadoria.dossie import Documento, Dossie, montar_dossie
from curadoria.validacao import frases, normalizar, permitidos_da_verba, validar_rascunho
from nucleo.config import carregar_config
from nucleo.pipeline import processar

VERBA = "transferegov_discricionarias-1981768"
TRECHO_1 = "Situação da proposta: Proposta/Plano de Trabalho Rejeitados"


@pytest.fixture(scope="module")
def contexto(raiz_sem_publicado):
    config = carregar_config()
    proc = processar(raiz_sem_publicado, date(2026, 10, 30), config)
    verba = next(v for v in proc.normalizacao.verbas if v.id == VERBA)
    fontes = config.fontes.fontes
    urls = {k: fontes[k].url or fontes[k].base_url for k in ("transferegov_discricionarias", "cauc", "obrasgov")}
    return config, verba, montar_dossie(verba, proc.retratos, raiz_sem_publicado, urls)


def bom(dossie: Dossie, **mudancas) -> dict:
    historico = dossie.documentos[1]
    base = {
        "verba_id": VERBA,
        "categoria": "reprovacao_tecnica",
        "texto": "A proposta foi rejeitada pelo órgão concedente [1]. O histórico registra a última mudança de situação em 21/01/2025 [2].",
        "evitavel": "indeterminado",
        "confianca": "baixa",
        "citacoes": [
            {"n": 1, "documento_id": dossie.documentos[0].id, "trecho": TRECHO_1},
            {"n": 2, "documento_id": historico.id, "trecho": historico.texto.splitlines()[-1]},
        ],
        "observacoes_para_revisor": "O documento não diz o motivo da rejeição.",
    }
    return {**base, **mudancas}


def valida(contexto, dados):
    config, verba, dossie = contexto
    return validar_rascunho(dados, dossie, permitidos_da_verba(verba, config), config)


def test_rascunho_bom_passa(contexto):
    r = valida(contexto, bom(contexto[2]))
    assert r.ok and r.erros == [] and r.avisos == []


def test_trecho_com_espacos_e_caixa_diferentes_ainda_confere(contexto):
    dossie = contexto[2]
    dados = bom(dossie)
    dados["citacoes"][0]["trecho"] = "  SITUAÇÃO da proposta:\n Proposta/Plano   de Trabalho Rejeitados "
    assert valida(contexto, dados).ok


def test_trecho_inexistente_reprova(contexto):
    dados = bom(contexto[2])
    dados["citacoes"][0]["trecho"] = "Proposta rejeitada por falta de projeto básico"
    r = valida(contexto, dados)
    assert not r.ok and "citação [1]: o trecho não aparece literalmente" in r.erros[0]


def test_trecho_de_outro_documento_reprova(contexto):
    dados = bom(contexto[2])
    dados["citacoes"][0]["documento_id"] = contexto[2].documentos[1].id  # o trecho é do instrumento
    assert any("não aparece literalmente" in e for e in valida(contexto, dados).erros)


def test_documento_fora_do_dossie_reprova(contexto):
    dados = bom(contexto[2])
    dados["citacoes"][0]["documento_id"] = "diario-oficial-2025"
    assert any("não está no dossiê" in e for e in valida(contexto, dados).erros)


def test_frase_sem_citacao_reprova(contexto):
    dados = bom(contexto[2], texto="A proposta foi rejeitada pelo órgão concedente [1]. A prefeitura não corrigiu a tempo. O histórico registra a mudança [2].")
    r = valida(contexto, dados)
    assert r.erros == ["frase sem citação: «A prefeitura não corrigiu a tempo.»"]


def test_marcador_depois_do_ponto_vale(contexto):
    dados = bom(contexto[2], texto="A proposta foi rejeitada pelo órgão concedente. [1] O histórico registra a mudança. [2]")
    assert valida(contexto, dados).ok


def test_marcador_sem_citacao_correspondente_reprova(contexto):
    dados = bom(contexto[2], texto="A proposta foi rejeitada [1]. O histórico registra a mudança [2]. Houve outra pendência [3].")
    assert valida(contexto, dados).erros == ["o texto cita [3], que não existe em `citacoes`"]


def test_citacao_nao_usada_so_avisa(contexto):
    dados = bom(contexto[2], texto="A proposta foi rejeitada pelo órgão concedente [1].")
    r = valida(contexto, dados)
    assert r.ok and r.avisos == ["a citação [2] não é usada no texto"]


def test_citacoes_com_numero_repetido_reprovam(contexto):
    dados = bom(contexto[2])
    dados["citacoes"][1]["n"] = 1
    assert any("mesmo número" in e for e in valida(contexto, dados).erros)


@pytest.mark.parametrize(
    "texto",
    [
        "O prefeito João Silva não enviou os documentos [1].",
        "A proposta foi rejeitada após parecer de Maria de Souza Lima [1].",
        "Segundo a Dra. Ana, a proposta foi rejeitada [1].",
    ],
)
def test_nome_de_pessoa_reprova(contexto, texto):
    dados = bom(contexto[2], texto=texto + " O histórico registra a mudança [2].")
    erros = valida(contexto, dados).erros
    assert any("pessoa" in e for e in erros)  # "Dra." também parte a frase: reprova por conservadorismo


def test_orgaos_municipio_e_instrumentos_nao_sao_confundidos_com_pessoas(contexto):
    texto = "A Prefeitura Municipal de Neves Paulista teve a proposta ao Ministério da Agricultura e Pecuária rejeitada [1]. O Plano de Trabalho consta como Rejeitado [2]."
    assert valida(contexto, bom(contexto[2], texto=texto)).ok


def test_em_apuracao_com_texto_padrao_dispensa_citacao(contexto):
    config = contexto[0]
    dados = bom(contexto[2], categoria="em_apuracao", texto=config.regras.curadoria.texto_em_apuracao, citacoes=[])
    assert valida(contexto, dados).ok


def test_em_apuracao_com_texto_proprio_ou_citacoes_reprova(contexto):
    dossie = contexto[2]
    assert not valida(contexto, bom(dossie, categoria="em_apuracao", texto="Ainda não sabemos o motivo.", citacoes=[])).ok
    assert any("exige" in e for e in valida(contexto, bom(dossie, categoria="em_apuracao")).erros)


def test_fora_do_schema_reprova_sem_conferir_o_resto(contexto):
    r = valida(contexto, {"verba_id": VERBA})
    assert len(r.erros) == 1 and r.erros[0].startswith("fora do schema")


def test_rascunho_de_outra_verba_reprova(contexto):
    assert any("não de" in e for e in valida(contexto, bom(contexto[2], verba_id="outra")).erros)


def test_helpers():
    assert normalizar("  A\n B  c ") == "a b c"
    assert frases("Uma [1]. Duas. [2] Três!") == ["Uma [1].", "Duas. [2]", "Três!"]


def test_documento_simples_sem_dados_reais():
    dossie = Dossie("v1", [Documento("d", "t", "u", "2026-01-01T00:00:00-03:00", "Linha um\nLinha dois")])
    dados = {"verba_id": "v1", "categoria": "cauc", "texto": "Há pendência [1].", "evitavel": "sim", "confianca": "media",
             "citacoes": [{"n": 1, "documento_id": "d", "trecho": "linha um linha dois"}], "observacoes_para_revisor": ""}
    assert validar_rascunho(dados, dossie).ok
