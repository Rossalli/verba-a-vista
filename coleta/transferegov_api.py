"""Coletor da API pública do Transferegov: parcerias, fundoafundo e especiais. Ver docs/fontes.md §Transferegov.

- Parâmetro desconhecido é ignorado pela API (que devolve a tabela inteira): só os nomes de PARAMETROS
  (lidos do OpenAPI de cada módulo) são aceitos.
- `fundoafundo/planos-acao` dá HTTP 500 com qualquer filtro de código IBGE: filtra-se pelo CNPJ.
- Dados bancários e e-mail nunca entram no retrato (`limpar`).
"""

from datetime import date

from coleta.base import ColetaErro, Http, RetratoBruto, agora
from nucleo.config import Config, carregar_config

FONTE = "transferegov_api"
OPCOES: tuple[str, ...] = ()
PAGINA = 200
SENSIVEIS = ("numero_conta", "numero_agencia", "dv_conta", "dv_agencia", "email", "nome_agencia")
_PAG = {"pagina", "tamanho_da_pagina"}

PARAMETROS = {
    ("parcerias", "data-atualizacao"): set(),
    ("parcerias", "proposta"): {"cd_ibge_recebedor"} | _PAG,
    ("parcerias", "parceria"): {"id_proposta"} | _PAG,
    ("parcerias", "programa"): {"id_programa"} | _PAG,
    ("parcerias", "beneficiario_emenda_parlamentar"): {"nm_municipio_beneficiario_emenda", "sg_uf_beneficiario_emenda"} | _PAG,
    ("fundoafundo", "data-atualizacao"): set(),
    ("fundoafundo", "planos-acao"): {"cnpj_ente_recebedor_plano_acao"} | _PAG,
    ("fundoafundo", "termos-adesao"): {"id_plano_acao"} | _PAG,
    ("fundoafundo", "programas-beneficiarios"): {"codigo_ibge_municipio_ente_beneficiario_programa"} | _PAG,
    ("fundoafundo", "programas"): {"id_programa"} | _PAG,
    ("especiais", "data-atualizacao"): set(),
    ("especiais", "beneficiarios-especiais"): {"cnpj_beneficiario"} | _PAG,
    ("especiais", "planos-acao-especiais"): {"id_beneficiario"} | _PAG,
    ("especiais", "planos-trabalho-especiais"): {"id_plano_acao"} | _PAG,
}


def criar_http(config: Config) -> Http:
    return Http.da_config(config, intervalo_minimo_s=0.3)


def limpar(registro: dict) -> dict:
    """Tira dados bancários e e-mail: ficam só os campos de que a análise precisa."""
    return {k: v for k, v in registro.items() if not any(s in k for s in SENSIVEIS)}


def _todos(http: Http, base: str, modulo: str, endpoint: str, **params) -> list[dict]:
    desconhecidos = set(params) - PARAMETROS[(modulo, endpoint)]
    if desconhecidos:
        raise ValueError(f"{modulo}/{endpoint}: parâmetros fora da lista: {sorted(desconhecidos)}")
    registros: list[dict] = []
    pagina = 1
    while True:
        corpo = http.get_json(f"{base}/{modulo}/{endpoint}", {**params, "pagina": pagina, "tamanho_da_pagina": PAGINA})
        registros += corpo["data"]
        if pagina >= corpo["total_pages"]:
            return registros
        pagina += 1


def _unicos(registros: list[dict], chave: str) -> list[dict]:
    vistos: set = set()
    saida = []
    for r in registros:
        if r[chave] not in vistos:
            vistos.add(r[chave])
            saida.append(r)
    return saida


