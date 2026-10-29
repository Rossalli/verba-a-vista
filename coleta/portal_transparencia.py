"""Coletor do Portal da Transparência (CGU). Ver docs/fontes.md §Portal e D11 (fonte de complemento).

Limite da API: 400 requisições/min; acima disso a chave fica suspensa por 8 h. Por isso:
- intervalo mínimo calculado de `coleta.portal_transparencia_req_por_min` (nunca acima de `limite_req_min`);
- teto de MAX_REQUISICOES por execução (conta também as repetições);
- 401, 403 e 429 interrompem a fonte na hora, sem nova tentativa (`AcessoNegadoErro`).

A chave vem só da variável de ambiente PORTAL_TRANSPARENCIA_KEY e nunca é gravada nem aparece em erros.

O que se coleta (e o que não): `convenios` por `codigoIBGE`; `recursos-recebidos` e
`documentos-por-favorecido` por CNPJ (o filtro `codigoIBGE` de `recursos-recebidos` devolve vazio); janelas de
até 12 meses. `/emendas` não entra: a emenda vem agregada (`MÚLTIPLO`), sem o valor do município.
"""

import os
from datetime import date

from coleta.base import ColetaErro, Http, RetratoBruto, agora
from nucleo.config import Config, carregar_config

FONTE = "portal_transparencia"
OPCOES: tuple[str, ...] = ()
VARIAVEL_CHAVE = "PORTAL_TRANSPARENCIA_KEY"
MAX_REQUISICOES = 400
MAX_PAGINAS = 40
FASE_PAGAMENTO = 3

PARAMETROS = {
    "convenios": {"codigoIBGE", "pagina"},
    "despesas/recursos-recebidos": {"mesAnoInicio", "mesAnoFim", "codigoFavorecido", "pagina"},
    "despesas/documentos-por-favorecido": {"codigoPessoa", "fase", "ano", "pagina"},
}


def criar_http(config: Config) -> Http:
    chave = os.environ.get(VARIAVEL_CHAVE)
    if not chave:
        raise ColetaErro(f"{VARIAVEL_CHAVE} não definida (variável de ambiente)")
    limite = min(config.regras.coleta.portal_transparencia_req_por_min, config.fontes.fontes[FONTE].limite_req_min or 400)
    return Http.da_config(
        config,
        intervalo_minimo_s=60.0 / limite,
        parar_em=frozenset({401, 403, 429}),
        max_requisicoes=MAX_REQUISICOES,
        cabecalhos={"chave-api-dados": chave, "Accept": "application/json"},
    )


def _todas(http: Http, base: str, endpoint: str, **params) -> list[dict]:
    """15 itens por página e sem total: pagina até vir uma página vazia."""
    desconhecidos = set(params) - PARAMETROS[endpoint]
    if desconhecidos:
        raise ValueError(f"{endpoint}: parâmetros fora da lista: {sorted(desconhecidos)}")
    itens: list[dict] = []
    for pagina in range(1, MAX_PAGINAS + 1):
        lote = http.get_json(f"{base}/{endpoint}", {**params, "pagina": pagina})
        if not lote:
            return itens
        itens += lote
    raise ColetaErro(f"Portal {endpoint}: mais de {MAX_PAGINAS} páginas, interrompido por segurança")


def janelas_de_um_ano(inicio: date, fim: date) -> list[tuple[str, str]]:
    """(`MM/AAAA` inicial, `MM/AAAA` final) por ano, de `inicio.year` a `fim.year`; o último vai até o mês de `fim`."""
    return [(f"01/{ano}", f"12/{ano}" if ano < fim.year else f"{fim.month:02d}/{ano}") for ano in range(inicio.year, fim.year + 1)]


def coletar(data: date, *, config: Config | None = None, http: Http | None = None) -> RetratoBruto:
    config = config or carregar_config()
    http = http or criar_http(config)
    base = config.fontes.fontes[FONTE].base_url
    municipio = config.regras.municipio
    cnpjs = list(dict.fromkeys([c for c in [municipio.cnpj_prefeitura, *municipio.cnpjs_fundos] if c]))
    janelas = janelas_de_um_ano(municipio.inicio_recorte, data)

    convenios = _todas(http, base, "convenios", codigoIBGE=municipio.codigo_ibge)
    fora = [c["id"] for c in convenios if c["municipioConvenente"]["codigoIBGE"] != municipio.codigo_ibge]
    if fora:
        raise ColetaErro(f"Portal convenios: {len(fora)} convênios de outro IBGE (ex.: id {fora[0]})")

    recursos = [
        r for cnpj in cnpjs for inicio, fim in janelas
        for r in _todas(http, base, "despesas/recursos-recebidos", mesAnoInicio=inicio, mesAnoFim=fim, codigoFavorecido=cnpj)
    ]
    pagamentos = [
        d for cnpj in cnpjs for ano in range(municipio.inicio_recorte.year, data.year + 1)
        for d in _todas(http, base, "despesas/documentos-por-favorecido", codigoPessoa=cnpj, fase=FASE_PAGAMENTO, ano=ano)
    ]
    return RetratoBruto(
        fonte=FONTE,
        data=data,
        coletado_em=agora(config),
        metadados={"cnpjs": cnpjs, "janelas_recursos_recebidos": [list(j) for j in janelas], "fase_documentos": FASE_PAGAMENTO},
        dados={"convenios": convenios, "recursos_recebidos": recursos, "documentos_pagamento": pagamentos},
    )
