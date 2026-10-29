import io
import json
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from coleta import obrasgov
from coleta.base import ColetaErro, Http
from nucleo.config import carregar_config

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "obrasgov"
DIA = date(2026, 10, 29)


def amostra(nome):
    return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))["amostra"]


@pytest.fixture
def config():
    return carregar_config()


def http_falso():
    return Http(tentativas=1, backoff_inicial_s=0, dormir=lambda _s: None)


def zip_da_ponte(linhas):
    cabecalho = "﻿id_projeto_investimento;nr_instrumento;programa_governo;link_transparencia\n"
    corpo = "".join(f"{i};{n};;https://discricionarias.exemplo/x?idProposta=1&Usr=guest&Pwd=guest\n" for i, n in linhas)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("siconv_dados_obrasgov_geral.csv", (cabecalho + corpo).encode("utf-8"))
    return buffer.getvalue()


def mockar(config, *, geometrias=None, projetos=None, ponte=None):
    base = config.fontes.fontes["obrasgov"].base_url
    geos = geometrias if geometrias is not None else amostra("geometria")
    projs = projetos if projetos is not None else amostra("projeto-investimento")
    por_projeto = {r: amostra(r) for r in ("execucao-fisica", "historico-situacao-cancelada-paralisada", "contrato", "empenho")}
    chamadas = []

    def pagina(linhas, p):
        tamanho, n = int(p["tamanho_da_pagina"]), int(p["pagina"])
        total = max(1, -(-len(linhas) // tamanho))
        return {"data": linhas[(n - 1) * tamanho : n * tamanho], "total_pages": total, "total_items": len(linhas), "page_number": n, "page_size": tamanho}

    def tratar(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        p = dict(request.url.params)
        chamadas.append((endpoint, p))
        if endpoint == "data-atualizacao":
            return httpx.Response(200, json={"data_ultima_atualizacao": "2026-10-29T00:00:00"})
        if endpoint == "geometria":
            return httpx.Response(200, json=pagina([g for g in geos if str(g["cod_ibge"]) == p["cod_ibge"]], p))
        if endpoint == "projeto-investimento":
            return httpx.Response(200, json=pagina([x for x in projs if x["id_projeto_investimento"] == p["id_projeto_investimento"]], p))
        if endpoint in por_projeto:
            return httpx.Response(200, json=pagina([x for x in por_projeto[endpoint] if x["id_projeto_investimento"] == p["id_projeto_investimento"]], p))
        return httpx.Response(404)

    respx.get(url__startswith=base).mock(side_effect=tratar)
    url_ponte = f"{config.fontes.fontes['transferegov_discricionarias'].url}/siconv_dados_obrasgov_geral.zip"
    conteudo = ponte if ponte is not None else zip_da_ponte(
        [("106169.35-86", "990509"), ("31694.35-09", "925702"), ("47960.35-00", "970941"), ("99999.99-99", "111111")]
    )
    respx.get(url_ponte).mock(return_value=httpx.Response(200, content=conteudo))
    return chamadas


@respx.mock
def test_coleta_projetos_do_municipio_e_seus_recursos(config):
    mockar(config)
    retrato = obrasgov.coletar(DIA, config=config, http=http_falso())
    assert retrato.fonte == "obrasgov"
    assert retrato.metadados["data_ultima_atualizacao"] == "2026-10-29T00:00:00"
    assert retrato.metadados["projetos"] == ["106169.35-86", "31694.35-09", "328.35-98", "47960.35-00"]
    c = retrato.contagens()
    assert c["geometria"] == 4 and c["projeto_investimento"] == 4
    assert c["execucao_fisica"] == 0 and c["historico_situacao"] == 0  # o município não tem registros (T1.3)
    assert c["contrato"] == 7 and c["empenho"] == 46
    # fica também o projeto do DNIT: quem o descarta é a normalização (D8), não a coleta
    assert {p["id_projeto_investimento"] for p in retrato.dados["projeto_investimento"]} >= {"328.35-98"}


@respx.mock
def test_filtra_pelo_ibge_e_nunca_envia_parametro_fora_da_lista(config):
    chamadas = mockar(config)
    obrasgov.coletar(DIA, config=config, http=http_falso())
    geo = [p for e, p in chamadas if e == "geometria"]
    assert geo[0]["cod_ibge"] == "3532504"
    for endpoint, params in chamadas:
        assert set(params) <= obrasgov.PARAMETROS[endpoint]


@respx.mock
def test_ponte_guarda_so_id_e_instrumento_dos_projetos_do_municipio_sem_o_link_guest(config):
    mockar(config)
    retrato = obrasgov.coletar(DIA, config=config, http=http_falso())
    assert retrato.dados["ponte_siconv"] == [
        {"id_projeto_investimento": "106169.35-86", "nr_instrumento": "990509"},
        {"id_projeto_investimento": "31694.35-09", "nr_instrumento": "925702"},
        {"id_projeto_investimento": "47960.35-00", "nr_instrumento": "970941"},
    ]  # o do DNIT não tem linha; o "99999.99-99" de outro município fica de fora
    assert "guest" not in json.dumps(retrato.dados, ensure_ascii=False)


@respx.mock
def test_geometria_de_outro_municipio_e_erro(config):
    intruso = {**amostra("geometria")[0], "cod_ibge": 3550308}
    respx.reset()
    base = config.fontes.fontes["obrasgov"].base_url
    respx.get(f"{base}/data-atualizacao").mock(return_value=httpx.Response(200, json={"data_ultima_atualizacao": "x"}))
    respx.get(f"{base}/geometria").mock(return_value=httpx.Response(200, json={"data": [intruso], "total_pages": 1, "total_items": 1}))
    with pytest.raises(ColetaErro, match="não são do IBGE 3532504"):
        obrasgov.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_projeto_que_some_entre_geometria_e_projeto_investimento_e_erro(config):
    mockar(config, projetos=amostra("projeto-investimento")[:3])
    with pytest.raises(ColetaErro, match="4 projetos na geometria, mas 3 em projeto-investimento"):
        obrasgov.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_ponte_com_colunas_inesperadas_e_erro(config):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("x.csv", "a;b\n1;2\n")
    mockar(config, ponte=buffer.getvalue())
    with pytest.raises(ColetaErro, match="colunas inesperadas"):
        obrasgov.coletar(DIA, config=config, http=http_falso())


@respx.mock
def test_pagina_ate_total_pages(config, monkeypatch):
    monkeypatch.setattr(obrasgov, "PAGINA", 2)
    chamadas = mockar(config)
    obrasgov.coletar(DIA, config=config, http=http_falso())
    paginas_empenho = [p["pagina"] for e, p in chamadas if e == "empenho" and p["id_projeto_investimento"] == "328.35-98"]
    assert paginas_empenho == [str(i) for i in range(1, 22 + 1)]  # 43 empenhos do DNIT, 2 por página: ceil(43/2) = 22
