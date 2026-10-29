"""T1.1 POC da API pública do Transferegov (módulos parcerias, fundoafundo, especiais).

Uso:
    python scripts/poc_transferegov_api.py [--sem-fixtures]

O que faz:
- baixa o OpenAPI de cada módulo e valida cada nome de parâmetro antes de chamar (a API ignora
  parâmetros desconhecidos e devolve a tabela inteira com HTTP 200);
- filtra pelo município (código IBGE do config/regras.yaml) onde o módulo tem esse filtro;
- confere que o filtro funciona (todas as linhas têm o IBGE pedido, total menor que o sem filtro,
  parâmetro falso não filtra);
- liga os módulos que não têm filtro por município (parceria, termos de adesão, planos de ação e
  de trabalho de emendas especiais) pelos ids das verbas do município;
- imprime total, campos e valores distintos de situação, e grava amostras em
  tests/fixtures/transferegov_api/ (máx. 50 registros, sem dados bancários nem e-mail).
"""

import argparse
import io
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from nucleo.config import carregar_config

BASE = "https://api-publica.transferegov.gestao.gov.br"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "transferegov_api"
MAX_AMOSTRA = 50
PAGINA = 200  # máximo aceito pela API (OpenAPI: tamanho_da_pagina <= 200)
PAUSA_S = 0.3
SENSIVEIS = ("numero_conta", "numero_agencia", "dv_conta", "dv_agencia", "email", "nome_agencia")


class Cliente:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "verba-a-vista/0.1"})
        self.specs: dict[str, dict] = {}
        self.requisicoes = 0

    def spec(self, modulo: str) -> dict:
        if modulo not in self.specs:
            self.specs[modulo] = self._get(f"{BASE}/{modulo}/openapi.json", {}).json()
        return self.specs[modulo]

    def _get(self, url: str, params: dict) -> httpx.Response:
        for tentativa in range(4):
            self.requisicoes += 1
            time.sleep(PAUSA_S)
            try:
                resp = self.http.get(url, params=params)
            except httpx.HTTPError:
                if tentativa == 3:
                    raise
                time.sleep(2**tentativa)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and tentativa < 3:
                time.sleep(2 ** (tentativa + 1))
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("inalcançável")

    def validar(self, modulo: str, endpoint: str, params: dict) -> None:
        validos = {p["name"] for p in self.spec(modulo)["paths"][f"/{endpoint}"]["get"].get("parameters", [])}
        desconhecidos = set(params) - validos
        if desconhecidos:
            raise ValueError(f"{modulo}/{endpoint}: parâmetros fora do OpenAPI: {sorted(desconhecidos)}")

    def pagina(self, modulo: str, endpoint: str, params: dict, validar: bool = True) -> dict:
        if validar:
            self.validar(modulo, endpoint, params)
        return self._get(f"{BASE}/{modulo}/{endpoint}", params).json()

    def todos(self, modulo: str, endpoint: str, params: dict) -> tuple[list[dict], int]:
        """Todos os registros (paginando). Devolve (registros, total_items informado pela API)."""
        registros: list[dict] = []
        pagina = 1
        while True:
            dados = self.pagina(modulo, endpoint, {**params, "pagina": pagina, "tamanho_da_pagina": PAGINA})
            registros += dados["data"]
            if pagina >= dados["total_pages"]:
                return registros, dados["total_items"]
            pagina += 1

    def total(self, modulo: str, endpoint: str, params: dict, validar: bool = True) -> int:
        return self.pagina(modulo, endpoint, {**params, "pagina": 1, "tamanho_da_pagina": 1}, validar)["total_items"]


def limpar(registro: dict) -> dict:
    return {k: v for k, v in registro.items() if not any(s in k for s in SENSIVEIS)}


def salvar(nome: str, url: str, params: dict, registros: list[dict], total: int, gravar: bool) -> None:
    if not gravar:
        return
    FIXTURES.mkdir(parents=True, exist_ok=True)
    corpo = {
        "url": url,
        "params": params,
        "coletado_em": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
        "total_items": total,
        "amostra": [limpar(r) for r in registros[:MAX_AMOSTRA]],
    }
    (FIXTURES / f"{nome}.json").write_text(json.dumps(corpo, ensure_ascii=False, indent=2), encoding="utf-8")


def distintos(registros: list[dict], *campos: str) -> None:
    for campo in campos:
        contagem = Counter(r.get(campo) for r in registros)
        print(f"    {campo}: {dict(contagem.most_common())}")


def titulo(texto: str) -> None:
    print(f"\n=== {texto}")


