import csv
import io
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from nucleo import pipeline
from nucleo import publica as p
from nucleo.config import carregar_config
from nucleo.modelo import Verba
from nucleo.normaliza import carregar_retratos

RAIZ = Path(__file__).resolve().parents[1]
DATA = date(2026, 10, 30)
FONTE = {"nome": "Transferegov", "url": "https://exemplo.gov.br", "data_coleta": "2026-10-29T18:00:00-03:00"}


@pytest.fixture
def config():
    return carregar_config()


@pytest.fixture(scope="module")
def reais():
    return carregar_retratos(RAIZ, DATA)


@pytest.fixture(scope="module")
def processamento(raiz_sem_publicado):
    return pipeline.processar(raiz_sem_publicado, DATA)


def verba(id_="transferegov_discricionarias-1", **kw) -> Verba:
    base = {
        "id": id_, "fonte": "transferegov_discricionarias", "id_fonte": id_.split("-")[1], "nome": "Obra", "tipo": "voluntaria", "valor_total": 100_00,
        "status_site": "aprovada", "status_fonte": "Assinado", "em_risco": False, "historico": [], "fontes": [FONTE],
    }
    return Verba.model_validate({**base, **kw})


def ler_csv(caminho: Path) -> list[dict]:
    texto = caminho.read_bytes().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto, newline=""), delimiter=";"))


# --- fontes e referências ----------------------------------------------------------------------


def test_fontes_dizem_o_retrato_a_hora_e_a_data_do_dado(reais, config):
    f = p.montar_fontes(reais, config, DATA)
    assert list(f) == list(p.NOMES_FONTES)
    siconv = f["transferegov_discricionarias"]
    assert (siconv["retrato"], siconv["data_do_dado"], siconv["situacao"]) == ("2026-10-29", "2026-07-17", "defasada")  # a carga do Siconv é de julho
    assert f["cauc"]["data_do_dado"] == "2026-10-29" and f["obrasgov"]["data_do_dado"] == "2026-10-29" and f["transferegov_api"]["data_do_dado"] == "2026-10-29"
    assert f["portal_transparencia"]["data_do_dado"] is None and f["tesouro_constitucionais"]["data_do_dado"] is None
    assert all(x["coletado_em"].startswith("2026-10-29T") and x["nome"] and x["url"] for x in f.values())


def test_situacao_da_fonte_ok_defasada_ou_sem_retrato(reais, config):
    hoje = p.montar_fontes(reais, config, date(2026, 10, 29))
    assert {x["situacao"] for x in hoje.values()} == {"ok"}
    sem = {**reais, "cauc": None}
    f = p.montar_fontes(sem, config, DATA)
    assert f["cauc"] == {"nome": p.NOMES_FONTES["cauc"], "url": f["cauc"]["url"], "retrato": None, "coletado_em": None, "data_do_dado": None, "situacao": "sem_retrato"}
    assert f["obrasgov"]["situacao"] == "defasada"


def test_referencias_do_tesouro_em_centavos_com_o_aviso_do_ultimo_mes(reais):
    r = p.montar_referencias(reais["tesouro_constitucionais"])["transferencias_constitucionais"]
    por = {(x["ano"], x["transferencia"]): x for x in r["por_ano"]}
    assert por[(2024, "FPM")] == {"ano": 2024, "transferencia": "FPM", "valor": 1_431_757_469, "meses": 12}  # R$ 14.317.574,69
    assert por[(2026, "ITR")] == {"ano": 2026, "transferencia": "ITR", "valor": 34_911_983, "meses": 10}  # jan a out
    assert len(r["por_ano"]) == 6 and r["ultimo_mes"] == {"mes": "2026-10", "terceiro_decendio_zerado": True}
    assert p.montar_referencias(None) == {"transferencias_constitucionais": None}


def test_atualizado_em_e_a_coleta_mais_recente(reais, config):
    corpo = p.montar_publicado([], reais, config, DATA)
    assert corpo["atualizado_em"] == max((r["coletado_em"] for r in reais.values()), key=datetime.fromisoformat)
    assert corpo["data"] == "2026-10-30" and corpo["versao"] == 1
    assert p.montar_publicado([], {f: None for f in reais}, config, DATA)["atualizado_em"] is None


# --- verbas.json -------------------------------------------------------------------------------


