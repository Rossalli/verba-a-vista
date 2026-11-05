"""T5.1: avisos do dia (issues do workflow diário)."""

import json
import shutil
from datetime import date

import pytest

from nucleo import avisos as a
from nucleo import pipeline
from nucleo.normaliza import SituacaoNaoMapeada
from tests.conftest import RAIZ

HOJE = date(2026, 10, 30)


def test_ids_da_fila_separa_pendentes_de_reprovados(tmp_path):
    fila = tmp_path / "dados" / "fila"
    fila.mkdir(parents=True)
    for nome in ("transferegov_discricionarias-1.yaml", "transferegov_discricionarias-2.erro.yaml", "transferegov_discricionarias-3.yaml", "LEIAME.txt"):
        (fila / nome).write_text("x", encoding="utf-8")
    assert a.ids_da_fila(tmp_path) == (["transferegov_discricionarias-1", "transferegov_discricionarias-3"], ["transferegov_discricionarias-2"])
    assert a.ids_da_fila(tmp_path / "vazio") == ([], [])


def test_ids_novos_vem_da_saida_do_git_status():
    linhas = ["?? dados/fila/transferegov_discricionarias-1.yaml", " M dados/fila/transferegov_discricionarias-2.erro.yaml", "A  dados/fila/transferegov_discricionarias-3.yaml", "", "?? dados/fila/outro.txt"]
    assert a.ids_novos(linhas) == {"transferegov_discricionarias-1", "transferegov_discricionarias-2", "transferegov_discricionarias-3"}


def test_aviso_da_fila_so_quando_ha_rascunho_novo():
    assert a.aviso_fila(["v-1"], [], set()) is None  # fila pendente de ontem: nada de issue nova
    assert a.aviso_fila(["v-1"], [], {"outra"}) is None  # arquivo novo que não está mais na fila
    aviso = a.aviso_fila(["v-1", "v-2"], ["v-3"], {"v-2", "v-3"})
    assert aviso.titulo == a.TITULO_FILA and aviso.comentar is True
    assert "`v-1`\n" in aviso.corpo and "`v-2` (novo)" in aviso.corpo and "`v-3` (novo)" in aviso.corpo
    assert 'python -m curadoria.aprovar <id> --por "<seu nome>"' in aviso.corpo and "Nada é publicado até uma pessoa revisar" in aviso.corpo


def test_aviso_de_situacoes_nao_mapeadas_lista_fonte_campo_valor_e_quantidade():
    assert a.aviso_nao_mapeadas([]) is None
    aviso = a.aviso_nao_mapeadas([SituacaoNaoMapeada("transferegov_discricionarias", "SIT_PROPOSTA", "Proposta Suspensa", ["v-1", "v-2"])])
    assert aviso.titulo == a.TITULO_NAO_MAPEADAS and aviso.comentar is False
    assert "| `transferegov_discricionarias` | `SIT_PROPOSTA` | Proposta Suspensa | 2 |" in aviso.corpo and "situação em análise" in aviso.corpo


def test_aviso_de_fonte_sem_retrato_de_hoje():
    fontes = {"cauc": {"nome": "CAUC", "situacao": "ok", "retrato": "2026-10-30"}, "obrasgov": {"nome": "Obrasgov", "situacao": "defasada", "retrato": "2026-10-29", "data_do_dado": None}}
    aviso = a.aviso_fontes(fontes, HOJE)
    assert aviso.titulo == a.TITULO_FONTES and "| Obrasgov | defasada | 2026-10-29 | — |" in aviso.corpo and "CAUC" not in aviso.corpo
    assert a.aviso_fontes({"cauc": {"situacao": "ok"}}, HOJE) is None


def test_sem_nada_a_avisar_a_lista_e_vazia():
    assert a.montar_avisos(nao_mapeadas=[], fila_pendente=["v-1"], fila_erros=[], fila_novos=set(), fontes={"cauc": {"situacao": "ok"}}, hoje=HOJE) == []