def eh_prefeitura(nome: str | None, nome_municipio: str) -> bool:
    n = (nome or "").upper()
    return nome_municipio.upper() in n and ("MUNICIPIO" in n or "MUNICÍPIO" in n or "PREFEITURA" in n)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sem-fixtures", action="store_true", help="não grava amostras em tests/fixtures")
    args = parser.parse_args(argv)
    gravar = not args.sem_fixtures

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    config = carregar_config()
    ibge = int(config.regras.municipio.codigo_ibge)
    nome_municipio = config.regras.municipio.nome
    c = Cliente()

    titulo("Data de atualização dos dados (por módulo)")
    for modulo in ("parcerias", "fundoafundo", "especiais"):
        print(f"  {modulo}: {c.pagina(modulo, 'data-atualizacao', {})}")

    # --- parcerias -------------------------------------------------------------------------
    titulo(f"parcerias/proposta  filtro cd_ibge_recebedor={ibge}")
    params = {"cd_ibge_recebedor": ibge}
    propostas, total = c.todos("parcerias", "proposta", params)
    sem_filtro = c.total("parcerias", "proposta", {})
    falso = c.total("parcerias", "proposta", {"cd_ibge_recebedorx": ibge}, validar=False)
    print(f"  registros do município: {len(propostas)} (total_items={total}); sem filtro: {sem_filtro}")
    print(f"  controle: parâmetro falso devolve {falso} (== sem filtro? {falso == sem_filtro}) -> API ignora parâmetro desconhecido")
    print(f"  todas as linhas têm o IBGE pedido: {all(p['cd_ibge_recebedor'] == ibge for p in propostas)}")
    if propostas:
        print(f"  campos: {sorted(propostas[0])}")
        distintos(propostas, "situacao_proposta", "in_situacao_analise", "ano_proposta", "cnpj_ente_recebedor", "nm_ente_recebedor")
        desde = sum(1 for p in propostas if (p.get("dt_proposta") or "") >= config.regras.municipio.inicio_recorte.isoformat())
        print(f"  propostas com dt_proposta >= {config.regras.municipio.inicio_recorte}: {desde}")
    salvar("parcerias__proposta", f"{BASE}/parcerias/proposta", params, propostas, total, gravar)

    parcerias: list[dict] = []
    if propostas:
        titulo("parcerias/parceria  por id_proposta (sem filtro de município no endpoint)")
        for p in propostas:
            regs, _ = c.todos("parcerias", "parceria", {"id_proposta": p["id_proposta"]})
            parcerias += regs
        print(f"  parcerias ligadas às propostas: {len(parcerias)}")
        if parcerias:
            print(f"  campos: {sorted(parcerias[0])}")
            distintos(parcerias, "in_situacao_parceria", "in_situacao_autorizacao_execucao", "tp_origem")
        salvar("parcerias__parceria", f"{BASE}/parcerias/parceria", {"id_proposta": "<ids das propostas>"}, parcerias, len(parcerias), gravar)

    # --- fundoafundo -----------------------------------------------------------------------
    titulo("fundoafundo/planos-acao  filtro por código IBGE (esperado: erro 500 da API)")
    try:
        c.total("fundoafundo", "planos-acao", {"codigo_ibge_municipio_ente_recebedor_plano_acao": ibge})
        print("  filtro por IBGE funcionou desta vez")
    except httpx.HTTPStatusError as e:
        print(f"  codigo_ibge_municipio_ente_recebedor_plano_acao={ibge} -> HTTP {e.response.status_code} {e.response.text[:60]}")

    titulo(f"fundoafundo/planos-acao  filtro nome_municipio_ente_recebedor_plano_acao={nome_municipio!r}")
    params = {"nome_municipio_ente_recebedor_plano_acao": nome_municipio}
    planos_faf, total = c.todos("fundoafundo", "planos-acao", params)
    print(f"  registros do município: {len(planos_faf)} (total_items={total}); sem filtro: {c.total('fundoafundo', 'planos-acao', {})}")
    ok = all(str(p["codigo_ibge_municipio_ente_recebedor_plano_acao"]) == str(ibge) for p in planos_faf)
    print(f"  todas as linhas têm o IBGE esperado: {ok}")
    if planos_faf:
        print(f"  campos: {sorted(planos_faf[0])}")
        distintos(
            planos_faf,
            "situacao_plano_acao",
            "sigla_orgao_repassador_plano_acao",
            "tipo_unidade_recebedora_plano_acao",
            "cnpj_ente_recebedor_plano_acao",
            "nome_ente_recebedor_plano_acao",
        )
    salvar("fundoafundo__planos-acao", f"{BASE}/fundoafundo/planos-acao", params, planos_faf, total, gravar)

    fundos = sorted({p["cnpj_ente_recebedor"] for p in propostas if "FUNDO" in (p.get("nm_ente_recebedor") or "").upper()})
    for fundo in fundos:
        titulo(f"fundoafundo/planos-acao  filtro cnpj_fundo_vinculado_plano_acao={fundo} (fundos vistos em parcerias)")
        regs, total = c.todos("fundoafundo", "planos-acao", {"cnpj_fundo_vinculado_plano_acao": fundo})
        print(f"  registros: {len(regs)}")
        if regs:
            distintos(regs, "situacao_plano_acao", "nome_ente_recebedor_plano_acao", "nome_fundo_vinculado_plano_acao", "codigo_ibge_municipio_ente_recebedor_plano_acao")
            planos_faf += [r for r in regs if r["id_plano_acao"] not in {p["id_plano_acao"] for p in planos_faf}]

    if planos_faf:
        titulo("fundoafundo/termos-adesao  por id_plano_acao")
        termos: list[dict] = []
        for p in planos_faf:
            regs, _ = c.todos("fundoafundo", "termos-adesao", {"id_plano_acao": p["id_plano_acao"]})
            termos += regs
        print(f"  termos de adesão ligados aos planos: {len(termos)}")
        if termos:
            print(f"  campos: {sorted(termos[0])}")
            distintos(termos, "situacao_termo_adesao")
        salvar("fundoafundo__termos-adesao", f"{BASE}/fundoafundo/termos-adesao", {"id_plano_acao": "<ids>"}, termos, len(termos), gravar)

    titulo(f"fundoafundo/programas-beneficiarios  filtro codigo_ibge_municipio_ente_beneficiario_programa={ibge}")
    params = {"codigo_ibge_municipio_ente_beneficiario_programa": ibge}
    benef_faf, total = c.todos("fundoafundo", "programas-beneficiarios", params)
    print(f"  registros do município: {len(benef_faf)} (total_items={total})")
    if benef_faf:
        distintos(benef_faf, "tipo_beneficiario_programa", "nome_ente_beneficiario_programa")
    salvar("fundoafundo__programas-beneficiarios", f"{BASE}/fundoafundo/programas-beneficiarios", params, benef_faf, total, gravar)

    # --- especiais -------------------------------------------------------------------------
    titulo("especiais: identificar a prefeitura (CNPJ) a partir dos recebedores encontrados acima")
    candidatos: Counter = Counter()
    for p in propostas:
        if eh_prefeitura(p.get("nm_ente_recebedor"), nome_municipio):
            candidatos[(p["cnpj_ente_recebedor"], p["nm_ente_recebedor"])] += 1
    for p in planos_faf:
        if eh_prefeitura(p.get("nome_ente_recebedor_plano_acao"), nome_municipio):
            candidatos[(p["cnpj_ente_recebedor_plano_acao"], p["nome_ente_recebedor_plano_acao"])] += 1
    print(f"  candidatos (cnpj, nome): {dict(candidatos)}")

    beneficiarios: list[dict] = []
    for cnpj, _ in candidatos:
        titulo(f"especiais/beneficiarios-especiais  filtro cnpj_beneficiario={cnpj}")
        regs, total = c.todos("especiais", "beneficiarios-especiais", {"cnpj_beneficiario": cnpj})
        print(f"  registros: {len(regs)}")
        beneficiarios += regs
    titulo("especiais/beneficiarios-especiais  conferência: todos os beneficiários de SP, procurando o município")
    sp, _ = c.todos("especiais", "beneficiarios-especiais", {"uf_beneficiario": "SP"})
    cnpjs = {cnpj for cnpj, _ in candidatos}
    achados = [b for b in sp if nome_municipio.upper() in b["nome_beneficiario"].upper() or b["cnpj_beneficiario"] in cnpjs]
    print(f"  beneficiários de SP no módulo: {len(sp)}; correspondentes a {nome_municipio}: {len(achados)}")
    for b in achados:
        if b["id_beneficiario"] not in {x["id_beneficiario"] for x in beneficiarios}:
            beneficiarios.append(b)
    if beneficiarios:
        print(f"  campos: {sorted(beneficiarios[0])}")
    salvar("especiais__beneficiarios-especiais", f"{BASE}/especiais/beneficiarios-especiais", {"cnpj_beneficiario": "<cnpj da prefeitura>"}, beneficiarios, len(beneficiarios), gravar)

    planos_esp: list[dict] = []
    for b in beneficiarios:
        regs, _ = c.todos("especiais", "planos-acao-especiais", {"id_beneficiario": b["id_beneficiario"]})
        planos_esp += regs
    titulo("especiais/planos-acao-especiais  por id_beneficiario")
    print(f"  planos de ação (emendas Pix): {len(planos_esp)}")
    if planos_esp:
        print(f"  campos: {sorted(planos_esp[0])}")
        distintos(planos_esp, "situacao_plano_acao", "modalidade_plano_acao", "ano_plano_acao", "ano_emenda_parlamentar_plano_acao")
        print(f"  com motivo_impedimento_plano_acao preenchido: {sum(1 for p in planos_esp if p.get('motivo_impedimento_plano_acao'))}")
    salvar("especiais__planos-acao-especiais", f"{BASE}/especiais/planos-acao-especiais", {"id_beneficiario": "<ids>"}, planos_esp, len(planos_esp), gravar)

    trabalhos: list[dict] = []
    for p in planos_esp:
        regs, _ = c.todos("especiais", "planos-trabalho-especiais", {"id_plano_acao": p["id_plano_acao"]})
        trabalhos += regs
    titulo("especiais/planos-trabalho-especiais  por id_plano_acao")
    print(f"  planos de trabalho: {len(trabalhos)}")
    if trabalhos:
        print(f"  campos: {sorted(trabalhos[0])}")
        distintos(trabalhos, "situacao_plano_trabalho")
    salvar("especiais__planos-trabalho-especiais", f"{BASE}/especiais/planos-trabalho-especiais", {"id_plano_acao": "<ids>"}, trabalhos, len(trabalhos), gravar)

    print(f"\nRequisições feitas: {c.requisicoes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
