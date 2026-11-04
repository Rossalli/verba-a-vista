"""T5.3: amostra para a revisão de credibilidade."""

import csv
import json

import pytest

from nucleo import amostra as a
from nucleo.config import carregar_config
from tests.conftest import RAIZ


def verba(id_, fonte="transferegov_discricionarias", status="aprovada", risco=None, status_fonte="Assinado", **kw):
    base = {
        "id": id_, "fonte": fonte, "id_fonte": id_.split("-")[-1], "nome": f"Verba {id_}", "tipo": "voluntaria", "valor_total": 1234567, "status_site": status,
        "status_fonte": status_fonte, "em_risco": bool(risco), "motivos_risco": [{"codigo": c, "texto": f"alerta {c}"} for c in (risco or [])], "prazos": {},
        "fontes": [{"nome": "Transferegov", "url": "https://exemplo.gov.br", "data_coleta": "2026-10-29T18:00:00-03:00"}],
    }
    return {**base, **kw}


def universo():
    vs = [verba(f"transferegov_discricionarias-p{i}", status="perdida", status_fonte="Rejeitados" if i % 2 else "Rejeitados por Impedimento",
                perda={"categoria": "em_apuracao", "valor_perdido": 100000 + i, "data": "2025-01-21"}) for i in range(6)]
    vs += [verba(f"transferegov_discricionarias-c{i}", status="proposta", risco=["cauc_sem_comprovacao"]) for i in range(4)]
    vs += [verba(f"transferegov_discricionarias-z{i}", status="execucao", risco=["prazo_proximo"]) for i in range(2)]
    vs += [verba(f"transferegov_discricionarias-s{i}", status="proposta") for i in range(3)]
    vs += [verba(f"transferegov_discricionarias-a{i}", status="aprovada") for i in range(4)]
    vs += [verba(f"transferegov_parcerias-{i}", fonte="transferegov_parcerias", tipo="emenda_finalidade") for i in range(3)]
    vs += [verba(f"transferegov_fundoafundo-{i}", fonte="transferegov_fundoafundo", tipo="fundo_a_fundo") for i in range(2)]
    vs += [verba(f"siconv_programa-{i}", fonte="siconv_programa", tipo="programa_adesao", status="oportunidade", valor_total=None) for i in range(3)]
    return vs


def test_amostra_tem_12_verbas_distintas_cobrindo_os_grupos():
    amostra = a.montar_amostra(universo())
    ids = [v["id"] for _, v in amostra]
    assert len(amostra) == 12 and len(set(ids)) == 12
    contagem = {}
    for grupo, _ in amostra:
        contagem[grupo] = contagem.get(grupo, 0) + 1
    assert contagem == {nome: quantas for nome, _, quantas in a.GRUPOS}
    assert sum(quantas for *_, quantas in a.GRUPOS) == 12 >= 10  # a spec §12 exige pelo menos 10


def test_amostra_e_deterministica_e_nao_depende_da_ordem_de_entrada():
    vs = universo()
    primeira = [v["id"] for _, v in a.montar_amostra(vs)]
    assert primeira == [v["id"] for _, v in a.montar_amostra(list(reversed(vs)))]
    assert primeira != [v["id"] for _, v in a.montar_amostra(vs, semente="outra")]  # a semente muda a escolha


def test_perdas_alternam_entre_as_situacoes_da_fonte():
    perdas = [v for g, v in a.montar_amostra(universo()) if g.startswith("Perda")]
    assert {v["status_fonte"] for v in perdas} == {"Rejeitados", "Rejeitados por Impedimento"}


def test_grupo_sem_verba_suficiente_e_completado_com_sobras():
    vs = [v for v in universo() if v["fonte"] != "transferegov_fundoafundo"]
    amostra = a.montar_amostra(vs)
    assert len(amostra) == 12 and sum(1 for g, _ in amostra if g.startswith("Complemento")) == 1


def test_poucas_verbas_no_total_nao_quebra():
    amostra = a.montar_amostra(universo()[:5])
    assert len(amostra) == 5 and len({v["id"] for _, v in amostra}) == 5


def test_planilha_tem_dados_do_site_e_colunas_de_resposta_em_branco(tmp_path):
    amostra = a.montar_amostra(universo())
    destino = tmp_path / "amostra.csv"
    a.gravar_csv(amostra, destino, carregar_config().taxonomia)
    bruto = destino.read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf") and b"\r\n" in bruto  # BOM e CRLF, como o CSV publicado
    with destino.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    assert linhas[0] == a.COLUNAS_FIXAS + a.COLUNAS_RESPOSTA and len(linhas) == 13
    assert all(len(l) == len(linhas[0]) for l in linhas)
    perda = next(dict(zip(linhas[0], l)) for l in linhas[1:] if l[1].startswith("Perda"))
    assert perda["situação no site"] == "Perdida" and perda["perda: motivo"] == "Em apuração" and perda["perda em"] == "21/01/2025" and perda["valor total (R$)"] == "12345,67"
    risco = next(dict(zip(linhas[0], l)) for l in linhas[1:] if l[1].startswith("Em risco: alerta"))
    assert risco["alerta de risco"] == "alerta cauc_sem_comprovacao" and risco["página no site"].startswith("/verbas/")
    assert all(not any(l[len(a.COLUNAS_FIXAS):]) for l in linhas[1:])  # colunas de resposta vazias
    oportunidade = next(dict(zip(linhas[0], l)) for l in linhas[1:] if l[1].startswith("Oportunidade"))
    assert oportunidade["valor total (R$)"] == ""  # valor nulo não vira 0


def test_planilha_protege_texto_contra_formula_do_excel(tmp_path):
    perigosa = verba("transferegov_discricionarias-x", nome="=HYPERLINK(\"http://x\")")
    destino = tmp_path / "a.csv"
    a.gravar_csv([("g", perigosa)], destino, carregar_config().taxonomia)
    assert "'=HYPERLINK" in destino.read_text(encoding="utf-8-sig")


def test_dados_reais_geram_uma_amostra_de_pelo_menos_10(tmp_path, capsys):
    destino = tmp_path / "amostra.csv"
    assert a.main(["--raiz", str(RAIZ), "--saida", str(destino)]) == 0
    publicado = json.loads((RAIZ / "dados" / "publicados" / "verbas.json").read_text(encoding="utf-8"))
    with destino.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    ids = [l[2] for l in linhas[1:]]
    assert len(ids) >= 10 and len(set(ids)) == len(ids) and set(ids) <= {v["id"] for v in publicado["verbas"]}
    assert "verbas de" in capsys.readouterr().out