def test_publicar_dados_reais_grava_json_valido_com_as_46_verbas(processamento, tmp_path):
    res = p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path)
    assert res.verbas == 46 and res.json == tmp_path / "dados" / "publicados" / "verbas.json" and res.csv.name == "verbas.csv"
    corpo = json.loads(res.json.read_text(encoding="utf-8"))
    p.validar_publicado(corpo)
    ids = [v["id"] for v in corpo["verbas"]]
    assert len(ids) == 46 and ids == sorted(ids)
    assert "gerado_em" not in corpo and set(corpo) == {"versao", "data", "atualizado_em", "fontes", "referencias", "verbas"}
    assert not list((tmp_path / "dados" / "publicados").glob("*.tmp"))


def test_json_usa_so_lf_acentos_sem_escape_e_termina_em_nova_linha(processamento, tmp_path):
    res = p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path)
    bruto = res.json.read_bytes()
    assert b"\r" not in bruto and bruto.endswith(b"\n") and not bruto.startswith(b"\xef\xbb\xbf")
    assert "Prestação de contas".encode() not in bruto and "Em execução".encode() in bruto and b"\\u00" not in bruto


def test_publicar_duas_vezes_gera_arquivos_identicos(processamento, tmp_path):
    a = p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path)
    json1, csv1 = a.json.read_bytes(), a.csv.read_bytes()
    p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path)
    assert a.json.read_bytes() == json1 and a.csv.read_bytes() == csv1  # sem hora de geração: nenhum diff no Git


def test_schema_do_publicado_e_um_json_schema_valido():
    Draft202012Validator.check_schema(json.loads((RAIZ / "schemas" / "publicado.schema.json").read_text(encoding="utf-8")))


# --- verbas.csv --------------------------------------------------------------------------------


def test_csv_comeca_com_bom_e_decodifica_em_utf8_com_acentos(processamento, tmp_path):
    res = p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path)
    bruto = res.csv.read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")  # o BOM faz o Excel abrir em UTF-8
    texto = bruto.decode("utf-8-sig")
    assert "Prestação de contas" in texto and "Em execução" in texto and "Regularidade Previdenciária" in texto
    assert "SÃO PAULO" in texto  # Ã é letra do português; mojibake seria Ã seguido de símbolo (Ã§ no lugar de ç)
    assert not re.search(r"Ã[^\x00-\x7f]", texto) and "�" not in texto  # sem mojibake nem caractere de substituição
    assert texto.count("\r\n") == 47 and "\r\n" not in texto.replace("\r\n", "")  # cabeçalho + 46 linhas, fim de linha do Excel


def test_csv_tem_uma_linha_por_verba_e_o_cabecalho_combinado(processamento, tmp_path):
    res = p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path)
    linhas = ler_csv(res.csv)
    assert list(linhas[0]) == p.CABECALHO_CSV and len(linhas) == 46
    assert [l["id"] for l in linhas] == [v.id for v in processamento.normalizacao.verbas]
    assert all(len(l) == len(p.CABECALHO_CSV) and None not in l.values() for l in linhas)


def test_csv_valores_em_reais_com_virgula_e_datas_em_iso(processamento, tmp_path):
    linhas = {l["id"]: l for l in ler_csv(p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path).csv)}
    v = linhas["transferegov_discricionarias-2031354"]
    assert (v["valor_total_reais"], v["contrapartida_reais"], v["liberado_reais"]) == ("3411250,00", "161250,00", "938758,79")
    assert (v["prazo_assinatura"], v["prazo_fim_vigencia"], v["prazo_clausula_suspensiva"]) == ("2024-12-13", "2028-09-13", "")
    assert (v["situacao"], v["tipo"], v["instrumento"], v["em_risco"]) == ("Em execução", "Convênio, contrato de repasse ou termo de compromisso", "TERMO DE COMPROMISSO", "não")
    assert v["fontes"].count("; ") == 2 and v["ultima_coleta"].startswith("2026-10-29T")
    assert linhas["transferegov_discricionarias-1733967"]["execucao_fisica_pct"] == ""  # sem medição: vazio, não 0


