import json
import sys
import types
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from coleta import base
from coleta.base import AcessoNegadoErro, ColetaErro, Http, RetratoBruto
from nucleo.config import carregar_config

URL = "https://exemplo.gov.br/api"
DIA = date(2026, 10, 29)


def novo_http(**kw):
    pausas: list[float] = []
    kw.setdefault("tentativas", 3)
    kw.setdefault("backoff_inicial_s", 2.0)
    http = Http(dormir=pausas.append, **kw)
    return http, pausas


# --- Http.get ----------------------------------------------------------------------------------


@respx.mock
def test_get_repete_em_503_com_backoff_exponencial_e_devolve_o_sucesso():
    rota = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, json={"ok": True})])
    http, pausas = novo_http(tentativas=4)
    assert http.get_json(URL) == {"ok": True}
    assert rota.call_count == 3 and http.requisicoes == 3
    assert pausas == [2.0, 4.0]


@respx.mock
def test_get_repete_em_erro_de_rede():
    respx.get(URL).mock(side_effect=[httpx.ConnectTimeout("lento"), httpx.Response(200, json=[1])])
    http, pausas = novo_http()
    assert http.get_json(URL) == [1]
    assert pausas == [2.0]


@respx.mock
def test_get_nao_repete_em_404_e_inclui_o_status():
    rota = respx.get(URL).mock(return_value=httpx.Response(404, text="nada aqui"))
    http, pausas = novo_http()
    with pytest.raises(ColetaErro, match="HTTP 404"):
        http.get(URL)
    assert rota.call_count == 1 and pausas == []


@respx.mock
def test_get_desiste_depois_das_tentativas_e_diz_o_ultimo_erro():
    rota = respx.get(URL).mock(return_value=httpx.Response(500))
    http, pausas = novo_http(tentativas=3)
    with pytest.raises(ColetaErro, match=r"3 tentativas falharam \(último erro: HTTP 500\)"):
        http.get(URL)
    assert rota.call_count == 3 and pausas == [2.0, 4.0]  # não dorme depois da última


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 429])
def test_get_para_na_hora_nos_status_proibidos_de_repetir(status):
    rota = respx.get(URL).mock(return_value=httpx.Response(status, text="negado"))
    http, pausas = novo_http(parar_em=frozenset({401, 403, 429}))
    with pytest.raises(AcessoNegadoErro, match=str(status)):
        http.get(URL)
    assert rota.call_count == 1 and pausas == []


@respx.mock
def test_get_429_sem_parar_em_e_repetido():
    respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json={})])
    http, _ = novo_http()
    assert http.get_json(URL) == {}


@respx.mock
def test_get_json_com_corpo_invalido_vira_coletaerro():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>erro</html>"))
    http, _ = novo_http()
    with pytest.raises(ColetaErro, match="não é JSON"):
        http.get_json(URL)


@respx.mock
def test_get_respeita_o_intervalo_minimo_entre_chamadas():
    respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    agora = [0.0]
    pausas: list[float] = []

    def dormir(segundos):
        pausas.append(segundos)
        agora[0] += segundos  # dormir faz o tempo passar

    http = Http(tentativas=1, backoff_inicial_s=1, intervalo_minimo_s=0.2, dormir=dormir, relogio=lambda: agora[0])
    http.get(URL)
    agora[0] += 0.05  # a próxima chamada vem 0,05 s depois: falta 0,15 s
    http.get(URL)
    agora[0] += 0.5  # esta vem 0,5 s depois: não espera
    http.get(URL)
    assert pausas == [pytest.approx(0.15)]


@respx.mock
def test_teto_de_requisicoes_conta_tambem_as_tentativas_repetidas():
    rota = respx.get(URL).mock(return_value=httpx.Response(503))
    http, _ = novo_http(tentativas=5, max_requisicoes=3)
    with pytest.raises(ColetaErro, match="teto de 3 requisições"):
        http.get(URL)
    assert rota.call_count == 3


@respx.mock
def test_get_envia_cabecalhos_e_nao_vaza_a_chave_na_mensagem_de_erro():
    rota = respx.get(URL).mock(return_value=httpx.Response(403, text="negado"))
    http, _ = novo_http(parar_em=frozenset({403}), cabecalhos={"chave-api-dados": "SEGREDO123"})
    with pytest.raises(AcessoNegadoErro) as e:
        http.get(URL)
    assert rota.calls[0].request.headers["chave-api-dados"] == "SEGREDO123"
    assert "SEGREDO123" not in str(e.value)


# --- Http.baixar -------------------------------------------------------------------------------


