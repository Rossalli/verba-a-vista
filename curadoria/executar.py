"""Gera rascunhos para as perdas sem curadoria revisada (spec §7.1 passos 1 a 5, T3.4).

    python -m curadoria                  # plano: quais perdas seriam enviadas, sem chamar a IA (nada é cobrado)
    python -m curadoria --executar       # chama a IA (cobrado) e grava em dados/fila/
    python -m curadoria --id <id> --refazer --executar

Perda que já tem rascunho ou erro em `dados/fila/` não é enviada de novo sem `--refazer`.
"""

import argparse
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from curadoria.dossie import Dossie, montar_dossie
from curadoria.fila import gravar_erro, gravar_fila, na_fila
from curadoria.ia import RAIZ, IAErro, criar_cliente, gerar_rascunho
from curadoria.validacao import permitidos_da_verba, validar_rascunho
from nucleo.config import Config
from nucleo.pipeline import processar


@dataclass
class Resultado:
    na_fila: list[str] = field(default_factory=list)
    com_erro: list[str] = field(default_factory=list)
    sem_documentos: list[str] = field(default_factory=list)
    ja_na_fila: list[str] = field(default_factory=list)
    plano: list[str] = field(default_factory=list)  # só no plano (sem --executar)
    falha_api: str | None = None  # falha de infraestrutura (chave, API, rede): nada foi gravado e a próxima execução tenta de novo
    nao_tentadas: int = 0  # perdas que ficaram sem tentativa porque a falha de infraestrutura interrompeu o laço
    tokens_entrada: int = 0
    tokens_saida: int = 0


def urls_das_fontes(config: Config) -> dict[str, str]:
    fontes = config.fontes.fontes
    return {chave: fontes[chave].url or fontes[chave].base_url for chave in ("transferegov_discricionarias", "cauc", "obrasgov")}


def executar(raiz: Path = RAIZ, data: date | None = None, config: Config | None = None, ids: list[str] | None = None, refazer: bool = False, enviar: bool = False, cliente=None) -> Resultado:
    """`enviar=False` só monta o plano. O `cliente` é injetável (testes)."""
    data = data or date.today()
    proc = processar(raiz, data, config)
    config = proc.config
    verbas = {v.id: v for v in proc.normalizacao.verbas}
    resultado = Resultado()
    urls = urls_das_fontes(config)

    alvo = [i for i in proc.historico.precisam_curadoria if not ids or i in ids]
    for posicao, verba_id in enumerate(alvo):
        if na_fila(raiz, verba_id) and not refazer:
            resultado.ja_na_fila.append(verba_id)
            continue
        verba = verbas[verba_id]
        dossie: Dossie = montar_dossie(verba, proc.retratos, raiz, urls)
        if not dossie.documentos:
            resultado.sem_documentos.append(verba_id)  # sem documento não há o que a IA leia: segue "em apuração"
            continue
        if not enviar:
            resultado.plano.append(f"{verba_id}: {len(dossie.documentos)} documentos")
            continue
        permitidos = permitidos_da_verba(verba, config)
        try:
            cliente = cliente or criar_cliente()
            rascunho = gerar_rascunho(dossie, config, cliente)  # prompt e schema são do repositório, não da pasta de dados
        except IAErro as erro:
            if erro.retentavel:
                # Chave, API ou rede: não diz nada sobre este rascunho. Não grava arquivo (ele bloquearia a nova tentativa)
                # e para, porque as próximas chamadas falhariam do mesmo jeito.
                resultado.falha_api = str(erro)
                resultado.nao_tentadas = sum(1 for restante in alvo[posicao:] if refazer or not na_fila(raiz, restante))
                break
            gravar_erro(raiz, dossie, [str(erro)], None, erro.resposta_bruta, data)
            resultado.com_erro.append(verba_id)
            continue
        resultado.tokens_entrada += rascunho.tokens_entrada
        resultado.tokens_saida += rascunho.tokens_saida
        validacao = validar_rascunho(rascunho.dados, dossie, permitidos, config)
        if validacao.ok:
            gravar_fila(raiz, dossie, rascunho.dados, validacao, permitidos, rascunho.modelo, rascunho.id_requisicao, data)
            resultado.na_fila.append(verba_id)
        else:
            gravar_erro(raiz, dossie, validacao.erros, rascunho.dados, None, data)
            resultado.com_erro.append(verba_id)
    return resultado


def resumo(resultado: Resultado, enviou: bool) -> str:
    linhas = []
    if not enviou:
        linhas.append(f"Plano (nada foi enviado nem cobrado): {len(resultado.plano)} perda(s) iriam para a IA")
        linhas += [f"  - {item}" for item in resultado.plano]
        if resultado.plano:
            linhas.append("Para enviar de verdade: python -m curadoria --executar")
    else:
        linhas.append(f"Rascunhos na fila: {len(resultado.na_fila)}; reprovados ou com erro: {len(resultado.com_erro)}")
        linhas.append(f"Tokens: {resultado.tokens_entrada} de entrada, {resultado.tokens_saida} de saída")
    if resultado.falha_api:
        linhas.append(f"FALHA NA IA (nada foi gravado; tenta de novo na próxima execução; {resultado.nao_tentadas} perda(s) sem tentativa): {resultado.falha_api}")
    if resultado.ja_na_fila:
        linhas.append(f"Já têm rascunho/erro em dados/fila/ (use --refazer para gerar de novo): {len(resultado.ja_na_fila)}")
    if resultado.sem_documentos:
        linhas.append(f"Sem documentos para a IA ler (seguem em apuração): {len(resultado.sem_documentos)}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    import sys

    parser = argparse.ArgumentParser(prog="python -m curadoria", description="Gera rascunhos de motivo de perda para revisão.")
    parser.add_argument("--id", action="append", dest="ids", help="só esta verba (pode repetir)")
    parser.add_argument("--refazer", action="store_true", help="gera de novo mesmo que já haja rascunho ou erro na fila")
    parser.add_argument("--executar", action="store_true", help="chama a IA (cobrado); sem isso só mostra o plano")
    parser.add_argument("--data", type=date.fromisoformat, default=None)
    parser.add_argument("--raiz", type=Path, default=RAIZ)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    resultado = executar(args.raiz, args.data, None, args.ids, args.refazer, args.executar)
    print(resumo(resultado, args.executar))
    if resultado.falha_api and os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Curadoria com IA falhou::{resultado.falha_api}")  # anotação visível no resumo da execução
    return 0  # falha da IA não bloqueia a publicação dos dados do dia


if __name__ == "__main__":
    raise SystemExit(main())
