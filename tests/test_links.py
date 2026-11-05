"""D21: os links que o site mostra têm que ser de páginas que uma pessoa abre, não de coleta (nem do endereço fora do ar)."""

import json
import re
from datetime import date
from pathlib import Path

import yaml

from nucleo.config import carregar_config
from nucleo.normaliza import carregar_retratos, normalizar

RAIZ = Path(__file__).resolve().parents[1]
DATA = date(2026, 10, 30)
PORTAL_CONVENIO = re.compile(r"^https://portaldatransparencia\.gov\.br/convenios/\d+$")
PROIBIDOS = ("repositorio.dados.gov.br", "/docs", "api-publica", "api.portaldatransparencia", "apiapex")


def verbas_reais():
    config = carregar_config()
    return normalizar(carregar_retratos(RAIZ, DATA), config, DATA).verbas


def test_nenhuma_verba_aponta_para_endereco_de_coleta_ou_fora_do_ar():
    urls = {(v.fonte, f.nome[:22], f.url) for v in verbas_reais() for f in v.fontes}
    ruins = [u for u in urls if any(p in u[2] for p in PROIBIDOS)]
    assert ruins == []


def test_cada_modulo_do_transferegov_aponta_para_a_sua_consulta_publica():
    fontes = carregar_config().fontes.fontes
    por_fonte = {}
    for v in verbas_reais():
        por_fonte.setdefault(v.fonte, set()).update(f.url for f in v.fontes if f.nome.startswith("Transferegov"))
    acesso_livre = "https://www.gov.br/transferegov/pt-br/sistemas/acesso-livre"
    assert por_fonte["transferegov_discricionarias"] == {acesso_livre} == por_fonte["siconv_programa"]
    assert por_fonte["transferegov_parcerias"] == {fontes["transferegov_api"].consulta_por_modulo["parcerias"]}
    assert por_fonte["transferegov_fundoafundo"] == {fontes["transferegov_api"].consulta_por_modulo["fundoafundo"]}
    assert por_fonte["transferegov_parcerias"] != por_fonte["transferegov_fundoafundo"]


def test_o_portal_aponta_para_a_pagina_do_proprio_convenio():
    portal = [f for v in verbas_reais() for f in v.fontes if f.nome.startswith("Portal")]
    assert len(portal) == 6 and all(PORTAL_CONVENIO.match(f.url) for f in portal)
    assert len({f.url for f in portal}) == 6  # um convênio por verba, sem repetir


def test_publicado_atual_nao_tem_link_morto_nas_verbas_nem_nas_fontes():
    publicado = json.loads((RAIZ / "dados" / "publicados" / "verbas.json").read_text(encoding="utf-8"))
    urls = {f["url"] for v in publicado["verbas"] for f in v["fontes"]} | {f["url"] for f in publicado["fontes"].values()}
    assert [u for u in urls if any(p in u for p in PROIBIDOS)] == []


def test_citacoes_aprovadas_nao_apontam_para_o_endereco_morto():
    for arquivo in (RAIZ / "dados" / "curadoria").glob("*.yaml"):
        for c in yaml.safe_load(arquivo.read_text(encoding="utf-8"))["citacoes"]:
            assert "repositorio.dados.gov.br" not in c["url"], arquivo.name


def test_portal_sem_codigo_cai_na_consulta_em_vez_de_quebrar():
    config = carregar_config()
    assert config.fontes.fontes["portal_transparencia"].url_registro.format(codigo=734297) == "https://portaldatransparencia.gov.br/convenios/734297"
    assert config.fontes.fontes["portal_transparencia"].url_consulta == "https://portaldatransparencia.gov.br/convenios/consulta"