def coletar(data: date, *, config: Config | None = None, http: Http | None = None) -> RetratoBruto:
    config = config or carregar_config()
    http = http or criar_http(config)
    base = config.fontes.fontes[FONTE].base_url
    municipio = config.regras.municipio
    ibge = int(municipio.codigo_ibge)
    cnpjs = list(dict.fromkeys([c for c in [municipio.cnpj_prefeitura, *municipio.cnpjs_fundos] if c]))

    atualizacao = {m: http.get_json(f"{base}/{m}/data-atualizacao") for m in ("parcerias", "fundoafundo", "especiais")}

    # parcerias (módulo novo, sem os convênios antigos)
    propostas = _todos(http, base, "parcerias", "proposta", cd_ibge_recebedor=ibge)
    fora = [p["id_proposta"] for p in propostas if p["cd_ibge_recebedor"] != ibge]
    if fora:
        raise ColetaErro(f"Transferegov parcerias/proposta: {len(fora)} propostas de outro IBGE (ex.: {fora[0]})")
    parcerias = [r for p in propostas for r in _todos(http, base, "parcerias", "parceria", id_proposta=p["id_proposta"])]
    programas_parcerias = [r for i in sorted({p["id_programa"] for p in propostas}) for r in _todos(http, base, "parcerias", "programa", id_programa=i)]
    emendas = _todos(http, base, "parcerias", "beneficiario_emenda_parlamentar", nm_municipio_beneficiario_emenda=municipio.nome.upper(), sg_uf_beneficiario_emenda=municipio.uf)

    # fundo a fundo
    planos = _unicos([r for c in cnpjs for r in _todos(http, base, "fundoafundo", "planos-acao", cnpj_ente_recebedor_plano_acao=c)], "id_plano_acao")
    fora = [p["id_plano_acao"] for p in planos if p["codigo_ibge_municipio_ente_recebedor_plano_acao"] != ibge]
    if fora:
        raise ColetaErro(f"Transferegov fundoafundo/planos-acao: {len(fora)} planos de outro IBGE (ex.: {fora[0]})")
    termos = [r for p in planos for r in _todos(http, base, "fundoafundo", "termos-adesao", id_plano_acao=p["id_plano_acao"])]
    beneficiarios_faf = _todos(http, base, "fundoafundo", "programas-beneficiarios", codigo_ibge_municipio_ente_beneficiario_programa=ibge)
    ids_faf = sorted({r["id_programa"] for r in [*planos, *beneficiarios_faf]})
    programas_faf = [r for i in ids_faf for r in _todos(http, base, "fundoafundo", "programas", id_programa=i)]

    # emendas Pix (especiais): o município pode não ter registros (T1.1)
    beneficiarios_esp = _unicos([r for c in cnpjs for r in _todos(http, base, "especiais", "beneficiarios-especiais", cnpj_beneficiario=c)], "id_beneficiario")
    planos_esp = [r for b in beneficiarios_esp for r in _todos(http, base, "especiais", "planos-acao-especiais", id_beneficiario=b["id_beneficiario"])]
    trabalhos_esp = [r for p in planos_esp for r in _todos(http, base, "especiais", "planos-trabalho-especiais", id_plano_acao=p["id_plano_acao"])]

    dados = {
        "parcerias.proposta": propostas,
        "parcerias.parceria": parcerias,
        "parcerias.programa": programas_parcerias,
        "parcerias.beneficiario_emenda_parlamentar": emendas,
        "fundoafundo.planos_acao": planos,
        "fundoafundo.termos_adesao": termos,
        "fundoafundo.programas_beneficiarios": beneficiarios_faf,
        "fundoafundo.programas": programas_faf,
        "especiais.beneficiarios": beneficiarios_esp,
        "especiais.planos_acao": planos_esp,
        "especiais.planos_trabalho": trabalhos_esp,
    }
    return RetratoBruto(
        fonte=FONTE,
        data=data,
        coletado_em=agora(config),
        metadados={"data_atualizacao": atualizacao, "cnpjs_consultados": cnpjs},
        dados={recurso: [limpar(r) for r in registros] for recurso, registros in dados.items()},
    )
