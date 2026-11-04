"""Amostra para a revisão de credibilidade (spec §12, T5.3).

    python -m nucleo.amostra            # grava docs/revisao-credibilidade/amostra.csv

Escolhe 12 verbas do publicado cobrindo o que mais precisa de conferência (perdas, alertas de risco, cada tipo de
fonte) e grava uma planilha com os dados do site, as chaves para achar a verba no Transferegov e colunas em branco
para quem revisa responder. A escolha é determinística (mesmos dados, mesma amostra), sem sorteio.
"""

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path

from nucleo.config import carregar_config
from nucleo.normaliza import RAIZ
from nucleo.publica import texto_seguro

EM_ANDAMENTO = ("aprovada", "execucao", "prestacao")

# (nome do grupo, quem entra, quantas) — a soma é 12 (a spec exige pelo menos 10).
GRUPOS: list[tuple[str, Callable[[dict], bool], int]] = [
    ("Perda (motivo em apuração ou revisado)", lambda v: v["status_site"] == "perdida", 3),
    ("Em risco: alerta de CAUC", lambda v: v["em_risco"] and any(m["codigo"] == "cauc_sem_comprovacao" for m in v["motivos_risco"]), 2),
    ("Em risco: prazo ou obra parada", lambda v: v["em_risco"] and any(m["codigo"] in ("prazo_proximo", "obra_parada") for m in v["motivos_risco"]), 1),
    ("Proposta sem alerta", lambda v: v["status_site"] == "proposta" and not v["em_risco"], 1),
    ("Em andamento sem alerta (convênio ou contrato de repasse)", lambda v: v["fonte"] == "transferegov_discricionarias" and v["status_site"] in EM_ANDAMENTO and not v["em_risco"], 2),
    ("Parceria (emenda com finalidade)", lambda v: v["fonte"] == "transferegov_parcerias", 1),
    ("Fundo a fundo", lambda v: v["fonte"] == "transferegov_fundoafundo", 1),
    ("Oportunidade (programa por adesão)", lambda v: v["status_site"] == "oportunidade", 1),
]

COLUNAS_FIXAS = [
    "nº", "por que está na amostra", "id", "nome", "tipo", "instrumento", "órgão concedente", "nº do instrumento", "id na fonte",
    "valor total (R$)", "valor liberado (R$)", "situação no site", "situação na fonte", "alerta de risco",
    "perda: motivo", "perda: valor (R$)", "perda em", "data da proposta", "assinatura", "fim da vigência", "prestação de contas até",
    "fonte", "página no site",
]
COLUNAS_RESPOSTA = [
    "A situação do site está correta? (sim / não / não sei)",
    "O valor confere com o Transferegov? (sim / não / não sei)",
    "O alerta de risco faz sentido? (sim / não / não se aplica)",
    "O motivo da perda confere? (sim / não / não se aplica)",
    "Observações (o que está errado, ou faltando, e como você sabe)",
]


def _ordem(semente: str, verba_id: str) -> str:
    return hashlib.sha1(f"{semente}:{verba_id}".encode()).hexdigest()


def escolher(candidatas: list[dict], quantas: int, semente: str) -> list[dict]:
    """Até `quantas` verbas, alternando entre as situações da fonte e, em cada uma, na ordem estável do hash do id."""
    por_situacao: dict[str, list[dict]] = {}
    for v in sorted(candidatas, key=lambda v: _ordem(semente, v["id"])):
        por_situacao.setdefault(v["status_fonte"], []).append(v)
    filas = [por_situacao[k] for k in sorted(por_situacao)]
    escolhidas: list[dict] = []
    while len(escolhidas) < quantas and any(filas):
        for fila in filas:
            if fila and len(escolhidas) < quantas:
                escolhidas.append(fila.pop(0))
    return escolhidas


def montar_amostra(verbas: list[dict], semente: str = "verba-a-vista") -> list[tuple[str, dict]]:
    """[(grupo, verba)] sem repetir verba. Grupo que não tem verbas suficientes é completado com sobras de outros."""
    usadas: set[str] = set()
    amostra: list[tuple[str, dict]] = []
    faltam = 0
    for nome, entra, quantas in GRUPOS:
        livres = [v for v in verbas if v["id"] not in usadas and entra(v)]
        for v in (escolhidas := escolher(livres, quantas, semente)):
            usadas.add(v["id"])
            amostra.append((nome, v))
        faltam += quantas - len(escolhidas)
    if faltam:
        sobras = [v for v in verbas if v["id"] not in usadas]
        for v in escolher(sobras, faltam, semente):
            usadas.add(v["id"])
            amostra.append(("Complemento (faltou verba em algum grupo)", v))
    return amostra


def _reais(centavos: int | None) -> str:
    return "" if centavos is None else f"{centavos // 100},{centavos % 100:02d}"


def _data(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso else ""


def linha(numero: int, grupo: str, v: dict, taxonomia) -> list[str]:
    perda = v.get("perda")
    prazos = v.get("prazos") or {}
    campos = [
        str(numero), grupo, v["id"], v["nome"], taxonomia.tipos[v["tipo"]], v.get("instrumento") or "", v.get("orgao_concedente") or "",
        v.get("numero_instrumento") or "", v["id_fonte"], _reais(v["valor_total"]), _reais(v.get("valor_liberado")),
        taxonomia.status[v["status_site"]] if v["status_site"] else taxonomia.sem_status, v["status_fonte"],
        "; ".join(m["texto"] for m in v["motivos_risco"]) if v["em_risco"] else "",
        ("Em apuração" if perda["categoria"] == "em_apuracao" else taxonomia.categorias[perda["categoria"]].rotulo) if perda else "",
        _reais(perda["valor_perdido"]) if perda else "", _data(perda["data"]) if perda else "",
        _data(prazos.get("proposta")), _data(prazos.get("assinatura")), _data(prazos.get("fim_vigencia")), _data(prazos.get("prestacao_contas")),
        v["fontes"][0]["nome"], f"/verbas/{v['id']}/",
    ]
    return [texto_seguro(c) for c in campos] + [""] * len(COLUNAS_RESPOSTA)


def gravar_csv(amostra: list[tuple[str, dict]], destino: Path, taxonomia) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8-sig", newline="") as f:  # BOM para o Excel reconhecer UTF-8
        escritor = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        escritor.writerow(COLUNAS_FIXAS + COLUNAS_RESPOSTA)
        for i, (grupo, v) in enumerate(amostra, start=1):
            escritor.writerow(linha(i, grupo, v, taxonomia))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nucleo.amostra", description="Gera a planilha de amostra para a revisão de credibilidade.")
    parser.add_argument("--raiz", type=Path, default=RAIZ)
    parser.add_argument("--saida", type=Path, default=None, help="padrão: docs/revisao-credibilidade/amostra.csv")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    publicado = json.loads((args.raiz / "dados" / "publicados" / "verbas.json").read_text(encoding="utf-8"))
    amostra = montar_amostra(publicado["verbas"])
    destino = args.saida or args.raiz / "docs" / "revisao-credibilidade" / "amostra.csv"
    gravar_csv(amostra, destino, carregar_config().taxonomia)
    print(f"{len(amostra)} verbas de {len(publicado['verbas'])} (dados de {publicado['atualizado_em'][:10]}) em {destino}")
    for grupo, v in amostra:
        print(f"  - {grupo}: {v['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
