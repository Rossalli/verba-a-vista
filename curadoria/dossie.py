"""Dossiê de uma verba perdida: os documentos oficiais que a IA pode ler (spec §7.2, T3.1).

Fase 1: só documentos obtidos automaticamente, todos tirados dos retratos brutos (nada é baixado aqui):
- `instrumento-<id>`: dados da proposta, do convênio e das emendas no Transferegov (Siconv em lote);
- `historico-situacao-<id>`: trilha de datas de cada mudança de situação (traz a data, não o motivo);
- `cauc-<data>`: itens do CAUC sem comprovação no retrato mais próximo da data da perda;
- `obrasgov-<projeto>`: histórico de paralisação/cancelamento da obra ligada, com a justificativa em texto livre;
- `parecer-<proposta>-<data>`: parecer do concedente lido na consulta pública do Transferegov (Acesso Livre, D23), sem nome
  nem contato de servidor; vem da conferência semanal, rodada por uma pessoa (`scripts/sync_acesso_livre.py`).

Os campos de cada documento são escolhidos a dedo: nada de endereço, conta bancária ou nome de parlamentar
(regra: sem nomes de pessoas nos textos de motivo).
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from nucleo.dinheiro import centavos_texto
from nucleo.historico import PREFIXO_SICONV
from nucleo.modelo import Verba
from nucleo.risco import itens_sem_comprovacao

CAMPOS_PROPOSTA = {
    "NR_PROPOSTA": "Número da proposta",
    "ANO_PROP": "Ano da proposta",
    "MODALIDADE": "Modalidade",
    "DESC_ORGAO": "Órgão concedente",
    "OBJETO_PROPOSTA": "Objeto",
    "SIT_PROPOSTA": "Situação da proposta",
    "SITUACAO_PROJETO_BASICO": "Situação do projeto básico",
    "DIA_PROPOSTA": "Data da proposta",
    "DIA_INIC_VIGENCIA_PROPOSTA": "Início da vigência da proposta",
    "DIA_FIM_VIGENCIA_PROPOSTA": "Fim da vigência da proposta",
}
CAMPOS_VALOR_PROPOSTA = {
    "VL_GLOBAL_PROP": "Valor global",
    "VL_REPASSE_PROP": "Valor do repasse",
    "VL_CONTRAPARTIDA_PROP": "Contrapartida",
}
CAMPOS_CONVENIO = {
    "NR_CONVENIO": "Número do convênio",
    "SIT_CONVENIO": "Situação do convênio",
    "SUBSITUACAO_CONV": "Subsituação do convênio",
    "SITUACAO_CONTRATACAO": "Situação da contratação",
    "SITUACAO_PUBLICACAO": "Situação da publicação",
    "INSTRUMENTO_ATIVO": "Instrumento ativo",
    "DIA_ASSIN_CONV": "Data da assinatura",
    "DIA_FIM_VIGENC_CONV": "Fim da vigência",
    "DATA_SUSPENSIVA": "Data da cláusula suspensiva",
    "DATA_RETIRADA_SUSPENSIVA": "Data da retirada da cláusula suspensiva",
    "MOTIVO_SUSPENSAO": "Motivo da suspensão",
}
CAMPOS_VALOR_CONVENIO = {
    "VL_GLOBAL_CONV": "Valor global",
    "VL_REPASSE_CONV": "Valor do repasse",
    "VL_DESEMBOLSADO_CONV": "Valor desembolsado",
}
CAMPOS_EMENDA = {"NR_EMENDA": "Número da emenda", "TIPO_PARLAMENTAR": "Tipo de autoria", "IND_IMPOSITIVO": "Impositiva"}
CAMPOS_OBRASGOV = (
    "descricao_historico_situacao_investimento",
    "data_historico_situacao_investimento",
    "justificativa_cancelada_paralisada",
    "possui_tratativas_situacao_investimento",
    "fase_tratativas_situacao_investimento",
)


@dataclass(frozen=True)
class Documento:
    id: str
    titulo: str
    url: str
    data_coleta: str  # ISO 8601 com fuso, como veio do retrato
    texto: str


@dataclass
class Dossie:
    verba_id: str
    documentos: list[Documento] = field(default_factory=list)

    def por_id(self, documento_id: str) -> Documento | None:
        return next((d for d in self.documentos if d.id == documento_id), None)


def _linhas(registro: dict, campos: dict[str, str], valores: dict[str, str] | None = None) -> list[str]:
    """`Rótulo: valor` só dos campos preenchidos; os de `valores` vêm em reais (a fonte guarda reais, texto BR)."""
    linhas = []
    for chave, rotulo in campos.items():
        valor = str(registro.get(chave) or "").strip()
        if valor:
            linhas.append(f"{rotulo}: {valor}")
    for chave, rotulo in (valores or {}).items():
        valor = str(registro.get(chave) or "").strip()
        if valor:
            reais, centavos = divmod(centavos_texto(valor), 100)
            linhas.append(f"{rotulo}: R$ {reais:,}".replace(",", ".") + f",{centavos:02d}")
    return linhas


def _data_hora(texto: str) -> datetime:
    return datetime.strptime(texto[:19], "%d/%m/%Y %H:%M:%S")


def _documento_instrumento(verba: Verba, dados: dict, retrato: dict, url: str) -> Documento | None:
    id_proposta = verba.id_fonte
    proposta = next((p for p in dados["proposta"] if p["ID_PROPOSTA"] == id_proposta), None)
    if proposta is None:
        return None
    linhas = _linhas(proposta, CAMPOS_PROPOSTA, CAMPOS_VALOR_PROPOSTA)
    for convenio in (c for c in dados["convenio"] if c["ID_PROPOSTA"] == id_proposta):
        linhas.append("")
        linhas += _linhas(convenio, CAMPOS_CONVENIO, CAMPOS_VALOR_CONVENIO)
    for emenda in (e for e in dados["emenda"] if e["ID_PROPOSTA"] == id_proposta):
        linhas.append("")
        linhas += _linhas(emenda, CAMPOS_EMENDA)
    return Documento(
        id=f"instrumento-{id_proposta}",
        titulo=f"Transferegov: proposta {proposta['NR_PROPOSTA']} e instrumento",
        url=url,
        data_coleta=retrato["coletado_em"],
        texto="\n".join(linhas),
    )


def _documento_historico(verba: Verba, dados: dict, retrato: dict, url: str) -> Documento | None:
    eventos = sorted(
        (e for e in dados["historico_situacao"] if e["ID_PROPOSTA"] == verba.id_fonte),
        key=lambda e: _data_hora(e["DIA_HISTORICO_SIT"]),
    )
    if not eventos:
        return None
    texto = "\n".join(f"{_data_hora(e['DIA_HISTORICO_SIT']):%d/%m/%Y}: {e['HISTORICO_SIT']}" for e in eventos)
    return Documento(
        id=f"historico-situacao-{verba.id_fonte}",
        titulo=f"Transferegov: histórico de situação da proposta {verba.numero_instrumento}",
        url=url,
        data_coleta=retrato["coletado_em"],
        texto=texto,
    )


def _retrato_cauc_mais_proximo(raiz: Path, data_perda: date) -> tuple[dict, date] | None:
    candidatos = []
    for caminho in (raiz / "dados" / "brutos" / "cauc").glob("????-??-??.json"):
        dia = date.fromisoformat(caminho.stem)
        candidatos.append((abs((dia - data_perda).days), dia, caminho))
    if not candidatos:
        return None
    _, dia, caminho = min(candidatos)
    return json.loads(caminho.read_text(encoding="utf-8")), dia


def _documento_cauc(verba: Verba, raiz: Path, url: str) -> Documento | None:
    if verba.perda is None or verba.perda.data is None:
        return None
    achado = _retrato_cauc_mais_proximo(raiz, verba.perda.data)
    if achado is None:
        return None
    retrato, dia = achado
    itens = itens_sem_comprovacao(retrato)
    if itens:
        texto = "Itens do CAUC sem comprovação:\n" + "\n".join(f"{codigo} {exigencia}" for codigo, exigencia in itens)
    else:
        texto = "Nenhum item do CAUC consta sem comprovação."
    return Documento(
        id=f"cauc-{dia.isoformat()}",
        titulo=f"CAUC: situação do município em {dia:%d/%m/%Y}",
        url=retrato["metadados"].get("recurso", {}).get("url") or url,  # o CSV do dia, quando o retrato o registra
        data_coleta=retrato["coletado_em"],
        texto=texto,
    )


def _documento_obrasgov(verba: Verba, dados: dict, retrato: dict, url: str, id_projeto: str) -> Documento | None:
    registros = [h for h in dados["historico_situacao"] if h.get("id_projeto_investimento") == id_projeto]
    if not registros:
        return None
    registros.sort(key=lambda h: h.get("data_historico_situacao_investimento") or "")
    blocos = []
    for registro in registros:
        blocos.append("\n".join(f"{campo}: {registro[campo]}" for campo in CAMPOS_OBRASGOV if registro.get(campo) not in (None, "")))
    return Documento(
        id=f"obrasgov-{id_projeto}",
        titulo=f"Obrasgov: histórico de situação do projeto {id_projeto}",
        url=url,
        data_coleta=retrato["coletado_em"],
        texto="\n\n".join(blocos),
    )


def _documentos_pareceres(verba: Verba, acesso: dict, url: str) -> list[Documento]:
    """Um documento por parecer do concedente lido no Acesso Livre (já sem nome e contato, `coleta.acesso_livre`)."""
    saida: list[Documento] = []
    for parecer in sorted((p for p in acesso["dados"]["pareceres"] if p["id_proposta"] == verba.id_fonte), key=lambda p: (p["data"] or "", p["id_parecer"])):
        base = f"parecer-{verba.id_fonte}-{parecer['data']}"
        documento_id = base if all(d.id != base for d in saida) else f"{base}-{parecer['id_parecer']}"  # dois no mesmo dia
        dia = date.fromisoformat(parecer["data"])
        saida.append(
            Documento(
                id=documento_id,
                titulo=f"Transferegov (Acesso Livre): parecer do {parecer['parecer_do'].lower()} de {dia:%d/%m/%Y}, proposta {verba.numero_instrumento}",
                url=url,
                data_coleta=acesso["coletado_em"],
                texto=f"Parecer do {parecer['parecer_do']} ({parecer['atribuicao']}), {dia:%d/%m/%Y}:\n{parecer['texto']}",
            )
        )
    return saida


def _id_projeto_obrasgov(verba: Verba, siconv: dict, obras: dict) -> str | None:
    convenio = next((c for c in siconv["dados"]["convenio"] if c["ID_PROPOSTA"] == verba.id_fonte), None)
    if convenio is None:
        return None
    ponte = {r["nr_instrumento"]: r["id_projeto_investimento"] for r in obras["dados"]["ponte_siconv"]}
    return ponte.get(convenio["NR_CONVENIO"])


def montar_dossie(verba: Verba, retratos: dict[str, dict | None], raiz: Path, urls: dict[str, str]) -> Dossie:
    """Documentos disponíveis para `verba` (só as do Siconv têm dossiê na fase 1; as demais voltam vazias).

    `urls` mapeia a chave da fonte (`transferegov_discricionarias`, `cauc`, `obrasgov`) à URL citada no documento.
    Documento sem dado na fonte simplesmente não entra: o dossiê pode vir vazio, e a IA então responde `em_apuracao`.
    """
    dossie = Dossie(verba.id)
    siconv = retratos.get("transferegov_discricionarias")
    if verba.fonte != "transferegov_discricionarias" or not verba.id.startswith(f"{PREFIXO_SICONV}-") or siconv is None:
        return dossie
    candidatos = [
        _documento_instrumento(verba, siconv["dados"], siconv, urls["transferegov_discricionarias"]),
        _documento_historico(verba, siconv["dados"], siconv, urls["transferegov_discricionarias"]),
        _documento_cauc(verba, raiz, urls["cauc"]),
    ]
    obras = retratos.get("obrasgov")
    if obras is not None:
        id_projeto = _id_projeto_obrasgov(verba, siconv, obras)
        if id_projeto:
            candidatos.append(_documento_obrasgov(verba, obras["dados"], obras, urls["obrasgov"], id_projeto))
    acesso = retratos.get("transferegov_acesso_livre")
    if acesso is not None and "transferegov_acesso_livre" in urls:
        candidatos += _documentos_pareceres(verba, acesso, urls["transferegov_acesso_livre"])
    dossie.documentos = [d for d in candidatos if d is not None]
    return dossie
