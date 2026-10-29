"""Coletor do Transferegov Discricionárias e Legais (antigo Siconv), CSV em lote. Ver docs/fontes.md.

Cobre convênios e contratos de repasse (propostas, convênios, emendas, histórico de situação, desembolsos,
prorrogações) e as oportunidades (programas, programas dirigidos, Novo PAC Seleções; spec §4, D10).

- A carga do Siconv é antiga (`data_carga_siconv.txt`): a data dela vai nos metadados e o site a mostra.
- Os zips (~340 MB só os de convênios, mais ~370 MB dos programas) ficam em cache FORA do Git
  (`.cache/siconv`); o download é pulado quando o tamanho no servidor não mudou.
- `siconv_convenio` não tem município: liga por ID_PROPOSTA. `siconv_programa` repete cada programa por UF e
  natureza jurídica: guarda-se só as linhas de natureza municipal e UF do município (ou sem UF).
- `siconv_proponentes` traz e-mail e telefone: só id, CNPJ e nome da prefeitura ficam no retrato.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from coleta import siconv
from coleta.base import RAIZ, ColetaErro, Http, RetratoBruto, agora
from nucleo.config import Config, carregar_config

FONTE = "transferegov_discricionarias"
OPCOES = ("cache",)
CACHE_PADRAO = RAIZ / ".cache" / "siconv"
JANELAS = ("RECEB_PROP", "EMENDA_PAR", "BENEF_ESP")
COLUNAS_PROPONENTE = ["ID_PROPONENTE", "IDENTIF_PROPONENTE", "NM_PROPONENTE"]
COLUNAS_IGNORADAS = {"proposta_selecao_pac": ["JUSTIFICATIVA_PROPOSTA_SELECAO_PAC"]}  # texto longo e livre, sem uso
ARQUIVOS = (
    "proposta", "proposta_cancelada", "convenio", "emenda", "historico_situacao", "desembolso", "prorroga_oficio",
    "programa", "programa_proponentes", "proposta_selecao_pac", "proponentes",
)


def criar_http(config: Config) -> Http:
    return Http.da_config(config, timeout_s=300.0)


def programas_relevantes(programas: pd.DataFrame, dirigidos: set[str], uf: str, data: date) -> pd.Series:
    """Máscara das linhas de `siconv_programa` que interessam ao município.

    Natureza jurídica municipal e UF do município (ou sem UF), e: o programa é dirigido à prefeitura
    (`siconv_programa_proponentes`) OU está `DISPONIBILIZADO` com alguma janela ainda não encerrada em `data`.
    """
    municipal = programas["NATUREZA_JURIDICA_PROGRAMA"].str.contains("Municipal", na=False)
    da_uf = programas["UF_PROGRAMA"].isin([uf, ""])
    referencia = pd.Timestamp(data)
    alguma_aberta = pd.Series(False, index=programas.index)
    for janela in JANELAS:
        fim = pd.to_datetime(programas[f"DT_PROG_FIM_{janela}"], format="%d/%m/%Y", errors="coerce")
        alguma_aberta |= fim.notna() & (fim >= referencia)
    disponivel = (programas["SIT_PROGRAMA"] == "DISPONIBILIZADO") & alguma_aberta
    return municipal & da_uf & (programas["ID_PROGRAMA"].isin(dirigidos) | disponivel)


def coletar(data: date, *, config: Config | None = None, http: Http | None = None, cache: Path | None = None) -> RetratoBruto:
    config = config or carregar_config()
    http = http or criar_http(config)
    cache = Path(cache) if cache else CACHE_PADRAO
    municipio = config.regras.municipio
    base = config.fontes.fontes[FONTE].url

    data_carga = http.get(f"{base}/data_carga_siconv.txt").content.decode("utf-8-sig").strip()
    zips = {nome: http.baixar(f"{base}/siconv_{nome}.csv.zip", cache / f"siconv_{nome}.csv.zip") for nome in ARQUIVOS}

    proposta = siconv.ler_filtrado(zips["proposta"], "COD_MUNIC_IBGE", {municipio.codigo_ibge})
    cancelada = siconv.ler_filtrado(zips["proposta_cancelada"], "COD_MUNIC_IBGE", {municipio.codigo_ibge})
    if proposta.empty and cancelada.empty:
        raise ColetaErro(f"Siconv: nenhuma proposta para o IBGE {municipio.codigo_ibge}")
    ids_proposta = set(proposta.get("ID_PROPOSTA", [])) | set(cancelada.get("ID_PROPOSTA", []))
    convenio = siconv.ler_filtrado(zips["convenio"], "ID_PROPOSTA", ids_proposta)
    numeros = set(convenio.get("NR_CONVENIO", []))

    proponente = siconv.ler_filtrado(zips["proponentes"], "IDENTIF_PROPONENTE", {municipio.cnpj_prefeitura})
    if len(proponente) != 1:
        raise ColetaErro(f"Siconv: esperava 1 proponente com o CNPJ {municipio.cnpj_prefeitura}, achei {len(proponente)}")
    ids_proponente = set(proponente["ID_PROPONENTE"])
    dirigidos = siconv.ler_filtrado(zips["programa_proponentes"], "ID_PROPONENTE", ids_proponente)
    ids_dirigidos = set(dirigidos["ID_PROGRAMA"]) if not dirigidos.empty else set()
    programas = siconv.ler_se(zips["programa"], lambda b: programas_relevantes(b, ids_dirigidos, municipio.uf, data))
    selecao_pac = siconv.ler_filtrado(zips["proposta_selecao_pac"], "ID_PROPONENTE", ids_proponente)

    dados = {
        "proposta": siconv.registros(proposta),
        "proposta_cancelada": siconv.registros(cancelada),
        "convenio": siconv.registros(convenio),
        "emenda": siconv.registros(siconv.ler_filtrado(zips["emenda"], "ID_PROPOSTA", ids_proposta)),
        "historico_situacao": siconv.registros(siconv.ler_filtrado(zips["historico_situacao"], "ID_PROPOSTA", ids_proposta)),
        "desembolso": siconv.registros(siconv.ler_filtrado(zips["desembolso"], "NR_CONVENIO", numeros)),
        "prorroga_oficio": siconv.registros(siconv.ler_filtrado(zips["prorroga_oficio"], "NR_CONVENIO", numeros)),
        "proponente": siconv.registros(proponente, COLUNAS_PROPONENTE),
        "programa_proponentes": siconv.registros(dirigidos),
        "programa": siconv.registros(programas),
        "proposta_selecao_pac": siconv.registros(selecao_pac.drop(columns=COLUNAS_IGNORADAS["proposta_selecao_pac"], errors="ignore")),
    }
    return RetratoBruto(
        fonte=FONTE,
        data=data,
        coletado_em=agora(config),
        metadados={
            "data_carga": data_carga,
            "arquivos": {nome: zips[nome].stat().st_size for nome in ARQUIVOS},
            "colunas_ignoradas": COLUNAS_IGNORADAS,
            "filtro_programa": f"natureza jurídica municipal, UF {municipio.uf} ou sem UF, e (dirigido à prefeitura ou DISPONIBILIZADO com janela não encerrada em {data.isoformat()})",
            "id_proponente_prefeitura": sorted(ids_proponente),
        },
        dados=dados,
    )
