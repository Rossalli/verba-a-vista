"""Conferência semanal no Acesso Livre do Transferegov (D23): roda NO SEU COMPUTADOR, num Chrome visível.

Uso (uma vez por semana, na pasta do projeto, com o ambiente ativado):

    pip install -e ".[local]"                 # só na primeira vez (instala o Playwright; usa o Chrome que você já tem)
    python scripts/sync_acesso_livre.py

O que faz, como uma pessoa faria, com alguns segundos entre uma página e outra:
1. abre a página do Acesso Livre (gov.br) e o link "Consultar Propostas" (o acesso de visitante que o governo oferece;
   o usuário e a senha ficam só na memória e nunca são impressos nem gravados);
2. consulta as propostas da prefeitura pelo CNPJ e lê todas as páginas da lista (número, situação, órgão, "Possui Parecer");
3. nas propostas com parecer que mudaram desde o lote do Siconv, que o lote não tem ou que o site já mostra como perdidas,
   lê a lista de pareceres e o texto de cada um (sem nome, telefone nem e-mail de servidor);
4. grava `dados/brutos/transferegov_acesso_livre/AAAA-MM-DD.json` (e o log). Depois: git add, commit e push.

Para na hora, sem tentar de novo nem contornar, se aparecer captcha, pedido de login do gov.br ou bloqueio.
Se a estrutura da página mudar, para com uma mensagem dizendo em que passo.
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from coleta import acesso_livre as al
from coleta.base import agora, gravar_retrato, registrar_log
from nucleo.config import carregar_config
from nucleo.normaliza import RAIZ, carregar_retratos

PAGINA = "https://www.gov.br/transferegov/pt-br/sistemas/acesso-livre"
CONSULTA = "https://discricionarias.transferegov.sistema.gov.br/voluntarias/proposta/ConsultarProposta/ConsultarProposta.do"
PAUSA_PADRAO = 3.0

# Lidos na própria página; testados no navegador contra a lista real (241 propostas em 13 páginas).
JS_LINHAS_LISTA = r"""() => {
  const tb = document.getElementById('row'); if (!tb) return null;
  return [...tb.rows].slice(1).map(r => {
    const c = [...r.cells].map(x => x.innerText.trim().replace(/\s+/g, ' '));
    const a = r.cells[0].querySelector('a');
    const m = ((a && a.getAttribute('href')) || '').match(/idProposta=(\d+)/);
    return {numero: c[0], situacao: c[1], orgao: c[2], possui_parecer: c[4], id_proposta: m ? m[1] : null};
  });
}"""
JS_LINHAS_PARECERES = r"""() => {
  const tb = [...document.querySelectorAll('table#row')].find(t => t.rows.length && /Parecer do/.test(t.rows[0].innerText));
  if (!tb) return null;
  return [...tb.rows].slice(1).map(r => {
    const c = [...r.cells].map(x => x.innerText.trim().replace(/\s+/g, ' '));
    const a = r.querySelector('a'); const h = (a && a.getAttribute('href')) || '';
    const m = h.match(/idParecer=(\d+)/);
    return {data: c[0], parecer_do: c[1], atribuicao: c[3], id_parecer: m ? m[1] : null, href: h};
  });
}"""
JS_TEXTO_PARECER = "() => { const t = document.querySelector('textarea[name=parecer]'); return t ? t.value : null; }"


class Barrado(Exception):
    """A página pediu login, captcha ou recusou o acesso: parar, nunca contornar."""


class EstruturaMudou(Exception):
    """A página não tem o que o script espera (o Transferegov mudou?)."""


def onde(page) -> str:
    u = urlsplit(page.url)
    return f"{u.netloc}{u.path} (título: {page.title()!r})"


def conferir_barreira(page) -> None:
    texto = page.inner_text("body")[:4000].lower()
    if "captcha" in texto or "não sou um robô" in texto or "sso.acesso.gov.br" in page.url:
        raise Barrado(f"a página pediu captcha ou login do gov.br: {onde(page)}")


def abrir_consulta(page, pausa: float) -> None:
    page.goto(PAGINA)
    href = page.get_by_role("link", name="Consultar Propostas", exact=True).first.get_attribute("href")
    if not href:
        raise EstruturaMudou("o link 'Consultar Propostas' não está na página do Acesso Livre")
    time.sleep(pausa)
    page.goto(href)  # leva o acesso de visitante; não imprimir
    try:
        page.wait_for_selector("select[name=tipoIdentificacao]", timeout=40_000)
    except Exception as erro:  # noqa: BLE001
        conferir_barreira(page)
        raise Barrado(f"a consulta não abriu em 40 s: {onde(page)}") from erro


def consultar_por_cnpj(page, cnpj: str) -> None:
    page.select_option("select[name=tipoIdentificacao]", "1")  # 1 = CNPJ
    page.fill("input[name=identificacao]", cnpj)
    page.locator("input[type=button][onclick*=CONSULTA_COMPLETA]").last.click()
    try:
        page.wait_for_selector("table#row", timeout=40_000)
    except Exception as erro:  # noqa: BLE001
        conferir_barreira(page)
        raise EstruturaMudou(f"a tabela de propostas não apareceu: {onde(page)}") from erro


def listar_propostas(page, pausa: float) -> tuple[list[dict], dict]:
    """Todas as linhas da lista, página por página."""
    linhas: list[dict] = []
    while True:
        paginacao = al.ler_paginacao(page.inner_text("body"))
        if paginacao is None:
            raise EstruturaMudou(f"sem a linha 'Página X de Y' na lista: {onde(page)}")
        atual, total_paginas, total_itens = paginacao
        bruto = page.evaluate(JS_LINHAS_LISTA)
        if not bruto:
            raise EstruturaMudou(f"a tabela da página {atual} veio vazia: {onde(page)}")
        linhas += [al.linha_da_lista(b) for b in bruto if b["id_proposta"]]
        print(f"   página {atual} de {total_paginas}: {len(bruto)} linhas")
        if atual >= total_paginas:
            break
        time.sleep(pausa)
        alvo = page.locator("a", has_text=re.compile(rf"^{atual + 1}$")).first
        if alvo.count() == 0:
            alvo = page.get_by_role("link", name="Próx").first
        alvo.click()
        page.wait_for_function("n => new RegExp('P[aá]gina ' + n + ' de').test(document.body.innerText)", arg=atual + 1)
    if len(linhas) != total_itens:
        print(f"   AVISO: a lista diz {total_itens} itens e li {len(linhas)}")
    return linhas, {"total_lista": total_itens, "paginas": total_paginas}


def ler_pareceres(page, proposta: dict, maximo: int, pausa: float) -> list[dict]:
    """Abre a proposta pelo número, vai à aba Pareceres e lê o texto de cada parecer (os mais recentes primeiro)."""
    page.goto(CONSULTA)
    page.fill("input[name=numeroProposta]", proposta["numero"].lstrip("0"))
    page.locator("input[type=button][onclick*=CONSULTA_COMPLETA]").first.click()
    page.wait_for_selector("table#row")
    time.sleep(pausa)
    page.locator("#row a", has_text=proposta["numero"]).first.click()
    page.get_by_role("link", name="Pareceres", exact=True).first.click()
    page.wait_for_function("() => [...document.querySelectorAll('table#row')].some(t => t.rows.length && /Parecer do/.test(t.rows[0].innerText))")
    itens = [i for i in (page.evaluate(JS_LINHAS_PARECERES) or []) if i["id_parecer"]][:maximo]
    saida = []
    for item in itens:
        time.sleep(pausa)
        page.goto(urljoin(page.url, item["href"]))  # o link do parecer; fica só na memória
        texto = page.evaluate(JS_TEXTO_PARECER)
        if texto is None:
            raise EstruturaMudou(f"o parecer {item['id_parecer']} não tem o campo de texto: {onde(page)}")
        saida.append(al.parecer_do_retrato(proposta["id_proposta"], {**item, "texto": texto}))
        page.go_back()
        page.wait_for_selector("table#row")
    return saida


def perdidas_publicadas(raiz: Path) -> set[str]:
    caminho = raiz / "dados" / "publicados" / "verbas.json"
    if not caminho.exists():
        return set()
    verbas = json.loads(caminho.read_text(encoding="utf-8"))["verbas"]
    return {v["id_fonte"] for v in verbas if v["fonte"] == "transferegov_discricionarias" and v["status_site"] == "perdida"}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    config = carregar_config()
    parser = argparse.ArgumentParser(prog="python scripts/sync_acesso_livre.py", description="Conferência semanal no Acesso Livre do Transferegov.")
    parser.add_argument("--raiz", type=Path, default=RAIZ)
    parser.add_argument("--cnpj", default=config.regras.municipio.cnpj_prefeitura, help="CNPJ do proponente (padrão: a prefeitura)")
    parser.add_argument("--sem-pareceres", action="store_true", help="só a lista de propostas")
    parser.add_argument("--maximo-pareceres", type=int, default=al.LIMITE_PARECERES_POR_PROPOSTA, help="pareceres lidos por proposta (os mais recentes)")
    parser.add_argument("--pausa", type=float, default=PAUSA_PADRAO, help="segundos entre uma página e outra (mínimo 2)")
    parser.add_argument("--navegador", choices=["chrome", "chromium"], default="chrome", help="chrome usa o que você já tem instalado")
    parser.add_argument("--sem-gravar", action="store_true", help="lê tudo e mostra o resumo, sem gravar o retrato")
    args = parser.parse_args(argv)
    pausa = max(args.pausa, 2.0)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as erro:
        print(f'Não consegui carregar o Playwright: {erro!r}\nPython em uso: {sys.executable} ({sys.version.split()[0]})\nSe ele não estiver instalado nesse Python, rode:  {sys.executable} -m pip install -e ".[local]"')
        return 2

    inicio = time.time()
    hoje = date.today()
    siconv = carregar_retratos(args.raiz, hoje).get("transferegov_discricionarias")
    antes = al.situacoes_do_siconv(siconv)
    perdidas = perdidas_publicadas(args.raiz)
    print(f"Conferência no Acesso Livre ({hoje.strftime('%d/%m/%Y')}); lote do Siconv com {len(antes)} propostas; {len(perdidas)} perdidas no site")
    with sync_playwright() as p:
        try:
            navegador = p.chromium.launch(channel="chrome" if args.navegador == "chrome" else None, headless=False)
        except Exception as erro:  # noqa: BLE001
            print(f"Não consegui abrir o Chrome ({erro}). Instale o Chrome, ou rode `playwright install chromium` e use --navegador chromium.")
            return 2
        page = navegador.new_context(locale="pt-BR").new_page()
        page.set_default_timeout(30_000)
        try:
            print("1) abrindo a consulta de propostas")
            abrir_consulta(page, pausa)
            print(f"2) consultando o CNPJ {args.cnpj}")
            consultar_por_cnpj(page, args.cnpj)
            propostas, meta = listar_propostas(page, pausa)
            pareceres: list[dict] = []
            alvo = [] if args.sem_pareceres else al.propostas_para_pareceres(propostas, antes, perdidas)
            print(f"3) pareceres: {len(alvo)} proposta(s) com parecer para ler: {', '.join(a['numero'] for a in alvo) or 'nenhuma'}")
            for a in alvo:
                lidos = ler_pareceres(page, a, args.maximo_pareceres, pausa)
                print(f"   {a['numero']}: {len(lidos)} parecer(es)")
                pareceres += lidos
        except Barrado as erro:
            print(f"\nPAROU, barrado: {erro}\nNada foi gravado. Não tente contornar; avise o projeto (docs/fontes.md, Acesso Livre).")
            return 1
        except EstruturaMudou as erro:
            print(f"\nPAROU, a página não é a esperada: {erro}\nNada foi gravado. Avise o projeto com esta mensagem.")
            return 2
        finally:
            navegador.close()

    novas = [p for p in propostas if p["id_proposta"] not in antes]
    mudaram = [p for p in propostas if p["id_proposta"] in antes and antes[p["id_proposta"]].strip().casefold() != p["situacao"].strip().casefold()]
    print(f"\nResumo: {len(propostas)} propostas; {len(mudaram)} mudaram de situação desde o lote do Siconv; {len(novas)} que o lote não tem; {len(pareceres)} pareceres")
    for p in mudaram:
        print(f"   mudou: {p['numero']}  {antes[p['id_proposta']]}  ->  {p['situacao']}")
    for p in novas:
        print(f"   nova:  {p['numero']}  {p['situacao']}")
    if args.sem_gravar:
        print("(--sem-gravar: nada foi gravado)")
        return 0
    momento = agora(config)
    retrato = al.montar_retrato(propostas, pareceres, momento, {"cnpj": args.cnpj, **meta, "ferramenta": "playwright", "navegador": args.navegador})
    try:
        caminho = gravar_retrato(args.raiz, retrato)
    except FileExistsError as erro:
        print(f"\n{erro}\nJá há uma conferência de hoje. Rode de novo amanhã.")
        return 1
    registrar_log(args.raiz, al.FONTE, retrato.data, {"origem": al.ORIGEM, "inicio": momento.isoformat(timespec="seconds"), "duracao_s": round(time.time() - inicio, 1), "contagens": retrato.contagens(), "mudaram": len(mudaram), "novas": len(novas)})
    print(f"\nGravado: {caminho}\nPróximo passo:  git add dados/brutos/transferegov_acesso_livre && git commit -m \"conferência no Acesso Livre\" && git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
