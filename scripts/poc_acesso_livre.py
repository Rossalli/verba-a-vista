"""POC Acesso Livre do Transferegov (Discricionárias e Legais): consulta de proposta por número, sem navegador.

Uso:
    python scripts/poc_acesso_livre.py

O que faz (4 requisições, com pausa de 1 s):
- lê a página oficial do Acesso Livre (gov.br) e acha o link "Consultar Propostas", que traz o usuário de visitante
  publicado pelo próprio governo (o script NUNCA imprime nem grava esse usuário e essa senha);
- abre o link no módulo e segue o login único (SAML) até a tela de consulta;
- imprime cada salto (código, host e caminho) e diz se chegou à consulta ou foi barrado.

Resultado em 05/11/2026: o módulo responde 200 com um formulário SAML de envio automático; o envio ao provedor de
identidade (`idp.transferegov.sistema.gov.br`) volta com **HTTP 401** ("Login do Transferegov", que redireciona ao
login do gov.br). No navegador, com JavaScript, o mesmo link de visitante abre a consulta. A causa do 401 não foi
investigada: o script se identifica como o projeto, **não imita navegador** e não tenta contornar a resposta
(docs/fontes.md).
"""

import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

PAGINA = "https://www.gov.br/transferegov/pt-br/sistemas/acesso-livre"
UA = "verba-a-vista/poc (+https://github.com/Rossalli/verba-a-vista)"
PAUSA = 1.0


class Links(HTMLParser):
    """Pares (texto, href) dos links da página."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._texto = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._texto.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append(("".join(self._texto).strip(), self._href))
            self._href = None


class Formularios(HTMLParser):
    """Formulários da página: ação, método e campos nomeados (nomes de atributo em minúsculas: o HTML usa HIDDEN)."""

    def __init__(self) -> None:
        super().__init__()
        self.formularios: list[dict] = []
        self._atual: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): v for k, v in attrs}
        if tag == "form":
            self._atual = {"acao": a.get("action"), "metodo": (a.get("method") or "get").lower(), "campos": {}}
            self.formularios.append(self._atual)
        elif self._atual is not None and tag in ("input", "select", "textarea") and a.get("name"):
            self._atual["campos"][a["name"]] = a.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "form":
            self._atual = None


def link_de_visitante(html: str, texto: str = "Consultar Propostas") -> str | None:
    """href do link com esse texto (contém o usuário de visitante: não imprimir)."""
    p = Links()
    p.feed(html)
    return next((h for t, h in p.links if t == texto), None)


def sem_credenciais(url: str) -> str:
    """`host/caminho` e os NOMES dos parâmetros, para imprimir sem expor usuário e senha."""
    u = urlsplit(url)
    nomes = sorted(par.split("=")[0] for par in u.query.split("&") if par)
    return f"{u.netloc}{u.path}" + (f" (parâmetros: {', '.join(nomes)})" if nomes else "")


def salto(r: httpx.Response) -> str:
    u = urlsplit(str(r.url))
    return f"HTTP {r.status_code} {u.netloc}{u.path}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=40) as c:
        r = c.get(PAGINA)
        print(f"1) página do Acesso Livre: {salto(r)}")
        href = link_de_visitante(r.text)
        if not href:
            print("   link 'Consultar Propostas' não encontrado: a página mudou")
            return 2
        print(f"   link: {sem_credenciais(href)}")
        time.sleep(PAUSA)
        r = c.get(href)
        print(f"2) abrir o link no módulo: {salto(r)}")
        f = Formularios()
        f.feed(r.text)
        saml = next((x for x in f.formularios if "SAMLRequest" in x["campos"]), None)
        if saml is None:
            print("   chegou direto à consulta" if "Consultar Proposta" in r.text else "   resposta inesperada (sem formulário SAML)")
            return 0 if "Consultar Proposta" in r.text else 2
        print(f"   formulário SAML de envio automático para {sem_credenciais(saml['acao'])}; campos: {sorted(saml['campos'])}")
        time.sleep(PAUSA)
        r = c.post(saml["acao"], data=saml["campos"])
        print(f"3) envio ao provedor de identidade: {salto(r)}")
        titulo = re.search(r"<title>([^<]*)</title>", r.text, re.I)
        print(f"   título da página: {titulo.group(1).strip() if titulo else '(sem título)'}")
        if r.status_code == 200 and "Consultar Proposta" in r.text:
            print("   chegou à consulta")
            return 0
        print("   BARRADO: o provedor de identidade respondeu 401 ao envio feito sem navegador (a consulta abre no navegador, com JavaScript).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