@respx.mock
def test_baixar_grava_o_arquivo_e_pula_quando_ja_existe_com_o_mesmo_tamanho(tmp_path):
    corpo = b"x" * 1000
    respx.head(URL).mock(return_value=httpx.Response(200, headers={"content-length": "1000"}))
    get = respx.get(URL).mock(return_value=httpx.Response(200, content=corpo))
    http, _ = novo_http()
    destino = tmp_path / "sub" / "a.zip"
    assert http.baixar(URL, destino) == destino and destino.read_bytes() == corpo
    assert get.call_count == 1
    http.baixar(URL, destino)  # segunda vez: cache
    assert get.call_count == 1
    assert not list(tmp_path.rglob("*.parte"))


@respx.mock
def test_baixar_com_tamanho_diferente_tenta_de_novo_e_limpa_o_parcial(tmp_path):
    respx.head(URL).mock(return_value=httpx.Response(200, headers={"content-length": "1000"}))
    get = respx.get(URL).mock(return_value=httpx.Response(200, content=b"curto"))
    http, _ = novo_http(tentativas=2)
    with pytest.raises(ColetaErro, match="download falhou"):
        http.baixar(URL, tmp_path / "a.zip")
    assert get.call_count == 2
    assert not (tmp_path / "a.zip").exists() and not list(tmp_path.glob("*.parte"))


@respx.mock
def test_baixar_funciona_sem_content_length(tmp_path):
    respx.head(URL).mock(return_value=httpx.Response(405))
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"abc"))
    http, _ = novo_http()
    assert http.baixar(URL, tmp_path / "a.bin").read_bytes() == b"abc"


# --- gravação ----------------------------------------------------------------------------------


