"""T1.4 POC da API do Portal da Transparência (CGU): convênios, emendas e pagamentos do município.

Uso:
    python scripts/poc_portal_transparencia.py [--sem-fixtures]

A chave vem da variável de ambiente PORTAL_TRANSPARENCIA_KEY; se não existir, o script lê a linha
correspondente do `.env` na raiz do projeto. O valor da chave nunca é impresso nem gravado.

Cuidados com o limite (400 requisições/min; acima disso a chave é suspensa por 8 h):
- intervalo mínimo entre requisições calculado de config/regras.yaml (portal_transparencia_req_por_min);
- teto de requisições por execução (MAX_REQUISICOES);
- 401, 403 e 429 interrompem a execução na hora, sem nova tentativa.

O que faz:
- valida os nomes de parâmetro contra o OpenAPI oficial (/v3/api-docs, sem chave);
- /convenios filtrado por codigoIBGE, paginado até a página vazia, comparado com o Siconv em lote;
- /emendas: mostra que a emenda vem agregada ("MÚLTIPLO"), buscando as emendas indicadas ao município;
- /despesas/recursos-recebidos por codigoIBGE e /despesas/documentos-por-favorecido por CNPJ;
- grava amostras em tests/fixtures/portal_transparencia/ (máx. 50 registros).
"""

import argparse
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from nucleo.config import carregar_config

RAIZ = Path(__file__).resolve().parents[1]
BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
OPENAPI = "https://api.portaldatransparencia.gov.br/v3/api-docs"
FIXTURES = RAIZ / "tests" / "fixtures" / "portal_transparencia"
MAX_AMOSTRA = 50
MAX_REQUISICOES = 400
MAX_PAGINAS = 40  # trava de segurança por consulta paginada


class PortalErro(Exception):
    """Parada segura: acesso negado ou limite excedido. Nunca repetir a chamada."""


def ler_chave() -> str:
    chave = os.environ.get("PORTAL_TRANSPARENCIA_KEY")
    if not chave:
        env = RAIZ / ".env"
        if env.exists():
            for linha in env.read_text(encoding="utf-8").splitlines():
                if linha.startswith("PORTAL_TRANSPARENCIA_KEY="):
                    chave = linha.split("=", 1)[1].strip().strip('"').strip("'")
    if not chave:
        raise PortalErro("PORTAL_TRANSPARENCIA_KEY não definida (variável de ambiente ou .env)")
    return chave


def centavos(texto: str | None) -> int | None:
    """'1.234,56' (formato brasileiro, como a API devolve) -> centavos inteiros. Vazio -> None.

    Estornos vêm com sinal e espaço (`- 7.174,10`); qualquer outro formato levanta InvalidOperation.
    """
    if texto is None or texto.strip() == "":
        return None
    texto = texto.strip()
    negativo = texto.startswith("-")
    numero = Decimal(texto.removeprefix("-").strip().replace(".", "").replace(",", ".")) * 100
    valor = int(numero.to_integral_value())
    return -valor if negativo else valor


def normalizar_numero(numero: str) -> str:
    """Número de proposta/convênio sem zeros à esquerda: o Portal diz `04431/2016`, o Siconv `4431/2016`."""
    antes, barra, depois = numero.partition("/")
    return f"{antes.lstrip('0')}{barra}{depois}"


