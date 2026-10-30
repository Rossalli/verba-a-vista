"""Curadoria revisada por pessoa (spec §7.1 passos 6 e 7): `dados/curadoria/<id>.yaml`.

É a única fonte do motivo de perda publicado. Rascunho da IA em `dados/fila/` nunca chega aqui sem revisão.
"""

from datetime import date
from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from nucleo.modelo import Categoria, Citacao, Evitavel, Perda, _Base


class CuradoriaErro(Exception):
    """Arquivo de curadoria ilegível ou inválido: o pipeline para em vez de publicar a perda como se não houvesse revisão."""


class CuradoriaRevisada(_Base):
    verba_id: str
    categoria: Categoria
    texto: str = Field(min_length=1, max_length=700)
    evitavel: Evitavel
    citacoes: list[Citacao]
    gerado_por_ia: bool
    revisado_por: str = Field(min_length=1)
    revisado_em: date


def caminho_curadoria(raiz: Path, verba_id: str) -> Path:
    return raiz / "dados" / "curadoria" / f"{verba_id}.yaml"


def carregar_curadoria(raiz: Path, verba_id: str) -> CuradoriaRevisada | None:
    """Curadoria revisada da verba, ou None se não houver arquivo."""
    caminho = caminho_curadoria(raiz, verba_id)
    if not caminho.exists():
        return None
    try:
        curadoria = CuradoriaRevisada.model_validate(yaml.safe_load(caminho.read_text(encoding="utf-8")))
    except (yaml.YAMLError, ValidationError) as erro:
        raise CuradoriaErro(f"{caminho}: {erro}") from erro
    if curadoria.verba_id != verba_id:
        raise CuradoriaErro(f"{caminho}: `verba_id` é {curadoria.verba_id}, esperado {verba_id}")
    if curadoria.categoria != "em_apuracao" and not curadoria.citacoes:
        raise CuradoriaErro(f"{caminho}: motivo de perda sem citação de documento só pode ser `em_apuracao` (regra inegociável)")
    return curadoria


def aplicar_curadoria(perda: Perda, curadoria: CuradoriaRevisada) -> Perda:
    """`perda` com o motivo revisado; `data` e `valor_perdido` continuam os do pipeline."""
    return perda.model_copy(
        update={
            "categoria": curadoria.categoria,
            "texto": curadoria.texto,
            "citacoes": list(curadoria.citacoes),
            "evitavel": curadoria.evitavel,
            "gerado_por_ia": curadoria.gerado_por_ia,
            "revisado_por": curadoria.revisado_por,
            "revisado_em": curadoria.revisado_em,
        }
    )
