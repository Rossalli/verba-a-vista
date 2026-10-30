"""Fila de revisão em arquivos (spec §7.1 passos 4 a 6, T3.4).

- `dados/fila/<id>.yaml`: rascunho aprovado na validação, esperando a revisão de uma pessoa. A pessoa edita `rascunho`
  à mão; os `documentos` vão no arquivo para ela poder conferir as citações sem sair dele.
- `dados/fila/<id>.erro.yaml`: rascunho reprovado (ou resposta inutilizável) com a lista de erros. Não é publicado.

Nada de `dados/fila/` chega ao site: só `dados/curadoria/` (ver `aprovar.py`).
"""

from datetime import date
from pathlib import Path

import yaml

from curadoria.dossie import Documento, Dossie
from curadoria.validacao import Validacao


class _Dumper(yaml.SafeDumper):
    pass


def _texto(dumper: yaml.SafeDumper, valor: str):
    # Texto de várias linhas em bloco (`|`): o revisor lê e edita o documento como ele é.
    return dumper.represent_scalar("tag:yaml.org,2002:str", valor, style="|" if "\n" in valor else None)


_Dumper.add_representer(str, _texto)


def _pasta(raiz: Path) -> Path:
    return raiz / "dados" / "fila"


def caminho_fila(raiz: Path, verba_id: str) -> Path:
    return _pasta(raiz) / f"{verba_id}.yaml"


def caminho_erro(raiz: Path, verba_id: str) -> Path:
    return _pasta(raiz) / f"{verba_id}.erro.yaml"


def _gravar(caminho: Path, dados: dict) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = yaml.dump(dados, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=100)
    caminho.write_text(texto, encoding="utf-8", newline="\n")
    return caminho


def _documentos(dossie: Dossie) -> list[dict]:
    return [{"id": d.id, "titulo": d.titulo, "url": d.url, "data_coleta": d.data_coleta, "texto": d.texto} for d in dossie.documentos]


def _limpar(caminho: Path) -> None:
    caminho.unlink(missing_ok=True)  # rascunho antigo da outra pasta: o resultado novo o substitui


def gravar_fila(raiz: Path, dossie: Dossie, rascunho: dict, validacao: Validacao, permitidos: list[str], modelo: str, id_requisicao: str | None, hoje: date) -> Path:
    _limpar(caminho_erro(raiz, dossie.verba_id))
    return _gravar(
        caminho_fila(raiz, dossie.verba_id),
        {
            "verba_id": dossie.verba_id,
            "gerado_em": hoje.isoformat(),
            "modelo": modelo,
            "id_requisicao": id_requisicao,
            "avisos": validacao.avisos,
            "permitidos": permitidos,
            "rascunho": rascunho,
            "documentos": _documentos(dossie),
        },
    )


def gravar_erro(raiz: Path, dossie: Dossie, erros: list[str], rascunho: dict | None, resposta_bruta: str | None, hoje: date) -> Path:
    _limpar(caminho_fila(raiz, dossie.verba_id))
    return _gravar(
        caminho_erro(raiz, dossie.verba_id),
        {"verba_id": dossie.verba_id, "gerado_em": hoje.isoformat(), "erros": erros, "rascunho": rascunho, "resposta_bruta": resposta_bruta},
    )


def carregar_fila(raiz: Path, verba_id: str) -> dict | None:
    caminho = caminho_fila(raiz, verba_id)
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def dossie_da_fila(fila: dict) -> Dossie:
    return Dossie(fila["verba_id"], [Documento(**d) for d in fila["documentos"]])


def na_fila(raiz: Path, verba_id: str) -> bool:
    """Já há rascunho (ou erro) para a verba: não gerar de novo, e não pagar outra chamada, sem `--refazer`."""
    return caminho_fila(raiz, verba_id).exists() or caminho_erro(raiz, verba_id).exists()