def test_csv_perda_alerta_e_oportunidade(processamento, tmp_path):
    linhas = {l["id"]: l for l in ler_csv(p.publicar(processamento.normalizacao.verbas, processamento.retratos, processamento.config, DATA, tmp_path).csv)}
    perdida = linhas["transferegov_discricionarias-2113259"]
    assert (perdida["situacao"], perdida["perda_categoria"], perdida["perda_valor_reais"], perdida["perda_data"], perdida["perda_gerada_por_ia"]) == ("Perdida", "Motivo em apuração", "549500,00", "2026-03-05", "não")
    assert perdida["perda_texto"].startswith("Motivo em apuração.") and perdida["perda_evitavel"] == "indeterminado" and perdida["perda_revisada_por"] == ""
    risco = linhas["transferegov_discricionarias-2227146"]
    assert (risco["em_risco"], risco["alertas"]) == ("sim", "CAUC: item 4.2 sem comprovação (Regularidade Previdenciária)")
    prazo = linhas["transferegov_discricionarias-1733967"]
    assert prazo["alertas"] == "Prazo em 51 dias"
    oportunidade = next(l for l in linhas.values() if l["situacao"] == "Oportunidade")
    assert oportunidade["valor_total_reais"] == "" and oportunidade["prazo_adesao"] == "2026-12-31" and oportunidade["tipo"] == "Programa por adesão ou seleção"


def test_csv_verba_sem_status_mapeado_usa_o_rotulo_do_selo(config, tmp_path):
    v = verba(status_site=None, status_fonte="Situação nova")
    p.publicar([v], {}, config, DATA, tmp_path)
    (linha,) = ler_csv(tmp_path / p.ARQUIVO_CSV)
    assert (linha["situacao"], linha["situacao_na_fonte"]) == ("Situação em análise", "Situação nova")


def test_csv_texto_com_ponto_e_virgula_aspas_e_quebra_de_linha_volta_inteiro(config, tmp_path):
    objeto = 'Obra "A"; fase 1;\nfase 2, com vírgula'
    p.publicar([verba(objeto=objeto, nome="Obra; A")], {}, config, DATA, tmp_path)
    (linha,) = ler_csv(tmp_path / p.ARQUIVO_CSV)
    assert linha["objeto"] == objeto and linha["nome"] == "Obra; A"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("=SOMA(A1:A9)", "'=SOMA(A1:A9)"), ("+1", "'+1"), ("-1", "'-1"), ("@usuario", "'@usuario"), ("\tx", "'\tx"), ("normal", "normal"), ("a=b", "a=b"), ("", ""), (None, "")],
)
def test_texto_seguro_contra_formula_do_excel(texto, esperado):
    assert p.texto_seguro(texto) == esperado


def test_csv_protege_a_celula_que_a_fonte_comecou_com_formula(config, tmp_path):
    p.publicar([verba(nome='=HYPERLINK("http://x","clique")', objeto="@alvo")], {}, config, DATA, tmp_path)
    (linha,) = ler_csv(tmp_path / p.ARQUIVO_CSV)
    assert linha["nome"].startswith("'=") and linha["objeto"] == "'@alvo"


@pytest.mark.parametrize(("centavos", "esperado"), [(0, "0,00"), (5, "0,05"), (123456, "1234,56"), (100_000_000, "1000000,00"), (-717410, "-7174,10"), (None, "")])
def test_reais_csv(centavos, esperado):
    assert p.reais_csv(centavos) == esperado


# --- falhas não gravam nada --------------------------------------------------------------------


def grava_sentinelas(raiz: Path) -> tuple[Path, Path]:
    pasta = raiz / "dados" / "publicados"
    pasta.mkdir(parents=True)
    (pasta / "verbas.json").write_text('{"antigo": true}', encoding="utf-8")
    (pasta / "verbas.csv").write_bytes(b"antigo")
    return pasta / "verbas.json", pasta / "verbas.csv"


def test_verba_invalida_no_schema_nao_grava_nada_e_preserva_o_publicado(config, tmp_path):
    json_antigo, csv_antigo = grava_sentinelas(tmp_path)
    v = verba()
    v.tipo = "inventado"  # a atribuição não revalida; o schema pega antes de gravar
    with pytest.raises(ValueError, match="publicado inválido"):
        p.publicar([v], {}, config, DATA, tmp_path)
    assert json_antigo.read_text(encoding="utf-8") == '{"antigo": true}' and csv_antigo.read_bytes() == b"antigo"
    assert not list(json_antigo.parent.glob("*.tmp"))


