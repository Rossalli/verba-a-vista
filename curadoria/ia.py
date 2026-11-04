"""Cliente da IA na curadoria (spec §7.1 passos 2 e 3, T3.2).

Monta o prompt de `prompts/curadoria.md`, envia o dossiê e devolve o rascunho já validado no JSON Schema.
A validação de citações (§7.4) é da T3.3; aqui só se garante que a resposta é um JSON no formato do schema.

A chave vem de `ANTHROPIC_API_KEY` (ambiente ou `.env`); nunca é impressa nem gravada.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from curadoria.dossie import Dossie
from nucleo.config import Config, carregar_config

RAIZ = Path(__file__).resolve().parents[1]
SEPARADOR = "\n---\n"  # o prompt de verdade vem depois do primeiro separador do arquivo


class IAErro(Exception):
    """A chamada não produziu um rascunho utilizável.

    `retentavel` separa falha de infraestrutura (chave ausente ou sem workspace, API fora do ar, rede) de falha do
    conteúdo (recusa, corte por tamanho, JSON ou schema inválido). A primeira não diz nada sobre o rascunho: não se
    grava arquivo na fila e a perda é tentada de novo na próxima execução.
    """

    def __init__(self, mensagem: str, resposta_bruta: str | None = None, retentavel: bool = False) -> None:
        super().__init__(mensagem)
        self.resposta_bruta = resposta_bruta
        self.retentavel = retentavel


@dataclass
class Rascunho:
    dados: dict  # conforme schemas/rascunho_curadoria.schema.json
    modelo: str
    id_requisicao: str | None
    tokens_entrada: int
    tokens_saida: int


def carregar_schema(raiz: Path = RAIZ) -> dict:
    return json.loads((raiz / "schemas" / "rascunho_curadoria.schema.json").read_text(encoding="utf-8"))


def montar_prompt(config: Config, raiz: Path = RAIZ) -> str:
    """Prompt de sistema com municipio, uf, texto padrão, taxonomia e schema preenchidos."""
    modelo = (raiz / "prompts" / "curadoria.md").read_text(encoding="utf-8")
    corpo = modelo.split(SEPARADOR, 1)[1]
    taxonomia = "\n".join(f"- `{nome}`: {c.descricao}" for nome, c in config.taxonomia.categorias.items())
    valores = {
        "municipio": config.regras.municipio.nome,
        "uf": config.regras.municipio.uf,
        "texto_em_apuracao": config.regras.curadoria.texto_em_apuracao,
        "taxonomia": taxonomia,
        "schema": json.dumps(carregar_schema(raiz), ensure_ascii=False, indent=2),
    }
    for chave, valor in valores.items():
        corpo = corpo.replace("{{" + chave + "}}", valor)
    return corpo.strip()


def _atributo(valor: str) -> str:
    return valor.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def montar_mensagem(dossie: Dossie) -> str:
    """Mensagem do usuário: um `<documento>` por item. O texto vai sem alteração, para a citação literal bater."""
    blocos = [f"verba_id: {dossie.verba_id}", ""]
    for d in dossie.documentos:
        # Impede que o texto de um documento feche a tag e "saia" dela; é o único trecho alterado.
        texto = d.texto.replace("</documento", "< /documento")
        blocos.append(f'<documento id="{_atributo(d.id)}" titulo="{_atributo(d.titulo)}" url="{_atributo(d.url)}" data_coleta="{_atributo(d.data_coleta)}">')
        blocos.append(texto)
        blocos.append("</documento>")
        blocos.append("")
    return "\n".join(blocos).rstrip() + "\n"


def interpretar_resposta(texto: str, verba_id: str, raiz: Path = RAIZ) -> dict:
    """JSON da resposta validado no schema; levanta `IAErro` se não for JSON, não validar ou for de outra verba."""
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise IAErro(f"resposta não é JSON válido: {erro}", texto) from erro
    try:
        jsonschema.validate(dados, carregar_schema(raiz))
    except jsonschema.ValidationError as erro:
        raise IAErro(f"resposta fora do schema: {erro.message}", texto) from erro
    if dados["verba_id"] != verba_id:
        raise IAErro(f"resposta é da verba {dados['verba_id']}, não de {verba_id}", texto)
    return dados


def criar_cliente():
    """Cliente da Anthropic com a chave do ambiente (lê o `.env` se ela ainda não estiver lá)."""
    import os

    import anthropic

    from coleta.base import carregar_dotenv

    carregar_dotenv(RAIZ)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise IAErro("ANTHROPIC_API_KEY não definida (ambiente ou .env)", retentavel=True)
    return anthropic.Anthropic()


def gerar_rascunho(dossie: Dossie, config: Config | None = None, cliente=None, raiz: Path = RAIZ) -> Rascunho:
    """Pede ao modelo o rascunho de motivo da perda. `cliente` é injetável (testes usam um falso)."""
    import anthropic

    config = config or carregar_config()
    cur = config.regras.curadoria
    cliente = cliente or criar_cliente()
    try:
        resposta = cliente.messages.create(
            model=cur.modelo,
            max_tokens=cur.max_tokens,
            system=montar_prompt(config, raiz),
            messages=[{"role": "user", "content": montar_mensagem(dossie)}],
            # Raciocínio estendido desligado: a saída é um JSON curto e a conferência é mecânica (T3.3).
            # `disabled` dá 400 no Sonnet 5.5; `between_tools` é a forma de desligar.
            thinking={"type": "between_tools"},
        )
    except anthropic.APIError as erro:
        raise IAErro(f"falha na API da Anthropic: {type(erro).__name__}: {erro}", retentavel=True) from erro
    if resposta.stop_reason == "refusal":
        raise IAErro("o modelo recusou a requisição (stop_reason=refusal)")
    texto = "".join(b.text for b in resposta.content if b.type == "text")
    if resposta.stop_reason == "max_tokens":
        raise IAErro("resposta cortada por max_tokens; aumente `curadoria.max_tokens`", texto)
    dados = interpretar_resposta(texto, dossie.verba_id, raiz)
    return Rascunho(
        dados=dados,
        modelo=resposta.model,
        id_requisicao=getattr(resposta, "_request_id", None),
        tokens_entrada=resposta.usage.input_tokens,
        tokens_saida=resposta.usage.output_tokens,
    )
