"""Conferência semanal no Acesso Livre do Transferegov (D23): o que o script local lê e como vira retrato.

O navegador é dirigido por `scripts/sync_acesso_livre.py` (Playwright, feito para uma pessoa rodar). Este módulo não
abre página nenhuma: recebe as linhas que o script leu e cuida do que dá para testar offline:
- limpeza dos pareceres (sem nome, telefone nem e-mail de servidor: regra "sem nomes de pessoas");
- escolha das propostas cujos pareceres valem a pena abrir;
- montagem do retrato `dados/brutos/transferegov_acesso_livre/AAAA-MM-DD.json` (`origem: manual local`).
"""

import re
from datetime import date, datetime

from coleta.base import RetratoBruto

FONTE = "transferegov_acesso_livre"
ORIGEM = "manual local"
LIMITE_PARECERES_POR_PROPOSTA = 6
LIMITE_PROPOSTAS_COM_PARECER = 12

# Telefone com DDD entre parênteses ou com hífen no meio: não casa data nem número de proposta ("14/09/2026", "140/2026").
TELEFONE = re.compile(r"\(\d{2}\)\s*9?\d{4}-?\d{4}|\b\d{2}\s?9?\d{4}-\d{4}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ABRE_CONTATO = re.compile(r"^(contato|respons[aá]vel|atenciosamente|telefone|fone|e-?mail)\b", re.I)


def limpar_parecer(texto: str) -> str:
    """Tira do parecer as frases com telefone ou e-mail e as que apresentam contato ou assinatura.

    O resto fica como está: a citação na curadoria tem que ser literal. Nome de pessoa solto no corpo do texto não tem
    como ser achado aqui; a validação de citações (spec §7.4) e a revisão cuidam disso.
    """
    texto = re.sub(r"[ \t\r\f\v]+", " ", texto or "").strip()
    frases = re.split(r"(?<=[.!?])\s+", texto)
    mantidas = [f for f in frases if not (TELEFONE.search(f) or EMAIL.search(f) or ABRE_CONTATO.match(f.strip()))]
    return " ".join(mantidas).strip()


def ler_paginacao(texto: str) -> tuple[int, int, int] | None:
    """'Página 1 de 13 (241 item(s))' -> (1, 13, 241); None se o texto não tem a linha de paginação."""
    m = re.search(r"P[aá]gina\s+(\d+)\s+de\s+(\d+)\s+\((\d+)\s+item", texto or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def data_br(texto: str) -> str | None:
    """'25/08/2026' -> '2026-08-25'."""
    m = re.fullmatch(r"\s*(\d{2})/(\d{2})/(\d{4})\s*", texto or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def linha_da_lista(bruta: dict) -> dict:
    """Linha da tabela de propostas como o script a leu -> registro do retrato."""
    return {
        "id_proposta": str(bruta["id_proposta"]),
        "numero": bruta["numero"].strip(),
        "situacao": bruta["situacao"].strip(),
        "orgao": bruta["orgao"].strip(),
        "possui_parecer": bruta["possui_parecer"].strip().lower() in ("sim", "s"),
    }


def parecer_do_retrato(id_proposta: str, bruto: dict) -> dict:
    """Parecer como o script o leu -> registro do retrato (sem o nome do responsável, com o texto limpo)."""
    return {
        "id_proposta": str(id_proposta),
        "id_parecer": str(bruto["id_parecer"]),
        "data": data_br(bruto["data"]),
        "parecer_do": bruto["parecer_do"].strip(),
        "atribuicao": bruto["atribuicao"].strip(),
        "texto": limpar_parecer(bruto["texto"]),
    }


def situacoes_do_siconv(retrato_siconv: dict | None) -> dict[str, str]:
    """ID_PROPOSTA -> situação no lote do Siconv, a mesma que a lista do Acesso Livre mostra.

    Proposta que já virou convênio mostra a situação do **convênio** ("Em execução"); a sem convênio, a da proposta.
    Com mais de um convênio, vale o ativo (ou o de maior `NR_CONVENIO`), como na normalização.
    """
    if retrato_siconv is None:
        return {}
    d = retrato_siconv["dados"]
    convenio: dict[str, dict] = {}
    for c in sorted(d["convenio"], key=lambda c: (c["INSTRUMENTO_ATIVO"] == "SIM", int(c["NR_CONVENIO"]))):
        convenio[c["ID_PROPOSTA"]] = c  # o último, o ativo ou o maior, fica
    return {p["ID_PROPOSTA"]: (convenio[p["ID_PROPOSTA"]]["SIT_CONVENIO"] if p["ID_PROPOSTA"] in convenio else p["SIT_PROPOSTA"]) for p in [*d["proposta"], *d.get("proposta_cancelada", [])]}


def propostas_para_pareceres(propostas: list[dict], situacoes_siconv: dict[str, str], perdidas: set[str], limite: int = LIMITE_PROPOSTAS_COM_PARECER) -> list[dict]:
    """Propostas com parecer cujos textos valem a leitura: as que mudaram desde o lote, as que ele não tem e as perdidas.

    As que mudaram ou são novas vêm primeiro (são o que o site ainda não sabe).
    """
    def novidade(p: dict) -> bool:
        antes = situacoes_siconv.get(p["id_proposta"])
        return antes is None or antes.strip().casefold() != p["situacao"].strip().casefold()

    candidatas = [p for p in propostas if p["possui_parecer"] and (novidade(p) or p["id_proposta"] in perdidas)]
    candidatas.sort(key=lambda p: (not novidade(p), p["numero"]))
    return candidatas[:limite]


def montar_retrato(propostas: list[dict], pareceres: list[dict], agora: datetime, metadados: dict) -> RetratoBruto:
    ordenadas = sorted(propostas, key=lambda p: int(p["id_proposta"]))
    return RetratoBruto(
        fonte=FONTE,
        data=agora.date(),
        coletado_em=agora,
        metadados={**metadados, "origem": ORIGEM},
        dados={"propostas": ordenadas, "pareceres": sorted(pareceres, key=lambda p: (int(p["id_proposta"]), p["data"] or "", p["id_parecer"]))},
    )


def dias_desde(retrato: dict | None, hoje: date) -> int | None:
    """Dias desde a última conferência; None se nunca houve."""
    return None if retrato is None else (hoje - date.fromisoformat(retrato["data"])).days