def test_ids_repetidos_nao_gravam(config, tmp_path):
    with pytest.raises(ValueError, match="ids de verba repetidos"):
        p.publicar([verba(), verba()], {}, config, DATA, tmp_path)
    assert not (tmp_path / "dados").exists()


def test_falha_ao_montar_o_csv_nao_troca_nem_o_json(config, tmp_path, monkeypatch):
    json_antigo, csv_antigo = grava_sentinelas(tmp_path)

    def quebra(*a, **k):
        raise RuntimeError("falha no CSV")

    monkeypatch.setattr(p, "linha_csv", quebra)
    with pytest.raises(RuntimeError, match="falha no CSV"):
        p.publicar([verba()], {}, config, DATA, tmp_path)
    assert json_antigo.read_text(encoding="utf-8") == '{"antigo": true}' and csv_antigo.read_bytes() == b"antigo"
    assert not list(json_antigo.parent.glob("*.tmp"))


# --- pipeline de ponta a ponta -----------------------------------------------------------------


@pytest.fixture
def raiz_com_brutos(tmp_path):
    shutil.copytree(RAIZ / "dados" / "brutos", tmp_path / "dados" / "brutos")
    return tmp_path


def test_pipeline_publica_e_a_segunda_execucao_le_o_publicado_sem_mudar_nada(raiz_com_brutos, capsys):
    assert pipeline.main(["--data", "2026-10-30", "--raiz", str(raiz_com_brutos)]) == 0
    saida = capsys.readouterr().out
    assert "Histórico: primeira execução" in saida and "Publicado: 46 verbas em" in saida
    pasta = raiz_com_brutos / "dados" / "publicados"
    primeiro_json, primeiro_csv = (pasta / "verbas.json").read_bytes(), (pasta / "verbas.csv").read_bytes()
    assert pipeline.main(["--data", "2026-10-30", "--raiz", str(raiz_com_brutos)]) == 0
    saida2 = capsys.readouterr().out
    assert "comparado com o publicado anterior; novas=0, com mudança=0, desaparecidas=0" in saida2 and "Perdas novas: 0" in saida2
    assert (pasta / "verbas.json").read_bytes() == primeiro_json and (pasta / "verbas.csv").read_bytes() == primeiro_csv


def test_pipeline_no_dia_seguinte_mantem_as_verbas_e_marca_as_fontes_como_defasadas(raiz_com_brutos, capsys):
    pipeline.main(["--data", "2026-10-30", "--raiz", str(raiz_com_brutos)])
    antes = json.loads((raiz_com_brutos / "dados" / "publicados" / "verbas.json").read_text(encoding="utf-8"))
    pipeline.main(["--data", "2026-10-31", "--raiz", str(raiz_com_brutos)])
    depois = json.loads((raiz_com_brutos / "dados" / "publicados" / "verbas.json").read_text(encoding="utf-8"))

    def sem_alertas(corpo):
        return [{k: v for k, v in x.items() if k != "motivos_risco"} for x in corpo["verbas"]]

    assert sem_alertas(antes) == sem_alertas(depois)  # nada mudou nas fontes: histórico e perdas intactos
    prazo = lambda corpo: next(v["motivos_risco"][0]["texto"] for v in corpo["verbas"] if v["id"] == "transferegov_discricionarias-1733967")  # noqa: E731
    assert (prazo(antes), prazo(depois)) == ("Prazo em 51 dias", "Prazo em 50 dias")  # o único que muda é a contagem do prazo
    assert (antes["data"], depois["data"]) == ("2026-10-30", "2026-10-31") and {f["situacao"] for f in depois["fontes"].values()} == {"defasada"}


def test_pipeline_sem_publicar_nao_grava(raiz_com_brutos, capsys):
    assert pipeline.main(["--data", "2026-10-30", "--raiz", str(raiz_com_brutos), "--sem-publicar"]) == 0
    assert "Publicação: pulada" in capsys.readouterr().out and not (raiz_com_brutos / "dados" / "publicados").exists()


def test_gitattributes_fixa_os_bytes_dos_dados_publicados():
    texto = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert "dados/publicados/verbas.csv -text" in texto and "dados/publicados/verbas.json text eol=lf" in texto
