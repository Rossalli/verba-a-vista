"""Linha de comando da coleta: `python -m coleta` (alvo `make coleta`).

    python -m coleta                          # todas as fontes, data de hoje (America/Sao_Paulo)
    python -m coleta --fonte cauc --fonte obrasgov
    python -m coleta --data 2026-10-29 --forcar
    python -m coleta --cache D:\\siconv        # onde guardar os zips do Siconv (padrão: .cache/siconv)
    python -m coleta --destino C:\\teste       # grava em <destino>/dados/brutos em vez do repositório

Código de saída: 0 se todas as fontes deram certo (ou foram reaproveitadas do dia); 1 se alguma falhou.
As que deram certo já estão gravadas; a que falhou mantém o último retrato válido (spec §9).
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from coleta.base import FONTES, RAIZ, carregar_dotenv, executar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m coleta", description="Coleta os dados brutos das fontes federais do município.")
    parser.add_argument("--fonte", action="append", choices=sorted(FONTES), help="fonte a coletar (repetível; padrão: todas)")
    parser.add_argument("--data", type=date.fromisoformat, help="data do retrato, AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--forcar", action="store_true", help="coleta de novo mesmo com retrato do dia (não sobrescreve; só registra no log)")
    parser.add_argument("--cache", type=Path, help="pasta dos zips do Siconv (fora do Git)")
    parser.add_argument("--destino", type=Path, default=RAIZ, help="raiz onde gravar dados/brutos (padrão: o repositório)")
    args = parser.parse_args(argv)

    carregar_dotenv()
    opcoes = {"cache": args.cache} if args.cache else {}
    resultados = executar(args.fonte, args.data, raiz=args.destino, forcar=args.forcar, **opcoes)

    print(f"{'fonte':<30} {'situação':<14} {'registros':>9} {'requisições':>11} {'segundos':>8}")
    for r in resultados:
        print(f"{r.fonte:<30} {r.status:<14} {sum(r.registros.values()):>9} {r.requisicoes:>11} {r.duracao_s:>8.1f}")
        if r.erro:
            print(f"    {'ERRO' if r.status == 'erro' else 'aviso'}: {r.erro}")
        if r.caminho:
            print(f"    {r.caminho}")
    falhas = [r.fonte for r in resultados if r.status == "erro"]
    if falhas:
        print(f"\nFalharam: {', '.join(falhas)}. As demais foram gravadas.", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
