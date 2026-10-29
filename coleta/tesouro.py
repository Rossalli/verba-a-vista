"""Coletor das Transferências Constitucionais do Tesouro (FPM, ITR e outras). Ver docs/fontes.md §Tesouro.

Cuidados da API (sem OpenAPI, nomes confirmados por chamadas reais):
- os parâmetros diferem de caixa entre endpoints, e um nome errado faz o servidor tentar devolver a série
  inteira e estourar o tempo; por isso só os nomes da lista PARAMETROS são aceitos;
- `por_estado_municipio` é paginado e o campo `next` vem sempre preenchido: parar na página incompleta;
- o código do município é o do Tesouro (6751 = Código SIAFI), não o IBGE;
- o mês corrente vem incompleto (3º decêndio zerado): o detalhe do último mês fica no retrato.
"""

from datetime import date

from coleta.base import ColetaErro, Http, RetratoBruto, agora
from nucleo.config import Config, carregar_config

FONTE = "tesouro_constitucionais"
OPCOES: tuple[str, ...] = ()
PAGINA = 500
TRANSFERENCIAS_DO_DETALHE = ("FPM", "ITR")

# Parâmetros aceitos por endpoint, com a caixa exata que a API exige.
PARAMETROS = {
    "transferencias": set(),
    "estados": set(),
    "municipios": {"p_nome", "p_uf"},
    "por_estado_municipio": {"p_estado", "p_municipio", "p_ano", "p_mes", "p_transferencia", "p_sn_detalhar", "page", "pageSize"},
    "por_estado_municipio_detalhe": {"P_ESTADO", "P_MUNICIPIOS", "P_ANO", "P_MES", "P_TRANSFERENCIA"},
}


def criar_http(config: Config) -> Http:
    return Http.da_config(config, intervalo_minimo_s=0.5)


def _chamar(http: Http, base: str, endpoint: str, **params) -> dict:
    desconhecidos = set(params) - PARAMETROS[endpoint]
    if desconhecidos:
        raise ValueError(f"{endpoint}: parâmetros fora da lista (a caixa importa): {sorted(desconhecidos)}")
    corpo = http.get_json(f"{base}/{endpoint}", params)
    if corpo.get("status") != "ok":
        raise ColetaErro(f"Tesouro {endpoint}: status {corpo.get('status')!r}: {str(corpo)[:200]}")
    return corpo


def _todas(http: Http, base: str, endpoint: str, **params) -> list[dict]:
    registros: list[dict] = []
    pagina = 1
    while True:
        lote = _chamar(http, base, endpoint, **params, page=pagina, pageSize=PAGINA)["registros"]
        registros += lote
        if len(lote) < PAGINA:
            return registros
        pagina += 1


def coletar(data: date, *, config: Config | None = None, http: Http | None = None) -> RetratoBruto:
    config = config or carregar_config()
    http = http or criar_http(config)
    base = config.fontes.fontes[FONTE].base_url
    municipio = config.regras.municipio
    ibge = int(municipio.codigo_ibge)

    tipos = _chamar(http, base, "transferencias")["registros"]
    estados = _chamar(http, base, "estados")["registros"]
    achados = [m for m in _chamar(http, base, "municipios", p_nome=municipio.nome)["registros"] if m["nome"] == municipio.nome]
    if len(achados) != 1:
        raise ColetaErro(f"Tesouro: esperava 1 município chamado {municipio.nome!r}, achei {len(achados)}")
    codigo, codigo_uf = achados[0]["codigo"], achados[0]["codigo_uf"]
    estado = next((e["nome"] for e in estados if e["codigo"] == codigo_uf), None)

    linhas: list[dict] = []
    anos = list(range(municipio.inicio_recorte.year, data.year + 1))
    for ano in anos:
        linhas += _todas(http, base, "por_estado_municipio", p_estado=codigo_uf, p_municipio=codigo, p_ano=ano)
    if not linhas:
        raise ColetaErro(f"Tesouro: nenhuma transferência para o código {codigo} em {anos[0]}-{anos[-1]}")
    fora = [r for r in linhas if r["CO_IBGE"] != ibge or r["codigo_siafi"] != codigo or r["UF"] != municipio.uf]
    if fora:
        raise ColetaErro(f"Tesouro: {len(fora)} linhas não são do município (CO_IBGE/codigo_siafi/UF): {fora[0]}")

    ultimo = max((r["ANO"], r["MES"]) for r in linhas if r["TRANSFERENCIA"] == "FPM")
    codigos_tipos = {t["transferencia"]: t["codigo"] for t in tipos}
    detalhe: list[dict] = []
    for nome in TRANSFERENCIAS_DO_DETALHE:
        detalhe += _chamar(
            http, base, "por_estado_municipio_detalhe",
            P_ESTADO=codigo_uf, P_MUNICIPIOS=codigo, P_ANO=ultimo[0], P_MES=int(ultimo[1]), P_TRANSFERENCIA=codigos_tipos[nome],
        )["registros"]

    return RetratoBruto(
        fonte=FONTE,
        data=data,
        coletado_em=agora(config),
        metadados={"codigo_tesouro": codigo, "codigo_uf": codigo_uf, "estado": estado, "anos": anos, "ultimo_mes_fpm": f"{ultimo[0]}-{ultimo[1]}"},
        dados={"transferencias": tipos, "por_estado_municipio": linhas, "detalhe": detalhe},
    )