class Cliente:
    def __init__(self, chave: str, req_por_min: int) -> None:
        self.http = httpx.Client(timeout=90, headers={"chave-api-dados": chave, "Accept": "application/json", "User-Agent": "verba-a-vista/0.1"})
        self.intervalo = 60.0 / req_por_min
        self.requisicoes = 0
        self._ultima = 0.0
        self._params: dict[str, set[str]] | None = None

    def parametros_validos(self, endpoint: str) -> set[str]:
        if self._params is None:
            spec = httpx.get(OPENAPI, timeout=60).json()  # público, não usa a chave
            self._params = {p.removeprefix("/api-de-dados/"): {x["name"] for x in v["get"].get("parameters", [])} for p, v in spec["paths"].items() if "get" in v}
        return self._params[endpoint]

    def get(self, endpoint: str, **params) -> list | dict:
        desconhecidos = set(params) - self.parametros_validos(endpoint)
        if desconhecidos:
            raise ValueError(f"{endpoint}: parâmetros fora do OpenAPI: {sorted(desconhecidos)}")
        if self.requisicoes >= MAX_REQUISICOES:
            raise PortalErro(f"teto de {MAX_REQUISICOES} requisições por execução atingido")
        espera = self.intervalo - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.monotonic()
        self.requisicoes += 1
        resp = self.http.get(f"{BASE}/{endpoint}", params=params)
        if resp.status_code in (401, 403, 429):
            raise PortalErro(f"{endpoint}: HTTP {resp.status_code} ({resp.text[:120]!r}): execução interrompida, sem nova tentativa")
        resp.raise_for_status()
        return resp.json()

    def todas_as_paginas(self, endpoint: str, **params) -> list[dict]:
        itens: list[dict] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            lote = self.get(endpoint, **params, pagina=pagina)
            if not lote:
                return itens
            itens += lote
        raise PortalErro(f"{endpoint}: mais de {MAX_PAGINAS} páginas, interrompido por segurança")


