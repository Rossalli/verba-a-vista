"""Aprovação de um rascunho da fila (spec §7.1 passo 6, T3.4).

    python -m curadoria.aprovar <id-da-verba> --por "<nome de quem revisou>"

Confere de novo o rascunho (a pessoa pode tê-lo editado), grava `dados/curadoria/<id>.yaml` com `revisado_por` e
`revisado_em` e tira o rascunho da fila. Só esse arquivo chega ao site.
"""

import argparse
from datetime import date
from pathlib import Path

import yaml

from curadoria.fila import caminho_fila, carregar_fila, dossie_da_fila
from curadoria.ia import RAIZ
from curadoria.validacao import validar_rascunho
from nucleo.config import Config, carregar_config
from nucleo.curadoria_revisada import CuradoriaRevisada, caminho_curadoria
from nucleo.modelo import Citacao


class AprovacaoErro(Exception):
    pass


def aprovar(raiz: Path, verba_id: str, por: str, hoje: date | None = None, config: Config | None = None) -> tuple[Path, list[str]]:
    """Grava a curadoria revisada. Devolve o caminho e os avisos da validação; levanta `AprovacaoErro` se não puder aprovar."""
    config = config or carregar_config()
    hoje = hoje or date.today()
    if not por.strip():
        raise AprovacaoErro("diga quem revisou: --por \"<nome>\"")
    fila = carregar_fila(raiz, verba_id)
    if fila is None:
        raise AprovacaoErro(f"não há rascunho na fila para {verba_id} ({caminho_fila(raiz, verba_id)})")
    destino = caminho_curadoria(raiz, verba_id)
    if destino.exists():
        raise AprovacaoErro(f"{destino} já existe; para mudar uma curadoria já aprovada, edite esse arquivo")

    rascunho, dossie = fila["rascunho"], dossie_da_fila(fila)
    if rascunho.get("categoria") == "em_apuracao":
        raise AprovacaoErro("rascunho em_apuracao não tem o que publicar: a perda já aparece como \"motivo em apuração\". Apague o arquivo da fila ou mude a categoria.")
    validacao = validar_rascunho(rascunho, dossie, fila.get("permitidos"), config)
    if not validacao.ok:
        raise AprovacaoErro("o rascunho não passa na validação:\n- " + "\n- ".join(validacao.erros))

    citacoes = []
    for c in rascunho["citacoes"]:
        documento = dossie.por_id(c["documento_id"])
        citacoes.append(Citacao(n=c["n"], documento_id=documento.id, titulo=documento.titulo, url=documento.url, trecho=c["trecho"]))
    curadoria = CuradoriaRevisada(
        verba_id=verba_id,
        categoria=rascunho["categoria"],
        texto=rascunho["texto"],
        evitavel=rascunho["evitavel"],
        citacoes=citacoes,
        gerado_por_ia=True,  # o texto parte do rascunho da IA, mesmo editado: o selo continua valendo
        revisado_por=por.strip(),
        revisado_em=hoje,
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    corpo = yaml.safe_dump(curadoria.model_dump(mode="json"), allow_unicode=True, sort_keys=False, width=100)
    destino.write_text(corpo, encoding="utf-8", newline="\n")
    caminho_fila(raiz, verba_id).unlink()
    return destino, validacao.avisos


def main(argv: list[str] | None = None) -> int:
    import sys

    parser = argparse.ArgumentParser(prog="python -m curadoria.aprovar", description="Aprova um rascunho da fila de curadoria.")
    parser.add_argument("verba_id")
    parser.add_argument("--por", required=True, help="nome de quem revisou")
    parser.add_argument("--raiz", type=Path, default=RAIZ)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        destino, avisos = aprovar(args.raiz, args.verba_id, args.por)
    except AprovacaoErro as erro:
        print(f"Não aprovado: {erro}")
        return 1
    for aviso in avisos:
        print(f"Aviso: {aviso}")
    print(f"Aprovado: {destino}. Rode `make normaliza` para publicar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
