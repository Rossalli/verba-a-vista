"""Coletor do Obrasgov (API nova, sob /obras). Ver docs/fontes.md §Obrasgov.

- O único filtro por município é `geometria.cod_ibge`; os projetos vêm por `id_projeto_investimento`.
- Guarda tudo que a API devolve para esses projetos (inclusive projetos de outros executores, como o do
  DNIT): quem decide o que entra no site é a normalização (D8: o Obrasgov é fonte auxiliar).
- A ponte `siconv_dados_obrasgov_geral` liga projeto a `nr_instrumento` (NR_CONVENIO do Siconv). A coluna
  `link_transparencia` dela traz usuário e senha `guest` na URL e **não é guardada**.
"""

import csv
import io
import zipfile
from datetime import date

from coleta.base import ColetaErro, Http, RetratoBruto, agora
from nucleo.config import Config, carregar_config

FONTE = "obrasgov"
OPCOES: tuple[str, ...] = ()
PAGINA = 200
ARQUIVO_PONTE = "siconv_dados_obrasgov_geral.zip"
ENDPOINTS_POR_PROJETO = {
    "execucao-fisica": "execucao_fisica",
    "historico-situacao-cancelada-paralisada": "historico_situacao",
    "contrato": "contrato",
    "empenho": "empenho",
}

# Parâmetros aceitos por endpoint (a API ignora parâmetro desconhecido e devolve tudo).
PARAMETROS = {
    "data-atualizacao": set(),
    "geometria": {"cod_ibge", "id_projeto_investimento", "pagina", "tamanho_da_pagina"},
    "projeto-investimento": {"id_projeto_investimento", "pagina", "tamanho_da_pagina"},
    "execucao-fisica": {"id_projeto_investimento", "pagina", "tamanho_da_pagina"},
    "historico-situacao-cancelada-paralisada": {"id_projeto_investimento", "pagina", "tamanho_da_pagina"},
    "contrato": {"id_projeto_investimento", "pagina", "tamanho_da_pagina"},
    "empenho": {"id_projeto_investimento", "pagina", "tamanho_da_pagina"},
}


def criar_http(config: Config) -> Http:
    return Http.da_config(config, intervalo_minimo_s=0.3)


def _chamar(http: Http, base: str, endpoint: str, **params) -> dict:
    desconhecidos = set(params) - PARAMETROS[endpoint]
    if desconhecidos:
        raise ValueError(f"{endpoint}: parâmetros fora da lista: {sorted(desconhecidos)}")
    return http.get_json(f"{base}/{endpoint}", params)


def _todos(http: Http, base: str, endpoint: str, **params) -> list[dict]:
    registros: list[dict] = []
    pagina = 1
    while True:
        corpo = _chamar(http, base, endpoint, **params, pagina=pagina, tamanho_da_pagina=PAGINA)
        registros += corpo["data"]
        if pagina >= corpo["total_pages"]:
            return registros
        pagina += 1


def ler_ponte(conteudo: bytes, ids: set[str]) -> list[dict]:
    """Linhas da ponte dos projetos pedidos, só com id e instrumento (sem o link com senha guest)."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        (nome,) = zf.namelist()
        linhas = zf.read(nome).decode("utf-8-sig").splitlines()
    leitor = csv.DictReader(linhas, delimiter=";")
    if not {"id_projeto_investimento", "nr_instrumento"} <= set(leitor.fieldnames or []):
        raise ColetaErro(f"ponte Siconv-Obrasgov com colunas inesperadas: {leitor.fieldnames}")
    return [{"id_projeto_investimento": r["id_projeto_investimento"], "nr_instrumento": r["nr_instrumento"]} for r in leitor if r["id_projeto_investimento"] in ids]


def coletar(data: date, *, config: Config | None = None, http: Http | None = None) -> RetratoBruto:
    config = config or carregar_config()
    http = http or criar_http(config)
    base = config.fontes.fontes[FONTE].base_url
    ibge = int(config.regras.municipio.codigo_ibge)

    atualizacao = _chamar(http, base, "data-atualizacao")
    geometrias = _todos(http, base, "geometria", cod_ibge=ibge)
    fora = [g for g in geometrias if g["cod_ibge"] != ibge]
    if fora:
        raise ColetaErro(f"Obrasgov: {len(fora)} geometrias não são do IBGE {ibge}: {fora[0]}")
    ids = sorted({g["id_projeto_investimento"] for g in geometrias})

    dados: dict[str, list[dict]] = {"geometria": geometrias, "projeto_investimento": []}
    dados.update({recurso: [] for recurso in ENDPOINTS_POR_PROJETO.values()})
    for projeto in ids:
        dados["projeto_investimento"] += _todos(http, base, "projeto-investimento", id_projeto_investimento=projeto)
        for endpoint, recurso in ENDPOINTS_POR_PROJETO.items():
            dados[recurso] += _todos(http, base, endpoint, id_projeto_investimento=projeto)
    if len(dados["projeto_investimento"]) != len(ids):
        raise ColetaErro(f"Obrasgov: {len(ids)} projetos na geometria, mas {len(dados['projeto_investimento'])} em projeto-investimento")

    url_ponte = f"{config.fontes.fontes['transferegov_discricionarias'].url}/{ARQUIVO_PONTE}"
    dados["ponte_siconv"] = ler_ponte(http.get(url_ponte).content, set(ids))

    return RetratoBruto(
        fonte=FONTE,
        data=data,
        coletado_em=agora(config),
        metadados={"data_ultima_atualizacao": atualizacao.get("data_ultima_atualizacao"), "projetos": ids, "ponte": url_ponte},
        dados=dados,
    )
