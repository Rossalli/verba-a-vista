"""Coletor do CAUC (Tesouro Nacional) via dataset do Tesouro Transparente (CKAN). Ver docs/fontes.md §CAUC.

O CSV traz todos os municípios do país; guarda-se só a linha do município e a legenda dos itens.
O arquivo é um retrato do dia sem histórico: o histórico sai das nossas coletas.
"""

import csv
import re
from datetime import date, datetime

from coleta.base import ColetaErro, Http, RetratoBruto, agora
from nucleo.config import Config, carregar_config

FONTE = "cauc"
OPCOES: tuple[str, ...] = ()
NOME_RECURSO = "Relatório da situação dos municípios no CAUC"
ENCODING = "cp1252"
LINHAS_METADADOS = 3
COLUNA_ITEM = re.compile(r"\d\.\d(\.\d)?")
CELULA_DATA = re.compile(r"\d{2}/\d{2}/\d{2}")


def criar_http(config: Config) -> Http:
    return Http.da_config(config)


def escolher_recurso(pacote: dict) -> dict:
    """Recurso CSV de municípios, achado pelo nome (o endereço do arquivo é um upload e pode mudar)."""
    candidatos = [r for r in pacote["resources"] if r.get("name") == NOME_RECURSO and (r.get("format") or "").upper() == "CSV"]
    if len(candidatos) != 1:
        raise ColetaErro(f"CAUC: esperava 1 recurso CSV {NOME_RECURSO!r} no dataset, achei {len(candidatos)}")
    return candidatos[0]


def ler_cauc(dados: bytes) -> tuple[dict, list[str], list[list[str]], dict[str, str]]:
    """Devolve (metadados, cabeçalho, entes, legenda). Linha curta fora da legenda é erro."""
    linhas = dados.decode(ENCODING).splitlines()
    brutos = [linha.strip().strip('"') for linha in linhas[:LINHAS_METADADOS]]
    achado = re.search(r"(\d{2}/\d{2}/\d{4})", brutos[0])
    if not achado:
        raise ColetaErro(f"CAUC: data da pesquisa não encontrada em {brutos[0]!r}")
    meta = {
        "data_pesquisa": datetime.strptime(achado.group(1), "%d/%m/%Y").date().isoformat(),
        "tipo_ente": brutos[1].split(":", 1)[1].strip(),
        "abrangencia": brutos[2].split(":", 1)[1].strip(),
    }
    tabela = list(csv.reader(linhas[LINHAS_METADADOS:], delimiter=";"))
    cabecalho, resto = tabela[0], tabela[1:]
    entes: list[list[str]] = []
    legenda_linhas: list[list[str]] = []
    for linha in resto:
        if len(linha) == len(cabecalho) and not legenda_linhas:
            entes.append(linha)
        elif len(linha) == 2:
            legenda_linhas.append(linha)
        else:
            raise ColetaErro(f"CAUC: linha com {len(linha)} colunas fora da legenda: {linha[:3]}")
    return meta, cabecalho, entes, {codigo: nome for codigo, nome in legenda_linhas[1:]}


def validar_celulas(linha: dict[str, str]) -> None:
    """Cada item é `!`, `Desabilitado`, vazio ou data dd/mm/aa. Valor novo é erro, nunca é interpretado."""
    for coluna, valor in linha.items():
        if COLUNA_ITEM.fullmatch(coluna) and valor not in ("!", "Desabilitado", "") and not CELULA_DATA.fullmatch(valor):
            raise ColetaErro(f"CAUC: valor não reconhecido no item {coluna}: {valor!r}")
        if COLUNA_ITEM.fullmatch(coluna) and CELULA_DATA.fullmatch(valor):
            try:
                datetime.strptime(valor, "%d/%m/%y")
            except ValueError as e:
                raise ColetaErro(f"CAUC: data inválida no item {coluna}: {valor!r}") from e


def coletar(data: date, *, config: Config | None = None, http: Http | None = None) -> RetratoBruto:
    config = config or carregar_config()
    http = http or criar_http(config)
    ibge = config.regras.municipio.codigo_ibge
    pacote = http.get_json(config.fontes.fontes[FONTE].url)["result"]
    recurso = escolher_recurso(pacote)
    resp = http.get(recurso["url"])
    meta, cabecalho, entes, legenda = ler_cauc(resp.content)
    if meta["tipo_ente"] != "Municípios":
        raise ColetaErro(f"CAUC: o arquivo é de {meta['tipo_ente']!r}, esperava 'Municípios'")
    linhas = [dict(zip(cabecalho, e, strict=True)) for e in entes if e[cabecalho.index("Código IBGE")] == ibge]
    if len(linhas) != 1:
        raise ColetaErro(f"CAUC: esperava 1 linha para o IBGE {ibge}, achei {len(linhas)}")
    validar_celulas(linhas[0])
    return RetratoBruto(
        fonte=FONTE,
        data=data,
        coletado_em=agora(config),
        metadados={
            **meta,
            "recurso": {"url": recurso["url"], "last_modified": recurso.get("last_modified"), "size": recurso.get("size")},
            "http": {"last_modified": resp.headers.get("last-modified"), "etag": resp.headers.get("etag")},
            "entes_no_arquivo": len(entes),
        },
        dados={"entes": linhas, "legenda": [{"codigo": c, "exigencia": n} for c, n in legenda.items()]},
    )
