"""Pipeline sobre os retratos brutos (spec §9): normaliza -> risco (T2.3) -> perda e histórico (T2.4) -> publica (T2.5).

Cada tarefa acrescenta um passo aqui. Por ora: `python -m nucleo.pipeline` (alvo `make normaliza`) normaliza,
aplica as regras de risco e imprime o resumo; não grava nada (a publicação vem na T2.5).
"""

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from nucleo.config import Config, carregar_config
from nucleo.normaliza import RAIZ, Normalizacao, carregar_retratos, normalizar, resumo_normalizacao
from nucleo.risco import ORDEM, ResultadoRisco, aplicar_risco


@dataclass
class Processamento:
    normalizacao: Normalizacao
    risco: ResultadoRisco


def processar(raiz: Path = RAIZ, data: date | None = None, config: Config | None = None) -> Processamento:
    config = config or carregar_config()
    data = data or date.today()
    retratos = carregar_retratos(raiz, data)
    normalizacao = normalizar(retratos, config, data)
    risco = aplicar_risco(normalizacao, retratos, config, data)
    return Processamento(normalizacao, risco)


def resumo_risco(processamento: Processamento) -> str:
    risco = processamento.risco
    linhas = [f"Em risco: {risco.verbas_em_risco} verba(s); motivos: " + (", ".join(f"{c}={risco.por_codigo[c]}" for c in ORDEM if risco.por_codigo[c]) or "nenhum")]
    for verba in processamento.normalizacao.verbas:
        if verba.em_risco:
            linhas.append(f"  - {verba.id} ({verba.status_site}): " + "; ".join(m.texto for m in verba.motivos_risco))
    linhas += [f"AVISO: {aviso}" for aviso in risco.avisos]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    import sys

    parser = argparse.ArgumentParser(prog="python -m nucleo.pipeline", description="Normaliza os retratos mais recentes e aplica as regras de risco.")
    parser.add_argument("--data", type=date.fromisoformat, default=None, help="data de referência, AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--raiz", type=Path, default=RAIZ, help="raiz com dados/brutos (padrão: o repositório)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    processamento = processar(args.raiz, args.data)
    print(resumo_normalizacao(processamento.normalizacao))
    print(resumo_risco(processamento))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
