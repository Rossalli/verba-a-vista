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


def carregar_curadoria(raiz: Path, verba_id: str, texto_em_apuracao: str) -> CuradoriaRevisada | None:
    """Curadoria revisada da verba, ou None se não houver arquivo.

    `texto_em_apuracao` é o texto padrão de `config/regras.yaml`: a única coisa que uma curadoria `em_apuracao`
    (sem documento) pode dizer.
    """
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
    if curadoria.categoria == "em_apuracao" and (curadoria.citacoes or curadoria.texto != texto_em_apuracao or curadoria.evitavel != "indeterminado"):
        # Sem documento não há texto livre: `em_apuracao` só publica o texto padrão, sem citações e com `evitavel: indeterminado`.
        raise CuradoriaErro(f"{caminho}: `em_apuracao` só pode ter o texto padrão, `evitavel: indeterminado` e nenhuma citação (regra inegociável)")
    return curadoria


def perda_sem_motivo(perda: Perda, texto_em_apuracao: str) -> Perda:
    """A mesma perda (data e valor ficam como na detecção), sem motivo: volta ao texto padrão em apuração.

    É o ponto de partida de toda execução: o motivo publicado vem só de `dados/curadoria/`, nunca do publicado anterior.
    """
    # Construída do zero (como a perda nova do histórico): `model_copy(update=...)` marcaria `revisado_*` como
    # definidos e a exportação passaria a trazer `null` onde a execução anterior omitia o campo.
    return Perda(
        categoria="em_apuracao",
        texto=texto_em_apuracao,
        citacoes=[],
        evitavel="indeterminado",
        data=perda.data,
        valor_perdido=perda.valor_perdido,
        gerado_por_ia=False,
    )


def aplicar_curadoria(perda: Perda, curadoria: CuradoriaRevisada) -> Perda:
    """`perda` com o motivo revisado; `data` e `valor_perdido` continuam os do pipeline.

    Revalida a `Perda` resultante (motivo só com citação e revisão), em vez de confiar na cópia.
    """
    return Perda.model_validate(
        {
            **perda.model_dump(),
            "categoria": curadoria.categoria,
            "texto": curadoria.texto,
            "citacoes": [c.model_dump() for c in curadoria.citacoes],
            "evitavel": curadoria.evitavel,
            "gerado_por_ia": curadoria.gerado_por_ia,
            "revisado_por": curadoria.revisado_por,
            "revisado_em": curadoria.revisado_em,
        }
    )
