"""T3.4: fila de revisão e aprovação, com perdas reais e cliente da IA falso (nenhuma chamada paga)."""

import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from curadoria import aprovar as ap
from curadoria.executar import executar, main, resumo
from curadoria.fila import caminho_erro, caminho_fila
from nucleo.curadoria_revisada import caminho_curadoria
from nucleo.pipeline import processar
from nucleo.publica import publicar
from tests.conftest import RAIZ
from tests.test_curadoria_dossie import IDS_PERDAS

DATA = date(2026, 10, 30)
BOA, TRECHO_FALSO, SEM_JSON = IDS_PERDAS[:3]
TRECHO = "Situação da proposta: Proposta/Plano de Trabalho Rejeitados"


def rascunho(verba_id: str, **mudancas) -> dict:
    base = {
        "verba_id": verba_id,
        "categoria": "reprovacao_tecnica",
        "texto": "A proposta consta como rejeitada na situação registrada pelo órgão concedente [1].",
        "evitavel": "indeterminado",
        "confianca": "baixa",
        "citacoes": [{"n": 1, "documento_id": f"instrumento-{verba_id.split('-')[1]}", "trecho": TRECHO}],
        "observacoes_para_revisor": "Os documentos não explicam o motivo.",
    }
    return {**base, **mudancas}


class ClienteFalso:
    """Responde de acordo com a verba do pedido: uma boa, uma com trecho inventado, uma que não é JSON."""

    def __init__(self) -> None:
        self.messages = self
        self.chamadas: list[str] = []

    def create(self, **kwargs):
        mensagem = kwargs["messages"][0]["content"]
        verba_id = mensagem.splitlines()[0].removeprefix("verba_id: ")
        self.chamadas.append(verba_id)
        if verba_id == SEM_JSON:
            texto = "Não consegui ler os documentos."
        elif verba_id == TRECHO_FALSO:
            citacao = {"n": 1, "documento_id": f"instrumento-{verba_id.split('-')[1]}", "trecho": "Rejeitada por falta de projeto básico"}
            texto = json.dumps(rascunho(verba_id, citacoes=[citacao]))
        else:
            texto = json.dumps(rascunho(verba_id))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=texto)],
            stop_reason="end_turn",
            model="claude-sonnet-5-5",
            usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            _request_id="req_teste",
        )


@pytest.fixture
def raiz(tmp_path) -> Path:
    shutil.copytree(RAIZ / "dados" / "brutos", tmp_path / "dados" / "brutos")
    return tmp_path


def gerar(raiz, cliente, **kw):
    return executar(raiz, DATA, None, [BOA, TRECHO_FALSO, SEM_JSON], enviar=True, cliente=cliente, **kw)


def editar_fila(raiz, verba_id, editar) -> Path:
    caminho = caminho_fila(raiz, verba_id)
    fila = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    editar(fila["rascunho"])
    caminho.write_text(yaml.safe_dump(fila, allow_unicode=True, sort_keys=False), encoding="utf-8")  # a pessoa edita à mão
    return caminho


def test_plano_nao_chama_a_ia_nem_grava_nada(raiz):
    cliente = ClienteFalso()
    r = executar(raiz, DATA, None, [BOA], enviar=False, cliente=cliente)
    assert r.plano == [f"{BOA}: 3 documentos"] and cliente.chamadas == []
    assert not (raiz / "dados" / "fila").exists()
    assert "nada foi enviado nem cobrado" in resumo(r, False)


