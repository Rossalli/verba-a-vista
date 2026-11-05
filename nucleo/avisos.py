"""Avisos do dia para quem revisa (T5.1): o que precisa de olhos humanos depois da coleta.

    python -m nucleo.avisos --fila-novos fila_novos.txt --abrir-issues

Escreve em JSON uma lista de avisos `{chave, titulo, corpo, comentar}`; com `--abrir-issues`, abre uma issue por aviso.
Cada aviso tem um título fixo: se já existe issue aberta com ele, não se abre outra (`comentar: true` só nos
rascunhos novos, que entram como comentário na issue aberta). Assim a fila pendente não gera uma issue por dia.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from nucleo.config import carregar_config
from nucleo.normaliza import RAIZ, SituacaoNaoMapeada
from nucleo.pipeline import processar

TITULO_FILA = "Rascunhos de curadoria para revisar"
TITULO_NAO_MAPEADAS = "Situações de fonte sem mapeamento"
TITULO_FONTES = "Fonte sem retrato de hoje"
TITULO_ACESSO_LIVRE = "Conferência no Acesso Livre atrasada"
FONTE_ACESSO_LIVRE = "transferegov_acesso_livre"


@dataclass
class Aviso:
    chave: str
    titulo: str
    corpo: str
    comentar: bool = False  # com issue já aberta, acrescenta um comentário em vez de ficar quieto


def ids_da_fila(raiz: Path) -> tuple[list[str], list[str]]:
    """(rascunhos aguardando revisão, rascunhos reprovados na validação) em `dados/fila/`."""
    pasta = raiz / "dados" / "fila"
    arquivos = sorted(pasta.glob("*.yaml")) if pasta.exists() else []
    erros = [a.name.removesuffix(".erro.yaml") for a in arquivos if a.name.endswith(".erro.yaml")]
    pendentes = [a.stem for a in arquivos if not a.name.endswith(".erro.yaml")]
    return pendentes, erros


def ids_novos(linhas: list[str]) -> set[str]:
    """Ids dos arquivos de `dados/fila/` listados por `git status --porcelain` (novos ou alterados nesta execução)."""
    novos = set()
    for linha in linhas:
        nome = Path(linha.strip().split(maxsplit=1)[-1]).name if linha.strip() else ""
        if nome.endswith(".yaml"):
            novos.add(nome.removesuffix(".erro.yaml").removesuffix(".yaml"))
    return novos


def aviso_fila(pendentes: list[str], erros: list[str], novos: set[str]) -> Aviso | None:
    if not (novos & (set(pendentes) | set(erros))):
        return None
    linhas = ["A coleta de hoje gerou rascunhos de motivo de perda. **Nada é publicado até uma pessoa revisar.**", ""]
    if pendentes:
        linhas.append("### Aguardando revisão (`dados/fila/<id>.yaml`)")
        linhas += [f"- `{i}`{' (novo)' if i in novos else ''}" for i in pendentes]
        linhas += ["", "Para cada um: leia os documentos no próprio arquivo, edite o `rascunho` se precisar e aprove com:", "", "```", 'python -m curadoria.aprovar <id> --por "<seu nome>"', "```", "", "Depois faça commit do arquivo criado em `dados/curadoria/`; o site é republicado sozinho."]
    if erros:
        linhas += ["", "### Reprovados na validação de citações (`dados/fila/<id>.erro.yaml`)", "Continuam como \"motivo em apuração\" no site. Veja os erros no arquivo; para tentar de novo, apague o arquivo ou rode `python -m curadoria --id <id> --refazer --executar`."]
        linhas += [f"- `{i}`{' (novo)' if i in novos else ''}" for i in erros]
    return Aviso("fila", TITULO_FILA, "\n".join(linhas), comentar=True)


def aviso_nao_mapeadas(nao_mapeadas: list[SituacaoNaoMapeada]) -> Aviso | None:
    if not nao_mapeadas:
        return None
    linhas = [
        "Estas situações apareceram nas fontes e ainda não estão em `config/status_map.yaml`. As verbas saem com o selo \"situação em análise\" (nunca com um status chutado).",
        "",
        "| Fonte | Campo | Situação | Verbas |",
        "| --- | --- | --- | --- |",
    ]
    linhas += [f"| `{s.fonte}` | `{s.campo}` | {s.valor} | {len(s.verbas)} |" for s in nao_mapeadas]
    linhas += ["", "Decida o status do site de cada uma e acrescente em `config/status_map.yaml` (e em `docs/fontes.md`, com a fonte da definição)."]
    return Aviso("nao_mapeadas", TITULO_NAO_MAPEADAS, "\n".join(linhas))


def aviso_acesso_livre(fontes: dict[str, dict], hoje: date, dias_alerta: int) -> Aviso | None:
    """D23: a conferência semanal depende de uma pessoa; sem retrato recente, avisa em vez de deixar o site envelhecer calado."""
    f = fontes.get(FONTE_ACESSO_LIVRE)
    if f is None:
        return None
    dias = (hoje - date.fromisoformat(f["retrato"])).days if f.get("retrato") else None
    if dias is not None and dias <= dias_alerta:
        return None
    ultima = f"A última foi em {date.fromisoformat(f['retrato']).strftime('%d/%m/%Y')} ({dias} dias)." if dias is not None else "Ainda não houve nenhuma."
    corpo = f"A conferência no Acesso Livre do Transferegov está atrasada (alerta a partir de {dias_alerta} dias). {ultima}\n\nEnquanto isso, as propostas sem convênio podem estar com a situação desatualizada no site. Para fazer: `python scripts/sync_acesso_livre.py`, depois commit e push de `dados/brutos/transferegov_acesso_livre/` (veja `docs/operacao.md`)."
    return Aviso("acesso_livre", TITULO_ACESSO_LIVRE, corpo)


def aviso_fontes(fontes: dict[str, dict], hoje: date) -> Aviso | None:
    problemas = {c: f for c, f in fontes.items() if f.get("situacao") not in ("ok", "manual") and c != FONTE_ACESSO_LIVRE}
    if not problemas:
        return None
    linhas = [f"Em {hoje.strftime('%d/%m/%Y')} estas fontes não tinham retrato do dia. O site mostra o último retrato válido de cada uma, com a data:", "", "| Fonte | Situação | Último retrato | Data do dado |", "| --- | --- | --- | --- |"]
    for chave, f in problemas.items():
        linhas.append(f"| {f.get('nome', chave)} | {f.get('situacao')} | {f.get('retrato') or '—'} | {f.get('data_do_dado') or '—'} |")
    linhas += ["", "Veja o log do dia em `dados/brutos/<fonte>/<data>.log.json` e o log da execução no GitHub Actions."]
    return Aviso("fontes", TITULO_FONTES, "\n".join(linhas))


def montar_avisos(*, nao_mapeadas: list[SituacaoNaoMapeada], fila_pendente: list[str], fila_erros: list[str], fila_novos: set[str], fontes: dict[str, dict], hoje: date, dias_acesso_livre: int = 8) -> list[Aviso]:
    candidatos = [aviso_fila(fila_pendente, fila_erros, fila_novos), aviso_nao_mapeadas(nao_mapeadas), aviso_fontes(fontes, hoje), aviso_acesso_livre(fontes, hoje, dias_acesso_livre)]
    return [a for a in candidatos if a is not None]


def abrir_issues(avisos: list[Aviso], executar=subprocess.run) -> list[str]:
    """Abre uma issue por aviso com `gh`, sem duplicar: título igual a uma issue aberta não abre outra.

    Com issue aberta, só os avisos com `comentar` viram comentário nela. `executar` é injetável (testes).
    Devolve uma linha de log por aviso.
    """
    log = []
    for aviso in avisos:
        busca = executar(["gh", "issue", "list", "--state", "open", "--search", f'"{aviso.titulo}" in:title', "--json", "number,title"], capture_output=True, text=True, check=True)
        abertas = [i["number"] for i in json.loads(busca.stdout or "[]") if i["title"] == aviso.titulo]
        if not abertas:
            executar(["gh", "issue", "create", "--title", aviso.titulo, "--body", aviso.corpo], check=True)
            log.append(f"issue criada: {aviso.titulo}")
        elif aviso.comentar:
            executar(["gh", "issue", "comment", str(abertas[0]), "--body", aviso.corpo], check=True)
            log.append(f"comentário na issue #{abertas[0]}: {aviso.titulo}")
        else:
            log.append(f"issue #{abertas[0]} já aberta, nada a fazer: {aviso.titulo}")
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nucleo.avisos", description="Lista, em JSON, o que precisa de revisão humana depois da coleta.")
    parser.add_argument("--raiz", type=Path, default=RAIZ)
    parser.add_argument("--data", type=date.fromisoformat, default=None, help="data de referência (padrão: hoje)")
    parser.add_argument("--fila-novos", type=Path, default=None, help="arquivo com a saída de `git status --porcelain -uall dados/fila`")
    parser.add_argument("--abrir-issues", action="store_true", help="abre as issues com `gh` (precisa de GH_TOKEN); o JSON continua saindo na tela")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    hoje = args.data or date.today()
    processamento = processar(args.raiz, hoje)
    publicado = json.loads((args.raiz / "dados" / "publicados" / "verbas.json").read_text(encoding="utf-8"))
    pendentes, erros = ids_da_fila(args.raiz)
    novos = ids_novos(args.fila_novos.read_text(encoding="utf-8").splitlines()) if args.fila_novos and args.fila_novos.exists() else set()
    avisos = montar_avisos(
        nao_mapeadas=processamento.normalizacao.nao_mapeadas,
        fila_pendente=pendentes,
        fila_erros=erros,
        fila_novos=novos,
        fontes=publicado["fontes"],
        hoje=hoje,
        dias_acesso_livre=carregar_config().regras.coleta.acesso_livre_dias_alerta,
    )
    print(json.dumps([asdict(a) for a in avisos], ensure_ascii=False, indent=1))
    if args.abrir_issues:
        for linha in abrir_issues(avisos):
            print(linha, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
