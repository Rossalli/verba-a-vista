import io
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from coleta import transferegov_discricionarias as d
from coleta.base import ColetaErro, Http
from nucleo.config import carregar_config

RAIZ = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DISC = RAIZ / "transferegov_discricionarias"
OPOR = RAIZ / "oportunidades"
DIA = date(2026, 10, 29)
OUTRO_IBGE = "3550308"


def ler(pasta, nome):
    return pd.read_csv(pasta / nome, sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)


def com(df, **colunas):
    """Primeira linha de `df` copiada com colunas trocadas (uma linha de 'outro município')."""
    linha = df.iloc[[0]].copy()
    for c, v in colunas.items():
        linha[c] = v
    return linha


def zip_csv(df):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("tabela.csv", ("﻿" + df.to_csv(sep=";", index=False)).encode("utf-8"))
    return buffer.getvalue()


@pytest.fixture
def config():
    return carregar_config()


def http_falso():
    return Http(tentativas=1, backoff_inicial_s=0, dormir=lambda _s: None)


def tabelas():
    """As tabelas do Siconv como estariam no servidor: linhas do município (amostras reais) + linhas de outros."""
    proposta, cancelada = ler(DISC, "proposta.csv"), ler(DISC, "proposta_cancelada.csv")
    convenio, emenda = ler(DISC, "convenio.csv"), ler(DISC, "emenda.csv")
    historico, desembolso, prorroga = ler(DISC, "historico_situacao.csv"), ler(DISC, "desembolso.csv"), ler(DISC, "prorroga_oficio.csv")
    dirigidos, pac = ler(OPOR, "siconv_programa_proponentes_municipio.csv"), ler(OPOR, "siconv_selecao_pac_municipio.csv")
    elegiveis = ler(OPOR, "siconv_programas_elegiveis_abertos.csv")
    id_dirigido = dirigidos["ID_PROGRAMA"].iloc[0]
    modelo = elegiveis.iloc[[0]]
    extras_programa = pd.concat(
        [
            com(modelo, ID_PROGRAMA="9001", UF_PROGRAMA="MG"),  # outra UF
            com(modelo, ID_PROGRAMA="9002", NATUREZA_JURIDICA_PROGRAMA="Administração Pública Estadual ou do Distrito Federal"),
            com(modelo, ID_PROGRAMA="9003", DT_PROG_FIM_RECEB_PROP="01/01/2020"),  # janela encerrada e não dirigido
            com(modelo, ID_PROGRAMA=id_dirigido, SIT_PROGRAMA="INATIVO", DT_PROG_FIM_RECEB_PROP="01/01/2020"),  # dirigido: entra mesmo encerrado
        ]
    )
    pac_com_texto = pd.concat([pac.assign(JUSTIFICATIVA_PROPOSTA_SELECAO_PAC="texto longo e livre"), com(pac, ID_PROPONENTE="777").assign(JUSTIFICATIVA_PROPOSTA_SELECAO_PAC="x")])
    proponentes = pd.DataFrame(
        [
            {"ID_PROPONENTE": "15310", "IDENTIF_PROPONENTE": "45145414000147", "NM_PROPONENTE": "MUNICIPIO DE NEVES PAULISTA", "EMAIL_PROPONENTE": "contato@exemplo.gov.br", "TELEFONE_PROPONENTE": "1799999999"},
            {"ID_PROPONENTE": "777", "IDENTIF_PROPONENTE": "11111111000111", "NM_PROPONENTE": "OUTRO", "EMAIL_PROPONENTE": "o@x", "TELEFONE_PROPONENTE": "1"},
        ]
    )
    return {
        "proposta": pd.concat([proposta, com(proposta, COD_MUNIC_IBGE=OUTRO_IBGE, ID_PROPOSTA="999990")]),
        "proposta_cancelada": pd.concat([cancelada, com(cancelada, COD_MUNIC_IBGE=OUTRO_IBGE, ID_PROPOSTA="999989")]),
        "convenio": pd.concat([convenio, com(convenio, ID_PROPOSTA="999990", NR_CONVENIO="999991")]),
        "emenda": pd.concat([emenda, com(emenda, ID_PROPOSTA="999990")]),
        "historico_situacao": pd.concat([historico, com(historico, ID_PROPOSTA="999990", NR_CONVENIO="999991")]),
        "desembolso": pd.concat([desembolso, com(desembolso, NR_CONVENIO="999991")]),
        "prorroga_oficio": pd.concat([prorroga, com(prorroga, NR_CONVENIO="999991")]),
        "programa": pd.concat([elegiveis, extras_programa]),
        "programa_proponentes": pd.concat([dirigidos, com(dirigidos, ID_PROPONENTE="777")]),
        "proposta_selecao_pac": pac_com_texto,
        "proponentes": proponentes,
    }