def test_gera_fila_e_erros(raiz):
    r = gerar(raiz, ClienteFalso())
    assert (r.na_fila, r.com_erro) == ([BOA], [TRECHO_FALSO, SEM_JSON])
    assert (r.tokens_entrada, r.tokens_saida) == (2000, 200)
    fila = yaml.safe_load(caminho_fila(raiz, BOA).read_text(encoding="utf-8"))
    assert fila["rascunho"]["categoria"] == "reprovacao_tecnica" and fila["modelo"] == "claude-sonnet-5-5"
    assert fila["documentos"][0]["id"] == "instrumento-1981768"
    assert "Neves Paulista" in " ".join(fila["permitidos"])
    erro = yaml.safe_load(caminho_erro(raiz, TRECHO_FALSO).read_text(encoding="utf-8"))
    assert "não aparece literalmente" in erro["erros"][0] and erro["rascunho"]["verba_id"] == TRECHO_FALSO
    assert yaml.safe_load(caminho_erro(raiz, SEM_JSON).read_text(encoding="utf-8"))["resposta_bruta"] == "Não consegui ler os documentos."
    assert not caminho_fila(raiz, TRECHO_FALSO).exists() and not caminho_fila(raiz, SEM_JSON).exists()


def test_nao_envia_de_novo_sem_refazer(raiz):
    cliente = ClienteFalso()
    gerar(raiz, cliente)
    r = gerar(raiz, cliente)
    assert sorted(r.ja_na_fila) == sorted([BOA, TRECHO_FALSO, SEM_JSON]) and len(cliente.chamadas) == 3
    gerar(raiz, cliente, refazer=True)
    assert len(cliente.chamadas) == 6


def test_so_a_curadoria_revisada_chega_ao_publicado(raiz):
    gerar(raiz, ClienteFalso())
    proc = processar(raiz, DATA)
    perda = next(v for v in proc.normalizacao.verbas if v.id == BOA).perda
    assert perda.categoria == "em_apuracao" and perda.revisado_por is None  # rascunho na fila não publica
    assert BOA in proc.historico.precisam_curadoria


def test_fluxo_completo_gera_revisa_aprova_e_publica(raiz):
    gerar(raiz, ClienteFalso())
    caminho = editar_fila(raiz, BOA, lambda r: r.update(texto=r["texto"] + " O motivo não está nos documentos [1]."))

    destino, avisos = ap.aprovar(raiz, BOA, "Bárbara", DATA)
    assert destino == caminho_curadoria(raiz, BOA) and avisos == [] and not caminho.exists()

    proc = processar(raiz, DATA)
    verba = next(v for v in proc.normalizacao.verbas if v.id == BOA)
    assert (verba.perda.categoria, verba.perda.revisado_por, verba.perda.revisado_em) == ("reprovacao_tecnica", "Bárbara", DATA)
    assert verba.perda.gerado_por_ia is True
    assert "O motivo não está nos documentos" in verba.perda.texto
    assert verba.perda.citacoes[0].titulo.startswith("Transferegov") and verba.perda.citacoes[0].url.startswith("http")
    assert BOA not in proc.historico.precisam_curadoria and TRECHO_FALSO in proc.historico.precisam_curadoria
    publicado = publicar(proc.normalizacao.verbas, proc.retratos, proc.config, DATA, raiz)  # valida no schema
    corpo = json.loads(publicado.json.read_text(encoding="utf-8"))
    perdas = {v["id"]: v["perda"] for v in corpo["verbas"] if v["status_site"] == "perdida"}
    assert perdas[BOA]["revisado_por"] == "Bárbara" and perdas[TRECHO_FALSO]["categoria"] == "em_apuracao"


def test_edicao_que_quebra_a_citacao_nao_e_aprovada(raiz):
    gerar(raiz, ClienteFalso())
    caminho = editar_fila(raiz, BOA, lambda r: r["citacoes"][0].update(trecho="inventei isto"))
    with pytest.raises(ap.AprovacaoErro, match="não aparece literalmente"):
        ap.aprovar(raiz, BOA, "Bárbara", DATA)
    assert caminho.exists() and not caminho_curadoria(raiz, BOA).exists()


