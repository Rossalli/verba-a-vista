import importlib.util
from datetime import datetime
from pathlib import Path

import httpx
import respx

from nucleo.config import carregar_config

_spec = importlib.util.spec_from_file_location(
    "teste_acesso", Path(__file__).resolve().parents[1] / "scripts" / "teste_acesso.py"
)
teste_acesso = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(teste_acesso)


def test_alvos_expande_modulos_e_marca_fontes_sem_url():
    alvos = dict(teste_acesso.alvos(carregar_config()))
    assert alvos["transferegov_api/especiais"] == "https://api-publica.transferegov.gestao.gov.br/especiais/docs"
    assert alvos["transferegov_api/parcerias"].endswith("/parcerias/docs")
    assert alvos["obrasgov"] == "https://api-publica.obrasgov.gestao.gov.br"
    assert alvos["transferegov_discricionarias"] == "https://repositorio.dados.gov.br/seges/detru"
    assert alvos["cauc"] is None


@respx.mock
def test_testar_classifica_respostas_e_falhas():
    respx.get("https://ok.example/").mock(return_value=httpx.Response(200))
    respx.get("https://auth.example/").mock(return_value=httpx.Response(401))
    respx.get("https://bloqueio.example/").mock(return_value=httpx.Response(403, text="  Proxy\n  bloqueou "))
    respx.get("https://fora.example/").mock(side_effect=httpx.ConnectTimeout("tempo esgotado"))

    with httpx.Client() as cliente:
        res = {
            nome: teste_acesso.testar_url(cliente, nome, url)
            for nome, url in [
                ("ok", "https://ok.example/"),
                ("auth", "https://auth.example/"),
                ("bloqueio", "https://bloqueio.example/"),
                ("fora", "https://fora.example/"),
                ("semurl", None),
            ]
        }

    assert res["ok"].veredito == "HTTP 200" and res["ok"].alcancou
    assert res["auth"].veredito == "HTTP 401" and res["auth"].alcancou
    assert res["bloqueio"].veredito == "403 (possível bloqueio)" and res["bloqueio"].nota == "Proxy bloqueou"
    assert res["fora"].veredito == "FALHOU" and not res["fora"].alcancou and "ConnectTimeout" in res["fora"].nota
    assert res["semurl"].veredito == "sem URL (A VERIFICAR)"


@respx.mock
def test_tabela_markdown():
    respx.get("https://ok.example/").mock(return_value=httpx.Response(200))
    with httpx.Client() as cliente:
        r = teste_acesso.testar_url(cliente, "ok", "https://ok.example/")
    tabela = teste_acesso.tabela_markdown([r, teste_acesso.Resultado("cauc", None)], "local", datetime(2026, 10, 29, 12, 0))
    assert tabela.startswith("Ambiente: local · 2026-10-29T12:00:00")
    assert "| ok | https://ok.example/ | HTTP 200 |" in tabela
    assert "| cauc | - | sem URL (A VERIFICAR) | - | - |" in tabela