def salvar(nome: str, params: dict, itens: list, gravar: bool) -> None:
    if not gravar:
        return
    FIXTURES.mkdir(parents=True, exist_ok=True)
    corpo = {"endpoint": nome.split("__")[0], "params": params, "coletado_em": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"), "total_itens": len(itens), "amostra": itens[:MAX_AMOSTRA]}
    (FIXTURES / f"{nome}.json").write_text(json.dumps(corpo, ensure_ascii=False, indent=2), encoding="utf-8")


def distintos(itens: list[dict], rotulo: str, extrair) -> None:
    print(f"    {rotulo}: {dict(Counter(extrair(i) for i in itens).most_common(8))}")


def cnpjs_dos_fundos() -> set[str]:
    """CNPJs dos fundos municipais vistos como recebedores no Transferegov (amostra da T1.1)."""
    caminho = RAIZ / "tests" / "fixtures" / "transferegov_api" / "parcerias__proposta.json"
    if not caminho.exists():
        return set()
    return {p["cnpj_ente_recebedor"] for p in json.loads(caminho.read_text(encoding="utf-8"))["amostra"]}


def titulo(texto: str) -> None:
    print(f"\n=== {texto}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sem-fixtures", action="store_true")
    args = parser.parse_args(argv)
    gravar = not args.sem_fixtures

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    config = carregar_config()
    ibge, cnpj = config.regras.municipio.codigo_ibge, config.regras.municipio.cnpj_prefeitura
    inicio = config.regras.municipio.inicio_recorte
    hoje = datetime.now(ZoneInfo(config.regras.coleta.fuso)).date()
    c = Cliente(ler_chave(), config.regras.coleta.portal_transparencia_req_por_min)
    print(f"intervalo mínimo entre requisições: {c.intervalo:.2f} s ({config.regras.coleta.portal_transparencia_req_por_min}/min; limite da API 400/min)")

    try:
        titulo(f"/convenios  codigoIBGE={ibge} (15 por página, sem total: pagina até vir vazia)")
        convenios = c.todas_as_paginas("convenios", codigoIBGE=ibge)
        print(f"  convênios: {len(convenios)}; campos: {sorted(convenios[0]) if convenios else None}")
        if convenios:
            distintos(convenios, "situacao", lambda i: i["situacao"])
            distintos(convenios, "tipoInstrumento", lambda i: i["tipoInstrumento"]["descricao"])
            distintos(convenios, "municipioConvenente.codigoIBGE", lambda i: i["municipioConvenente"]["codigoIBGE"])
            distintos(convenios, "convenente", lambda i: i["convenente"]["nome"])
            distintos(convenios, "orgaoMaximo", lambda i: i["orgao"]["orgaoMaximo"]["nome"] if i["orgao"].get("orgaoMaximo") else None)
            vig = sorted(i["dataFinalVigencia"] for i in convenios if i.get("dataFinalVigencia"))
            print(f"    dataInicioVigencia mais antiga/recente: {min(i['dataInicioVigencia'] for i in convenios)} / {max(i['dataInicioVigencia'] for i in convenios)}; dataFinalVigencia: {vig[0]} .. {vig[-1]}")
            print(f"    exemplo (resumo): { {k: (i := convenios[0])[k] for k in ('id', 'situacao', 'valor', 'valorLiberado', 'valorContrapartida', 'dataUltimaLiberacao', 'numeroProcesso')} } numero={convenios[0]['dimConvenio']['numero']}")
        salvar("convenios__codigoIBGE", {"codigoIBGE": ibge}, convenios, gravar)

        titulo("Comparação com o Siconv em lote (amostras da T1.2)")
        pasta = RAIZ / "tests" / "fixtures" / "transferegov_discricionarias"
        if (pasta / "convenio.csv").exists() and convenios:
            import pandas as pd

            ler = lambda nome: pd.read_csv(pasta / nome, sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)  # noqa: E731
            siconv_conv = ler("convenio.csv").merge(ler("proposta.csv")[["ID_PROPOSTA", "NR_PROPOSTA"]], on="ID_PROPOSTA", how="left")
            siconv_conv["chave"] = siconv_conv["NR_PROPOSTA"].map(normalizar_numero)
            portal: dict[str, list[dict]] = {}
            for i in convenios:
                portal.setdefault(normalizar_numero(i["dimConvenio"]["numero"]), []).append(i)
            nr_convenio = set(siconv_conv["NR_CONVENIO"])
            print(f"  Portal: {len(convenios)} convênios, {len(portal)} números distintos após normalizar; em comum com o NR_CONVENIO do Siconv: {len(nr_convenio & {i['dimConvenio']['numero'] for i in convenios})}")
            casados = siconv_conv[siconv_conv["chave"].isin(portal)]
            print(f"  casam com o Siconv por NR_PROPOSTA (zeros à esquerda ignorados): {len(casados)} de {len(siconv_conv)}")
            cruzamento = Counter((r.SIT_CONVENIO, portal[r.chave][0]["situacao"]) for r in casados.itertuples())
            print(f"    situação Siconv -> Portal: {dict(cruzamento)}")
            print(f"    sem par no Portal: {[(r.NR_PROPOSTA, r.SIT_CONVENIO) for r in siconv_conv[~siconv_conv['chave'].isin(portal)].itertuples()]}")
            # `NORMAL` não é "ativo": nos que casam com o Siconv equivale a "Prestação de Contas Concluída"
            em_aberto = [i for i in convenios if i["situacao"] in ("EM EXECUÇÃO", "NORMAL", "PRESTAÇÃO DE CONTAS EM ANÁLISE")]
            print(f"  convênios EM EXECUÇÃO, NORMAL ou PRESTAÇÃO DE CONTAS EM ANÁLISE no Portal ({len(em_aberto)}): {[(i['dimConvenio']['numero'], i['situacao'], i['dataInicioVigencia'], i['valor']) for i in em_aberto]}")

        titulo("/emendas: a emenda vem agregada? (as emendas indicadas ao município no Transferegov)")
        indicadas = RAIZ / "tests" / "fixtures" / "oportunidades" / "parcerias_emendas_indicadas.json"
        emendas_portal: list[dict] = []
        if indicadas.exists():
            codigos = sorted({e["nr_emenda"].replace(".", "") for e in json.loads(indicadas.read_text(encoding="utf-8"))})
            for codigo in codigos:
                emendas_portal += c.get("emendas", codigoEmenda=codigo, pagina=1)
            print(f"  emendas consultadas: {len(codigos)}; achadas no Portal: {len(emendas_portal)}")
            distintos(emendas_portal, "localidadeDoGasto", lambda i: i["localidadeDoGasto"])
            print(f"  valorEmpenhado (centavos) de {emendas_portal[0]['codigoEmenda']}: {centavos(emendas_portal[0]['valorEmpenhado'])} (a emenda inteira, não só o município)")
        salvar("emendas__codigoEmenda", {"codigoEmenda": "<nr_emenda das emendas indicadas>"}, emendas_portal, gravar)

        favorecidos = sorted({cnpj, *cnpjs_dos_fundos()})
        titulo(f"/despesas/recursos-recebidos  controle: codigoIBGE={ibge} (esperado: vazio, filtro não confiável)")
        controle = c.get("despesas/recursos-recebidos", mesAnoInicio=f"{hoje.year}-01"[5:] + f"/{hoje.year}", mesAnoFim=f"{hoje:%m/%Y}", codigoIBGE=ibge, pagina=1)
        print(f"  codigoIBGE devolveu {len(controle)} linhas no período")

        titulo(f"/despesas/recursos-recebidos  codigoFavorecido em {favorecidos}, de {inicio.year} a {hoje.year} (janelas de 1 ano)")
        recebidos: list[dict] = []
        for favorecido in favorecidos:
            for ano in range(inicio.year, hoje.year + 1):
                fim = f"12/{ano}" if ano < hoje.year else f"{hoje:%m/%Y}"
                recebidos += c.todas_as_paginas("despesas/recursos-recebidos", mesAnoInicio=f"01/{ano}", mesAnoFim=fim, codigoFavorecido=favorecido)
        print(f"  linhas: {len(recebidos)}; campos: {sorted(recebidos[0]) if recebidos else None}")
        if recebidos:
            print(f"    codigoPessoa vem formatado: {sorted({i['codigoPessoa'] for i in recebidos})}")
            distintos(recebidos, "nomePessoa", lambda i: i["nomePessoa"])
            distintos(recebidos, "orgaoSuperior", lambda i: i["nomeOrgaoSuperior"])
            distintos(recebidos, "UG", lambda i: i["nomeUG"])
            por_ano: dict[int, int] = {}
            for i in recebidos:
                por_ano[i["anoMes"] // 100] = por_ano.get(i["anoMes"] // 100, 0) + round(i["valor"] * 100)
            print(f"    soma por ano (R$): { {a: v / 100 for a, v in sorted(por_ano.items())} }")
        salvar("recursos_recebidos__codigoFavorecido", {"codigoFavorecido": favorecidos, "anos": f"{inicio.year}..{hoje.year}"}, recebidos, gravar)

        titulo(f"/despesas/documentos-por-favorecido  fase=3 (pagamento), {inicio.year} a {hoje.year}, favorecidos {favorecidos}")
        for favorecido in favorecidos:
            docs: list[dict] = []
            for ano in range(inicio.year, hoje.year + 1):
                docs += c.todas_as_paginas("despesas/documentos-por-favorecido", codigoPessoa=favorecido, fase=3, ano=ano)
            validos, invalidos = [], []
            for d in docs:
                try:
                    validos.append(centavos(d["valor"]) or 0)
                except InvalidOperation:
                    invalidos.append(d["valor"])
            print(f"  {favorecido}: {len(docs)} pagamentos, R$ {sum(validos) / 100:,.2f} nos {len(validos)} com valor legível; valores ilegíveis: {len(invalidos)} {sorted(set(invalidos))[:5]}")
            if docs:
                distintos(docs, "orgaoSuperior", lambda d: d["orgaoSuperior"])
                distintos(docs, "autor (emenda)", lambda d: d["autor"] or None)
                distintos(docs, "favorecidoIntermediario", lambda d: d["favorecidoIntermediario"])
            salvar(f"documentos_pagamento__{favorecido}", {"codigoPessoa": favorecido, "fase": 3, "anos": f"{inicio.year}..{hoje.year}"}, docs, gravar)
    except PortalErro as e:
        print(f"\nINTERROMPIDO: {e}")
        print(f"Requisições feitas até aqui: {c.requisicoes}")
        return 2
    print(f"\nRequisições feitas: {c.requisicoes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