def test_recusas_da_aprovacao(raiz):
    with pytest.raises(ap.AprovacaoErro, match="não há rascunho"):
        ap.aprovar(raiz, BOA, "Bárbara", DATA)
    gerar(raiz, ClienteFalso())
    with pytest.raises(ap.AprovacaoErro, match="quem revisou"):
        ap.aprovar(raiz, BOA, "  ", DATA)
    ap.aprovar(raiz, BOA, "Bárbara", DATA)
    caminho_fila(raiz, BOA).write_text("verba_id: x\n", encoding="utf-8")  # fila nova, curadoria já aprovada
    with pytest.raises(ap.AprovacaoErro, match="já existe"):
        ap.aprovar(raiz, BOA, "Bárbara", DATA)


def test_em_apuracao_nao_e_aprovado(raiz):
    gerar(raiz, ClienteFalso())
    padrao = "Motivo em apuração. Ainda não encontramos documento oficial que explique esta perda."
    editar_fila(raiz, BOA, lambda r: r.update(categoria="em_apuracao", citacoes=[], texto=padrao))
    with pytest.raises(ap.AprovacaoErro, match="em_apuracao"):
        ap.aprovar(raiz, BOA, "Bárbara", DATA)


def test_linha_de_comando(raiz, capsys):
    assert main(["--raiz", str(raiz), "--data", "2026-10-30", "--id", BOA]) == 0
    assert f"{BOA}: 3 documentos" in capsys.readouterr().out
    assert ap.main([BOA, "--por", "Bárbara", "--raiz", str(raiz)]) == 1
    assert "Não aprovado" in capsys.readouterr().out


# --- falha de infraestrutura da IA (chave, API, rede): não grava arquivo e tenta de novo depois ---------------


class ClienteQueFalha:
    def __init__(self, erro: Exception) -> None:
        self.messages, self.erro, self.chamadas = self, erro, 0

    def create(self, **kwargs):
        self.chamadas += 1
        raise self.erro


def erro_de_api():
    import anthropic
    import httpx

    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def test_falha_da_api_nao_grava_arquivo_para_na_primeira_e_conta_as_que_sobraram(raiz):
    cliente = ClienteQueFalha(erro_de_api())
    r = gerar(raiz, cliente)
    assert cliente.chamadas == 1  # as próximas falhariam do mesmo jeito
    assert "APIConnectionError" in r.falha_api and r.nao_tentadas == 3
    assert (r.na_fila, r.com_erro) == ([], [])
    assert not (raiz / "dados" / "fila").exists()  # nenhum .erro.yaml: ele bloquearia a nova tentativa


def test_depois_da_falha_a_proxima_execucao_tenta_de_novo(raiz):
    gerar(raiz, ClienteQueFalha(erro_de_api()))
    cliente = ClienteFalso()
    r = gerar(raiz, cliente)  # a IA voltou
    assert r.falha_api is None and r.ja_na_fila == [] and len(cliente.chamadas) == 3 and r.na_fila == [BOA]


def test_sem_chave_tambem_nao_grava_arquivo(raiz, monkeypatch, tmp_path):
    from curadoria import ia

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ia, "RAIZ", tmp_path)  # sem .env
    r = executar(raiz, DATA, None, [BOA], enviar=True)
    assert "ANTHROPIC_API_KEY" in r.falha_api and not (raiz / "dados" / "fila").exists()


def test_erro_do_conteudo_continua_gravando_arquivo(raiz):
    r = gerar(raiz, ClienteFalso())
    assert r.falha_api is None and SEM_JSON in r.com_erro and caminho_erro(raiz, SEM_JSON).exists()  # JSON ilegível: erro do rascunho, não da infraestrutura


def test_linha_de_comando_nao_falha_o_dia_e_avisa_no_actions(raiz, monkeypatch, capsys):
    from curadoria import executar as ex

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(ex, "criar_cliente", lambda: ClienteQueFalha(erro_de_api()))
    assert main(["--raiz", str(raiz), "--data", "2026-10-30", "--id", BOA, "--executar"]) == 0
    saida = capsys.readouterr().out
    assert "FALHA NA IA" in saida and "::warning title=Curadoria com IA falhou::" in saida