@pytest.fixture
def raiz_publicada(tmp_path):
    shutil.copytree(RAIZ / "dados" / "brutos", tmp_path / "dados" / "brutos")
    assert pipeline.main(["--data", "2026-10-30", "--raiz", str(tmp_path)]) == 0
    return tmp_path


def test_linha_de_comando_com_dados_reais(raiz_publicada, capsys):
    (raiz_publicada / "dados" / "fila").mkdir(parents=True)
    (raiz_publicada / "dados" / "fila" / "transferegov_discricionarias-1981768.yaml").write_text("verba_id: x\n", encoding="utf-8")
    novos = raiz_publicada / "novos.txt"
    novos.write_text("?? dados/fila/transferegov_discricionarias-1981768.yaml\n", encoding="utf-8")
    capsys.readouterr()
    assert a.main(["--raiz", str(raiz_publicada), "--data", "2026-10-30", "--fila-novos", str(novos)]) == 0
    saida = json.loads(capsys.readouterr().out)
    por_chave = {x["chave"]: x for x in saida}
    assert set(por_chave) == {"fila", "fontes", "acesso_livre"}  # dados reais (sem nenhuma conferência no Acesso Livre ainda, D23): nenhuma situação sem mapeamento; retratos de 29/10 são "defasados" em 30/10
    assert "transferegov_discricionarias-1981768" in por_chave["fila"]["corpo"] and por_chave["fila"]["comentar"] is True
    assert "Transferegov" in por_chave["fontes"]["corpo"]


def test_linha_de_comando_sem_fila_nem_novos_avisa_so_das_fontes(raiz_publicada, capsys):
    capsys.readouterr()
    assert a.main(["--raiz", str(raiz_publicada), "--data", "2026-10-30"]) == 0
    assert [x["chave"] for x in json.loads(capsys.readouterr().out)] == ["fontes", "acesso_livre"]


# --- abrir_issues (com um `gh` de mentira) -----------------------------------------------------


class GhFalso:
    """Registra os comandos e responde à busca com as issues abertas combinadas."""

    def __init__(self, abertas: list[dict]) -> None:
        self.abertas, self.comandos = abertas, []

    def __call__(self, comando, **kw):
        self.comandos.append(comando)
        saida = json.dumps(self.abertas) if comando[2] == "list" else ""
        return type("R", (), {"stdout": saida})()


def avisos_de_teste():
    return [a.Aviso("fila", a.TITULO_FILA, "corpo da fila", comentar=True), a.Aviso("fontes", a.TITULO_FONTES, "corpo das fontes")]


def test_sem_issue_aberta_cria_uma_por_aviso():
    gh = GhFalso([])
    log = a.abrir_issues(avisos_de_teste(), gh)
    criar = [c for c in gh.comandos if c[2] == "create"]
    assert [c[4] for c in criar] == [a.TITULO_FILA, a.TITULO_FONTES] and [c[6] for c in criar] == ["corpo da fila", "corpo das fontes"]
    assert log == [f"issue criada: {a.TITULO_FILA}", f"issue criada: {a.TITULO_FONTES}"]


def test_com_issue_aberta_so_a_fila_comenta_e_nada_se_duplica():
    gh = GhFalso([{"number": 7, "title": a.TITULO_FILA}, {"number": 9, "title": a.TITULO_FONTES}])
    log = a.abrir_issues(avisos_de_teste(), gh)
    assert [c[:4] for c in gh.comandos if c[2] != "list"] == [["gh", "issue", "comment", "7"]]
    assert log == [f"comentário na issue #7: {a.TITULO_FILA}", f"issue #9 já aberta, nada a fazer: {a.TITULO_FONTES}"]


def test_issue_de_titulo_parecido_nao_conta_como_a_mesma():
    gh = GhFalso([{"number": 3, "title": a.TITULO_FILA + " (antiga)"}])  # a busca do GitHub é aproximada; só título idêntico vale
    a.abrir_issues(avisos_de_teste()[:1], gh)
    assert [c[2] for c in gh.comandos] == ["list", "create"]
