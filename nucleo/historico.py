"""Histórico e detecção de perda (spec §6.1 e §9; plano T2.4; decisão D14).

Compara as verbas normalizadas de hoje com o publicado anterior (`dados/publicados/verbas.json`):
- cada mudança de situação vira uma entrada em `historico[]`;
- uma perda nova ganha `perda` (motivo "em apuração" até haver curadoria, spec §7) e `valor_perdido`;
- as perdas sem arquivo em `dados/curadoria/` entram em `precisam_curadoria` (o pedido de curadoria); as que têm arquivo recebem o motivo revisado (T3.4).

O publicado anterior é fonte de verdade do passado: se ele existe mas não pode ser lido, o pipeline PARA em vez
de recomeçar o histórico do zero.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from nucleo.config import Config
from nucleo.curadoria_revisada import aplicar_curadoria, carregar_curadoria, perda_sem_motivo
from nucleo.modelo import Historico, Perda, Verba
from nucleo.normaliza import Normalizacao

ARQUIVO_PUBLICADO = Path("dados") / "publicados" / "verbas.json"
SEM_STATUS = "situacao_em_analise"  # o selo do site para verba sem status mapeado (spec §4)
PREFIXO_SICONV = "transferegov_discricionarias"


@dataclass
class ResultadoHistorico:
    primeira_execucao: bool
    novas: list[str] = field(default_factory=list)  # ids sem publicação anterior
    mudancas: list[str] = field(default_factory=list)  # ids com situação nova desde a publicação anterior
    perdas_novas: list[str] = field(default_factory=list)
    desaparecidas: list[str] = field(default_factory=list)  # estavam publicadas e não saíram nas fontes de hoje
    precisam_curadoria: list[str] = field(default_factory=list)  # perdas sem dados/curadoria/<id>.yaml
    avisos: list[str] = field(default_factory=list)


def carregar_anterior(raiz: Path) -> dict[str, Verba] | None:
    """Verbas do último `verbas.json` publicado, por id; None se nunca houve publicação (primeira execução)."""
    caminho = raiz / ARQUIVO_PUBLICADO
    if not caminho.exists():
        return None
    try:
        corpo = json.loads(caminho.read_text(encoding="utf-8"))
        brutas = corpo["verbas"]
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"{caminho}: não foi possível ler o publicado anterior ({type(e).__name__}: {e}); o histórico não será recomeçado") from e
    anteriores: dict[str, Verba] = {}
    for bruta in brutas:
        try:
            verba = Verba.model_validate(bruta)
        except ValueError as e:
            raise ValueError(f"{caminho}: verba {bruta.get('id') if isinstance(bruta, dict) else bruta!r} inválida no publicado anterior: {e}") from e
        anteriores[verba.id] = verba
    return anteriores


def datas_do_siconv(retrato_siconv: dict | None) -> dict[str, date]:
    """Data do último evento de cada proposta em `siconv_historico_situacao`: quando a fonte registra a situação atual."""
    if retrato_siconv is None:
        return {}
    datas: dict[str, date] = {}
    for evento in retrato_siconv["dados"]["historico_situacao"]:
        dia = datetime.strptime(evento["DIA_HISTORICO_SIT"][:19], "%d/%m/%Y %H:%M:%S").date()
        chave = f"{PREFIXO_SICONV}-{evento['ID_PROPOSTA']}"
        if chave not in datas or dia > datas[chave]:
            datas[chave] = dia
    return datas


def rotulo(verba: Verba) -> str:
    return verba.status_site or SEM_STATUS


def valor_perdido(verba: Verba) -> tuple[int, str | None]:
    """(valor, aviso). Repasse da União não liberado + valor devolvido (spec §6.1).

    O repasse é o valor total menos a contrapartida (o `valor_total` do Siconv é o global, com a parte do município).
    """
    aviso = None
    if verba.valor_total is None:
        aviso = f"{verba.id}: valor_total ausente; valor_perdido considera só o valor devolvido"
        repasse = 0
    else:
        repasse = max(verba.valor_total - (verba.valor_contrapartida or 0), 0)
    nao_liberado = max(repasse - (verba.valor_liberado or 0), 0)
    return nao_liberado + (verba.valor_devolvido or 0), aviso


def _perda_nova(verba: Verba, data_da_perda: date, config: Config, avisos: list[str]) -> Perda:
    valor, aviso = valor_perdido(verba)
    if aviso:
        avisos.append(aviso)
    return Perda(
        categoria="em_apuracao",
        texto=config.regras.curadoria.texto_em_apuracao,
        citacoes=[],
        evitavel="indeterminado",
        data=data_da_perda,
        valor_perdido=valor,
        gerado_por_ia=False,
    )


def _nota_de_mudanca(anterior: Verba, atual: Verba) -> str | None:
    if anterior.status_fonte != atual.status_fonte:
        return f"Situação na fonte: {anterior.status_fonte} → {atual.status_fonte}"
    return "Mapeamento da situação atualizado" if anterior.status_site != atual.status_site else None


def aplicar_historico(
    normalizacao: Normalizacao,
    anterior: dict[str, Verba] | None,
    data: date,
    config: Config,
    raiz: Path,
    retratos: dict[str, dict | None] | None = None,
) -> ResultadoHistorico:
    """Preenche `historico` e `perda` nas verbas de `normalizacao`, comparando com o publicado anterior."""
    resultado = ResultadoHistorico(primeira_execucao=anterior is None)
    datas_fonte = datas_do_siconv((retratos or {}).get("transferegov_discricionarias"))
    anteriores = anterior or {}

    for verba in normalizacao.verbas:
        antes = anteriores.get(verba.id)
        desde = normalizacao.conferidas.get(verba.id) or datas_fonte.get(verba.id)  # D23: a conferência no Acesso Livre é a data mais nova
        if antes is None:
            nota = "Primeira coleta" if resultado.primeira_execucao else "Verba apareceu nas fontes"
            if desde:
                nota += f"; situação registrada na fonte desde {desde.strftime('%d/%m/%Y')}"
            verba.historico = [Historico(data=data, de=None, para=rotulo(verba), fonte=verba.fonte, nota=nota)]
            resultado.novas.append(verba.id)
        else:
            verba.historico = list(antes.historico)
            if (antes.status_site, antes.status_fonte) != (verba.status_site, verba.status_fonte):
                verba.historico.append(Historico(data=data, de=rotulo(antes), para=rotulo(verba), fonte=verba.fonte, nota=_nota_de_mudanca(antes, verba)))
                resultado.mudancas.append(verba.id)

        if verba.status_site == "perdida":
            if antes is not None and antes.status_site == "perdida" and antes.perda is not None:
                # Data e valor ficam como na detecção; o motivo NÃO é copiado do publicado anterior: só `dados/curadoria/` o define.
                verba.perda = perda_sem_motivo(antes.perda, config.regras.curadoria.texto_em_apuracao)
            else:
                verba.perda = _perda_nova(verba, desde or data, config, resultado.avisos)
                resultado.perdas_novas.append(verba.id)
            curadoria = carregar_curadoria(raiz, verba.id, config.regras.curadoria.texto_em_apuracao)
            if curadoria is None:
                resultado.precisam_curadoria.append(verba.id)
            else:
                verba.perda = aplicar_curadoria(verba.perda, curadoria)  # só a curadoria revisada muda o motivo publicado

    atuais = {v.id for v in normalizacao.verbas}
    resultado.desaparecidas = sorted(set(anteriores) - atuais)
    if resultado.desaparecidas:
        resultado.avisos.append(f"{len(resultado.desaparecidas)} verba(s) do publicado anterior não saíram das fontes e não serão publicadas: {', '.join(resultado.desaparecidas[:5])}")
    return resultado