def mockar(config, mudancas=None, carga="﻿17/07/2026 06:30:47\n"):
    base = config.fontes.fontes["transferegov_discricionarias"].url
    dados = {**tabelas(), **(mudancas or {})}
    rotas = {}
    for nome, df in dados.items():
        url = f"{base}/siconv_{nome}.csv.zip"
        conteudo = zip_csv(df)
        respx.head(url).mock(return_value=httpx.Response(200, headers={"content-length": str(len(conteudo))}))
        rotas[nome] = respx.get(url).mock(return_value=httpx.Response(200, content=conteudo))
    respx.get(f"{base}/data_carga_siconv.txt").mock(return_value=httpx.Response(200, content=carga.encode("utf-8")))
    return rotas


@respx.mock
def test_filtra_cada_tabela_pelo_municipio_e_descarta_as_linhas_de_outros(config, tmp_path):
    mockar(config)
    retrato = d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)
    dados = retrato.dados
    assert retrato.fonte == "transferegov_discricionarias"
    assert {r["COD_MUNIC_IBGE"] for r in dados["proposta"]} == {"3532504"} and len(dados["proposta"]) == len(ler(DISC, "proposta.csv"))
    assert {r["COD_MUNIC_IBGE"] for r in dados["proposta_cancelada"]} == {"3532504"} and len(dados["proposta_cancelada"]) == 7
    ids = {r["ID_PROPOSTA"] for r in [*dados["proposta"], *dados["proposta_cancelada"]]}
    assert len(dados["convenio"]) == 28 and {r["ID_PROPOSTA"] for r in dados["convenio"]} <= ids
    numeros = {r["NR_CONVENIO"] for r in dados["convenio"]}
    assert "999991" not in numeros
    esperado_emenda = ler(DISC, "emenda.csv")["ID_PROPOSTA"].isin(ids).sum()
    assert len(dados["emenda"]) == esperado_emenda > 0
    assert {r["ID_PROPOSTA"] for r in dados["historico_situacao"]} <= ids and len(dados["historico_situacao"]) > 0
    assert {r["NR_CONVENIO"] for r in dados["desembolso"]} <= numeros and len(dados["desembolso"]) == 30
    assert {r["NR_CONVENIO"] for r in dados["prorroga_oficio"]} <= numeros and len(dados["prorroga_oficio"]) == 22


@respx.mock
def test_valores_continuam_texto_sem_conversao(config, tmp_path):
    mockar(config)
    retrato = d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)
    convenio = retrato.dados["convenio"][0]
    assert isinstance(convenio["VL_GLOBAL_CONV"], str) and all(isinstance(v, str) for v in convenio.values())
    assert any("," in r["VL_GLOBAL_CONV"] for r in retrato.dados["convenio"])  # vírgula decimal preservada
    assert any(v == "" for r in retrato.dados["convenio"] for v in r.values())  # vazio é texto vazio, não NaN


@respx.mock
def test_proponente_so_com_id_cnpj_e_nome_sem_contatos(config, tmp_path):
    mockar(config)
    retrato = d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)
    assert retrato.dados["proponente"] == [{"ID_PROPONENTE": "15310", "IDENTIF_PROPONENTE": "45145414000147", "NM_PROPONENTE": "MUNICIPIO DE NEVES PAULISTA"}]
    texto = str(retrato.dados)
    assert "contato@exemplo.gov.br" not in texto and "1799999999" not in texto
    assert retrato.metadados["id_proponente_prefeitura"] == ["15310"]


@respx.mock
def test_programas_so_municipais_da_uf_e_dirigidos_ou_disponibilizados_com_janela_aberta(config, tmp_path):
    mockar(config)
    programas = d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path).dados["programa"]
    ids = {p["ID_PROGRAMA"] for p in programas}
    assert not ids & {"9001", "9002", "9003"}  # outra UF, estadual, encerrado e não dirigido
    id_dirigido = ler(OPOR, "siconv_programa_proponentes_municipio.csv")["ID_PROGRAMA"].iloc[0]
    assert id_dirigido in ids  # dirigido à prefeitura entra mesmo com a janela encerrada
    assert all("Municipal" in p["NATUREZA_JURIDICA_PROGRAMA"] and p["UF_PROGRAMA"] in ("SP", "") for p in programas)
    # dos 9 elegíveis da amostra, só os DISPONIBILIZADO (7) entram, mais o dirigido
    assert len(programas) == 7 + 1