def retrato(**kw):
    padrao = dict(fonte="cauc", data=DIA, coletado_em=datetime(2026, 10, 29, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")), metadados={"b": 2, "a": 1}, dados={"itens": [{"z": 1, "a": "açaí"}]})
    return RetratoBruto(**{**padrao, **kw})


def test_gravar_retrato_escreve_json_estavel_com_acentos(tmp_path):
    caminho = base.gravar_retrato(tmp_path, retrato())
    assert caminho == tmp_path / "dados" / "brutos" / "cauc" / "2026-10-29.json"
    texto = caminho.read_text(encoding="utf-8")
    assert "açaí" in texto  # sem escapes \u
    assert texto.index('"a": 1') < texto.index('"b": 2')  # chaves ordenadas
    assert json.loads(texto)["coletado_em"] == "2026-10-29T09:00:00-03:00"
    assert not list(caminho.parent.glob("*.tmp"))


def test_gravar_retrato_nunca_sobrescreve(tmp_path):
    base.gravar_retrato(tmp_path, retrato())
    with pytest.raises(FileExistsError, match="nunca são editados"):
        base.gravar_retrato(tmp_path, retrato(dados={"itens": []}))
    assert json.loads(base.caminho_retrato(tmp_path, "cauc", DIA).read_text(encoding="utf-8"))["dados"]["itens"] != []


def test_registrar_log_acumula_as_execucoes_do_dia(tmp_path):
    base.registrar_log(tmp_path, "cauc", DIA, {"status": "erro", "erro": "boom"})
    caminho = base.registrar_log(tmp_path, "cauc", DIA, {"status": "ok"})
    log = json.loads(caminho.read_text(encoding="utf-8"))
    assert caminho.name == "2026-10-29.log.json"
    assert [e["status"] for e in log["execucoes"]] == ["erro", "ok"] and log["fonte"] == "cauc"


def test_contagens_por_recurso():
    assert retrato(dados={"a": [{}, {}], "b": []}).contagens() == {"a": 2, "b": 0}


# --- executar ----------------------------------------------------------------------------------


@pytest.fixture
def fontes_falsas(monkeypatch):
    """Três fontes de mentira: uma boa, uma que falha e uma que só roda se for chamada."""
    chamadas: list[str] = []

    def modulo(nome, comportamento):
        m = types.ModuleType(f"coleta_falsa_{nome}")
        m.criar_http = lambda config: novo_http()[0]

        def coletar(data, *, config=None, http=None, **kw):
            chamadas.append(nome)
            http.requisicoes += 2
            return comportamento(nome, data)

        m.coletar = coletar
        sys.modules[m.__name__] = m
        return m.__name__

    def bom(nome, data):
        return RetratoBruto(nome, data, datetime(2026, 10, 29, 9, tzinfo=ZoneInfo("America/Sao_Paulo")), {"fonte_data": "2026-10-29"}, {"itens": [{"n": 1}, {"n": 2}]})

    def ruim(nome, data):
        raise ColetaErro("a fonte caiu")

    monkeypatch.setattr(base, "FONTES", {"boa": modulo("boa", bom), "ruim": modulo("ruim", ruim), "outra": modulo("outra", bom)})
    return chamadas


def relogio_fixo(config):
    return datetime(2026, 10, 29, 9, 0, tzinfo=ZoneInfo(config.regras.coleta.fuso))


def test_falha_de_uma_fonte_nao_derruba_as_outras(tmp_path, fontes_falsas):
    resultados = base.executar(data=DIA, raiz=tmp_path, relogio=relogio_fixo)
    por_fonte = {r.fonte: r for r in resultados}
    assert [r.status for r in resultados] == ["ok", "erro", "ok"]
    assert "a fonte caiu" in por_fonte["ruim"].erro and "ColetaErro" in por_fonte["ruim"].erro
    assert fontes_falsas == ["boa", "ruim", "outra"]  # todas rodaram
    assert por_fonte["boa"].registros == {"itens": 2} and por_fonte["boa"].requisicoes == 2
    assert not base.caminho_retrato(tmp_path, "ruim", DIA).exists()  # nada parcial
    log = json.loads(base.caminho_log(tmp_path, "ruim", DIA).read_text(encoding="utf-8"))
    assert log["execucoes"][0]["status"] == "erro" and "a fonte caiu" in log["execucoes"][0]["erro"]
    log_boa = json.loads(base.caminho_log(tmp_path, "boa", DIA).read_text(encoding="utf-8"))["execucoes"][0]
    assert log_boa["registros"] == {"itens": 2} and log_boa["metadados"] == {"fonte_data": "2026-10-29"}


def test_retrato_do_dia_e_reaproveitado_sem_chamar_a_fonte(tmp_path, fontes_falsas):
    base.executar(["boa"], DIA, raiz=tmp_path, relogio=relogio_fixo)
    fontes_falsas.clear()
    antes = base.caminho_retrato(tmp_path, "boa", DIA).read_text(encoding="utf-8")
    resultado = base.executar(["boa"], DIA, raiz=tmp_path, relogio=relogio_fixo)[0]
    assert resultado.status == "reaproveitado" and fontes_falsas == []
    assert base.caminho_retrato(tmp_path, "boa", DIA).read_text(encoding="utf-8") == antes
    assert [e["status"] for e in json.loads(base.caminho_log(tmp_path, "boa", DIA).read_text(encoding="utf-8"))["execucoes"]] == ["ok", "reaproveitado"]


def test_forcar_coleta_de_novo_mas_nao_sobrescreve_o_retrato(tmp_path, fontes_falsas):
    base.executar(["boa"], DIA, raiz=tmp_path, relogio=relogio_fixo)
    antes = base.caminho_retrato(tmp_path, "boa", DIA).read_text(encoding="utf-8")
    fontes_falsas.clear()
    resultado = base.executar(["boa"], DIA, raiz=tmp_path, forcar=True, relogio=relogio_fixo)[0]
    assert fontes_falsas == ["boa"] and resultado.status == "ok" and "já existia" in resultado.erro
    assert base.caminho_retrato(tmp_path, "boa", DIA).read_text(encoding="utf-8") == antes


def test_opcoes_so_chegam_as_fontes_que_as_declaram(tmp_path, monkeypatch):
    recebidas: dict[str, dict] = {}

    def modulo(nome, opcoes):
        m = types.ModuleType(f"coleta_opcoes_{nome}")
        m.OPCOES = opcoes
        m.criar_http = lambda config: novo_http()[0]

        def coletar(data, *, config=None, http=None, **kw):
            recebidas[nome] = kw
            return RetratoBruto(nome, data, datetime(2026, 10, 29, 9, tzinfo=ZoneInfo("America/Sao_Paulo")), {}, {})

        m.coletar = coletar
        sys.modules[m.__name__] = m
        return m.__name__

    monkeypatch.setattr(base, "FONTES", {"com": modulo("com", ("cache",)), "sem": modulo("sem", ())})
    base.executar(data=DIA, raiz=tmp_path, relogio=relogio_fixo, cache="/x", outra="y")
    assert recebidas == {"com": {"cache": "/x"}, "sem": {}}  # `outra` ninguém declarou: ignorada


def test_fonte_desconhecida_e_erro_de_uso(tmp_path):
    with pytest.raises(ValueError, match="fontes desconhecidas"):
        base.executar(["inventada"], DIA, raiz=tmp_path)


def test_todas_as_fontes_da_config_tem_coletor_registrado():
    assert set(base.FONTES) == {f for f, c in carregar_config().fontes.fontes.items() if c.ativa and not c.manual}  # as manuais (D23) são rodadas por uma pessoa, sem coletor
