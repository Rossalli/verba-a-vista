"""Regras de risco (spec §5; plano T2.3; decisão D13).

Cada regra é uma função pura (verba + o dado de que precisa + data + config -> motivo ou None), para testar as
bordas sem montar o pipeline. `aplicar_risco` roda as regras ligadas nas verbas das etapas de `risco.status` e
preenche `em_risco` e `motivos_risco`.

Princípio: ausência de dado nunca vira alerta (sem execução física não há "obra parada"; sem retrato do CAUC o
alerta de CAUC não é avaliado e isso vai para os avisos).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from nucleo.config import Config, normalizar_situacao
from nucleo.modelo import MotivoRisco, Verba
from nucleo.normaliza import ImpedimentoEmenda, Normalizacao, ObraLigada

COLUNA_ITEM = re.compile(r"\d\.\d(\.\d)?")
SITUACAO_IMPEDIDA = "IMPEDIDO"
SITUACOES_DE_OBRA_ENCERRADA = frozenset({"Concluída", "Cancelada", "Inacabada"})  # não se diz "parada" de obra encerrada
ORDEM = ("prazo_proximo", "cauc_sem_comprovacao", "obra_parada", "impedimento_emenda")


def _dias(n: int) -> dict:
    return {"dias": n, "dias_unidade": "dia" if n == 1 else "dias"}


def motivo_prazo(verba: Verba, data: date, config: Config) -> MotivoRisco | None:
    """`prazo_proximo`: o prazo monitorado mais próximo, de hoje até `dias_alerta_prazo` dias, extremos incluídos.

    Prazo vencido não conta (D13): `vence em até 60 dias` fala de prazo que ainda vai chegar.
    """
    risco = config.regras.risco
    if verba.prazos is None:
        return None
    candidatos = [(d, nome) for nome in risco.prazos_monitorados if (d := getattr(verba.prazos, nome)) is not None and 0 <= (d - data).days <= risco.dias_alerta_prazo]
    if not candidatos:
        return None
    prazo, _ = min(candidatos)
    return MotivoRisco(codigo="prazo_proximo", texto=risco.textos.prazo_proximo.format(**_dias((prazo - data).days)), data_limite=prazo)


def itens_sem_comprovacao(retrato_cauc: dict) -> list[tuple[str, str]]:
    """(código, exigência) dos itens `!` do município, em ordem numérica. `Desabilitado` e datas não contam."""
    (linha,) = retrato_cauc["dados"]["entes"]
    legenda = {x["codigo"]: x["exigencia"] for x in retrato_cauc["dados"]["legenda"]}
    itens = [c for c, valor in linha.items() if COLUNA_ITEM.fullmatch(c) and valor == "!"]
    return [(c, legenda.get(c, c)) for c in sorted(itens, key=lambda c: tuple(int(p) for p in c.split(".")))]


def motivos_cauc(verba: Verba, itens: list[tuple[str, str]], config: Config, data: date) -> list[MotivoRisco]:
    """`cauc_sem_comprovacao`: um motivo por item sem comprovação, só em verbas do tipo, da etapa e da fonte da regra.

    D17: não alerta verba com a vigência já encerrada (regularizar o CAUC não a salva) nem a situação da fonte que a
    regra ignora (proposta que ainda não foi enviada).
    """
    risco = config.regras.risco
    if verba.fonte not in risco.cauc_fontes or verba.tipo not in risco.cauc_tipos or verba.status_site not in risco.cauc_status:
        return []
    fim_vigencia = verba.prazos.fim_vigencia if verba.prazos else None
    if fim_vigencia is not None and fim_vigencia < data:
        return []
    if normalizar_situacao(verba.status_fonte) in {normalizar_situacao(s) for s in risco.cauc_ignora_situacoes_fonte}:
        return []
    return [MotivoRisco(codigo="cauc_sem_comprovacao", texto=risco.textos.cauc_sem_comprovacao.format(item=codigo, exigencia=exigencia)) for codigo, exigencia in itens]


def motivo_obra(verba: Verba, obra: ObraLigada, data: date, config: Config) -> MotivoRisco | None:
    """`obra_parada`: situação `Paralisada`, ou sem atualização de execução física há MAIS de `dias_obra_parada` dias.

    Sem registro de execução física a falta de atualização não dispara (ausência de dado não é obra parada).
    """
    risco = config.regras.risco
    if obra.situacao == "Paralisada":
        desde = obra.paralisada_desde or obra.ultima_atualizacao
        if desde is None:
            return MotivoRisco(codigo="obra_parada", texto=risco.textos.obra_paralisada)
        return MotivoRisco(codigo="obra_parada", texto=risco.textos.obra_parada.format(**_dias(max((data - desde).days, 0))))
    if obra.situacao in SITUACOES_DE_OBRA_ENCERRADA or obra.ultima_atualizacao is None:
        return None
    parada = (data - obra.ultima_atualizacao).days
    if parada > risco.dias_obra_parada:
        return MotivoRisco(codigo="obra_parada", texto=risco.textos.obra_parada.format(**_dias(parada)))
    return None


def motivo_impedimento(verba: Verba, impedimento: ImpedimentoEmenda, config: Config) -> MotivoRisco | None:
    """`impedimento_emenda`: impedimento técnico registrado e não superado (situação atual `IMPEDIDO`)."""
    if impedimento.situacao != SITUACAO_IMPEDIDA:
        return None
    return MotivoRisco(codigo="impedimento_emenda", texto=config.regras.risco.textos.impedimento_emenda)


@dataclass
class ResultadoRisco:
    verbas_em_risco: int
    por_codigo: Counter = field(default_factory=Counter)
    avisos: list[str] = field(default_factory=list)


def aplicar_risco(normalizacao: Normalizacao, retratos: dict[str, dict | None], config: Config, data: date) -> ResultadoRisco:
    """Preenche `em_risco` e `motivos_risco` nas verbas das etapas de `risco.status`; as demais ficam sem alerta."""
    risco = config.regras.risco
    ligadas = set(ORDEM) - set(risco.desligadas)
    etapas = set(risco.status)
    resultado = ResultadoRisco(0)

    itens_cauc: list[tuple[str, str]] = []
    if "cauc_sem_comprovacao" in ligadas:
        cauc = retratos.get("cauc")
        if cauc is None:
            resultado.avisos.append("CAUC sem retrato: o alerta de CAUC não foi avaliado")
        else:
            itens_cauc = itens_sem_comprovacao(cauc)
    if "obra_parada" in ligadas and retratos.get("obrasgov") is None:
        resultado.avisos.append("Obrasgov sem retrato: o alerta de obra parada não foi avaliado")

    for verba in normalizacao.verbas:
        if verba.status_site not in etapas:
            continue
        motivos: list[MotivoRisco] = []
        if "prazo_proximo" in ligadas and (m := motivo_prazo(verba, data, config)):
            motivos.append(m)
        if "cauc_sem_comprovacao" in ligadas:
            motivos += motivos_cauc(verba, itens_cauc, config, data)
        if "obra_parada" in ligadas and (obra := normalizacao.obras.get(verba.id)) and (m := motivo_obra(verba, obra, data, config)):
            motivos.append(m)
        if "impedimento_emenda" in ligadas and (imp := normalizacao.impedimentos.get(verba.id)) and (m := motivo_impedimento(verba, imp, config)):
            motivos.append(m)
        if motivos:
            verba.motivos_risco = motivos
            verba.em_risco = True
            resultado.verbas_em_risco += 1
            resultado.por_codigo.update(m.codigo for m in motivos)
        else:  # nova execução sobre verbas já avaliadas: limpa o alerta que deixou de valer
            verba.em_risco = False
            if verba.motivos_risco:
                verba.motivos_risco = []
    return resultado
