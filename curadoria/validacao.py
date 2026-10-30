"""Validação automática do rascunho da IA (spec §7.4, T3.3).

O rascunho é reprovado se:
- não valida no JSON Schema;
- algum `trecho` citado não aparece literalmente (após normalizar espaços e caixa) no `texto` do documento citado;
- alguma frase do `texto` não tem marcador `[n]` (ou o marcador aponta para uma citação que não existe);
- o `texto` parece conter nome de pessoa. Na dúvida, reprova: o rascunho vai para `dados/fila/<id>.erro.yaml`.

O que não reprova mas o revisor precisa ver vai em `avisos` (ex.: citação que o texto não usa).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from curadoria.dossie import Dossie
from curadoria.ia import RAIZ, carregar_schema
from nucleo.config import Config
from nucleo.modelo import Verba

MARCADOR = re.compile(r"\[(\d+)\]")
SENTENCA = re.compile(r".+?[.!?](?:\s*\[\d+\])*(?=\s|$)|.+$", re.S)  # o marcador pode vir antes ou depois do ponto
PALAVRA = re.compile(r"[^\W\d_][\w'’-]*")
CARGO_E_NOME = re.compile(
    r"\b(?:prefeit[oa]|vice-prefeit[oa]|vereador[a]?|deputad[oa]|senador[a]?|secretári[oa]|diretor[a]?|engenheir[oa]|"
    r"presidente|ministr[oa]|sr|sra|dr|dra)\b\.?\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý]"
)
CONECTORES = {"de", "da", "do", "das", "dos", "e"}
# Palavras de órgão, instrumento e situação que aparecem com maiúscula nos documentos e não identificam pessoa.
PALAVRAS_PERMITIDAS = {
    p.casefold()
    for p in (
        "Ministério Secretaria Prefeitura Município Municipal Estadual Federal Governo União Estado Câmara Fundo Conselho Departamento "
        "Agência Instituto Fundação Empresa Companhia Caixa Econômica Banco Tribunal Controladoria Gabinete Comissão Programa Plano "
        "Trabalho Proposta Convênio Termo Compromisso Contrato Instrumento Emenda Parlamentar Transferegov Siconv Obrasgov CAUC "
        "Portal Transparência Tesouro Nacional Diário Oficial Rejeitada Rejeitado Rejeitados Rejeitadas Reprovada Aprovada "
        "Cancelada Impedimento Técnico Análise Cadastrada Enviada Execução Prestação Contas Cláusula Suspensiva "
        "Contrapartida Repasse Obra Obras Saúde Educação Agricultura Pecuária Cidades Desenvolvimento Regional Social Assistência "
        "Esporte Cultura Turismo Justiça Segurança Pública Integração Meio Ambiente Mulheres Direitos Humanos"
    ).split()
}


@dataclass
class Validacao:
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros


def normalizar(texto: str) -> str:
    """Espaços colapsados e caixa ignorada: a única tolerância da conferência de trechos (§7.4)."""
    return " ".join(texto.split()).casefold()


def permitidos_da_verba(verba: Verba, config: Config) -> list[str]:
    """Nomes que podem aparecer no texto: município, órgão concedente e o nome/objeto da própria verba."""
    return [config.regras.municipio.nome, verba.orgao_concedente or "", verba.nome or "", verba.objeto or ""]


def frases(texto: str) -> list[str]:
    return [m.group().strip() for m in SENTENCA.finditer(texto.strip())]


def _nomes_suspeitos(texto: str, permitidos: list[str]) -> list[str]:
    """Sequências de 2+ palavras com inicial maiúscula (ligadas ou não por de/da/do...) que não são só nomes permitidos."""
    liberadas = set(PALAVRAS_PERMITIDAS)
    for nome in permitidos:
        liberadas.update(p.casefold() for p in PALAVRA.findall(nome))
    suspeitos: list[str] = []
    corrente: list[str] = []

    def fechar() -> None:
        while corrente and corrente[-1].casefold() in CONECTORES:
            corrente.pop()
        capitalizadas = [p for p in corrente if p.casefold() not in CONECTORES]
        if len(capitalizadas) >= 2 and any(p.casefold() not in liberadas for p in capitalizadas):
            suspeitos.append(" ".join(corrente))
        corrente.clear()

    for palavra in PALAVRA.findall(texto):
        if len(palavra) > 1 and palavra[0].isupper():
            corrente.append(palavra)
        elif palavra.casefold() in CONECTORES and corrente:
            corrente.append(palavra)
        else:
            fechar()
    fechar()
    return suspeitos


def validar_rascunho(dados: dict, dossie: Dossie, permitidos: list[str] | None = None, config: Config | None = None, raiz: Path = RAIZ) -> Validacao:
    """Aplica as quatro regras do §7.4. `permitidos`: nomes próprios que podem aparecer no texto (ver `permitidos_da_verba`)."""
    resultado = Validacao()
    try:
        jsonschema.validate(dados, carregar_schema(raiz))
    except jsonschema.ValidationError as erro:
        resultado.erros.append(f"fora do schema: {erro.message}")
        return resultado  # sem a forma certa não dá para conferir o resto

    if dados["verba_id"] != dossie.verba_id:
        resultado.erros.append(f"rascunho é da verba {dados['verba_id']}, não de {dossie.verba_id}")
    texto, citacoes = dados["texto"], dados["citacoes"]

    numeros = [c["n"] for c in citacoes]
    if len(set(numeros)) != len(numeros):
        resultado.erros.append("há citações com o mesmo número `n`")

    for c in citacoes:
        documento = dossie.por_id(c["documento_id"])
        if documento is None:
            resultado.erros.append(f"citação [{c['n']}] aponta para o documento `{c['documento_id']}`, que não está no dossiê")
        elif normalizar(c["trecho"]) not in normalizar(documento.texto):
            resultado.erros.append(f"citação [{c['n']}]: o trecho não aparece literalmente no documento `{documento.id}`")

    padrao = config.regras.curadoria.texto_em_apuracao if config else None
    em_apuracao_padrao = dados["categoria"] == "em_apuracao" and not citacoes and (padrao is None or texto.strip() == padrao)
    if not em_apuracao_padrao:
        usados = {int(n) for n in MARCADOR.findall(texto)}
        for numero in sorted(usados - set(numeros)):
            resultado.erros.append(f"o texto cita [{numero}], que não existe em `citacoes`")
        for frase in frases(texto):
            if not MARCADOR.search(frase):
                resultado.erros.append(f"frase sem citação: «{frase}»")
        for numero in sorted(set(numeros) - usados):
            resultado.avisos.append(f"a citação [{numero}] não é usada no texto")
        if dados["categoria"] == "em_apuracao":
            resultado.erros.append("categoria em_apuracao exige `citacoes` vazias e o texto padrão")

    if CARGO_E_NOME.search(texto):
        resultado.erros.append("o texto cita cargo seguido de nome (nome de pessoa?)")
    for nome in _nomes_suspeitos(texto, permitidos or []):
        resultado.erros.append(f"possível nome de pessoa no texto: «{nome}»")
    return resultado