@respx.mock
def test_novo_pac_do_municipio_sem_o_texto_livre_da_justificativa(config, tmp_path):
    mockar(config)
    retrato = d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)
    pac = retrato.dados["proposta_selecao_pac"]
    assert len(pac) == 10 and {p["ID_PROPONENTE"] for p in pac} == {"15310"}
    assert all("JUSTIFICATIVA_PROPOSTA_SELECAO_PAC" not in p for p in pac)
    assert retrato.metadados["colunas_ignoradas"] == {"proposta_selecao_pac": ["JUSTIFICATIVA_PROPOSTA_SELECAO_PAC"]}
    assert len(retrato.dados["programa_proponentes"]) == len(ler(OPOR, "siconv_programa_proponentes_municipio.csv"))


@respx.mock
def test_metadados_trazem_a_data_da_carga_e_o_filtro_usado(config, tmp_path):
    mockar(config)
    meta = d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path).metadados
    assert meta["data_carga"] == "17/07/2026 06:30:47"  # sem o BOM do arquivo
    assert set(meta["arquivos"]) == set(d.ARQUIVOS) and all(v > 0 for v in meta["arquivos"].values())
    assert "2026-10-29" in meta["filtro_programa"] and "SP" in meta["filtro_programa"]


@respx.mock
def test_zips_ficam_no_cache_e_nao_sao_baixados_de_novo(config, tmp_path):
    rotas = mockar(config)
    d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)
    assert {p.name for p in tmp_path.glob("*.zip")} == {f"siconv_{n}.csv.zip" for n in d.ARQUIVOS}
    d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)
    assert all(r.call_count == 1 for r in rotas.values())  # o tamanho no servidor não mudou: cache


@respx.mock
def test_sem_nenhuma_proposta_do_municipio_e_erro(config, tmp_path):
    vazia = ler(DISC, "proposta.csv").iloc[0:0]
    mockar(config, {"proposta": vazia, "proposta_cancelada": ler(DISC, "proposta_cancelada.csv").iloc[0:0]})
    with pytest.raises(ColetaErro, match="nenhuma proposta para o IBGE 3532504"):
        d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)


@respx.mock
def test_prefeitura_ausente_dos_proponentes_e_erro(config, tmp_path):
    mockar(config, {"proponentes": pd.DataFrame([{"ID_PROPONENTE": "777", "IDENTIF_PROPONENTE": "11111111000111", "NM_PROPONENTE": "OUTRO"}])})
    with pytest.raises(ColetaErro, match="esperava 1 proponente com o CNPJ 45145414000147, achei 0"):
        d.coletar(DIA, config=config, http=http_falso(), cache=tmp_path)


def programas(linhas):
    colunas = ["ID_PROGRAMA", "SIT_PROGRAMA", "NATUREZA_JURIDICA_PROGRAMA", "UF_PROGRAMA", "DT_PROG_FIM_RECEB_PROP", "DT_PROG_FIM_EMENDA_PAR", "DT_PROG_FIM_BENEF_ESP"]
    return pd.DataFrame(linhas, columns=colunas)


M = "Administração Pública Municipal"


def test_programas_relevantes_regras():
    df = programas(
        [
            ["1", "DISPONIBILIZADO", M, "SP", "31/12/2026", "", ""],  # entra: aberta
            ["2", "DISPONIBILIZADO", M, "", "", "", "29/10/2026"],  # entra: sem UF, janela termina hoje (conta)
            ["3", "DISPONIBILIZADO", M, "SP", "28/10/2026", "", ""],  # encerrada ontem
            ["4", "CADASTRADO", M, "SP", "31/12/2026", "", ""],  # não disponibilizado
            ["5", "DISPONIBILIZADO", M, "MG", "31/12/2026", "", ""],  # outra UF
            ["6", "DISPONIBILIZADO", "Consórcio Público", "SP", "31/12/2026", "", ""],  # não municipal
            ["7", "INATIVO", M, "SP", "01/01/2020", "", ""],  # só entra se dirigido
            ["8", "DISPONIBILIZADO", M, "SP", "", "", ""],  # sem nenhuma data de fim
        ]
    )
    assert list(d.programas_relevantes(df, set(), "SP", DIA)) == [True, True, False, False, False, False, False, False]
    assert list(d.programas_relevantes(df, {"7"}, "SP", DIA)) == [True, True, False, False, False, False, True, False]
