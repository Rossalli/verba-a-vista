"""T1.5 POC do CAUC (Tesouro Nacional) via dataset do Tesouro Transparente (CKAN).

Uso:
    python scripts/poc_cauc.py [--sem-fixtures]

O que faz:
- consulta a API CKAN do Tesouro Transparente (package_show, dataset `cauc`) e acha o recurso
  "Relatório da situação dos municípios no CAUC" (CSV) sem fixar o endereço do arquivo;
- baixa o CSV, lê (cp1252, `;`, 3 linhas de metadados antes do cabeçalho, legenda dos itens no fim)
  e filtra pelo código IBGE do município;
- classifica cada item do CAUC em: sem comprovação (`!`), regular até uma data, desabilitado ou
  sem dado, conforme o dicionário oficial (PDF de metadados do Tesouro Transparente);
- grava amostra em tests/fixtures/cauc/ (linhas originais, mesma codificação).
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import httpx

from nucleo.config import carregar_config

CKAN = "https://www.tesourotransparente.gov.br/ckan/api/3/action"
DATASET = "cauc"
NOME_RECURSO = "Relatório da situação dos municípios no CAUC"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cauc"
ENCODING = "cp1252"
LINHAS_METADADOS = 3
COLUNA_ITEM = re.compile(r"\d\.\d(\.\d)?")

SEM_COMPROVACAO = "sem_comprovacao"  # "!": o CAUC não obteve a comprovação do requisito
REGULAR_ATE = "regular_ate"  # data de validade da comprovação
DESABILITADO = "desabilitado"  # item indisponível na data, válido para todos os entes
SEM_DADO = "sem_dado"  # célula vazia


def classificar_celula(valor: str) -> tuple[str, date | None]:
    """Classifica uma célula de item do CAUC. Valor desconhecido levanta ValueError (nunca chutar)."""
    valor = valor.strip()
    if valor == "!":
        return SEM_COMPROVACAO, None
    if valor == "Desabilitado":
        return DESABILITADO, None
    if valor == "":
        return SEM_DADO, None
    try:
        return REGULAR_ATE, datetime.strptime(valor, "%d/%m/%y").date()
    except ValueError:
        raise ValueError(f"valor de célula do CAUC não reconhecido: {valor!r}") from None


def escolher_recurso(pacote: dict) -> dict:
    """Recurso CSV de municípios do dataset CKAN, achado pelo nome (o endereço do arquivo não é estável)."""
    candidatos = [r for r in pacote["resources"] if r.get("name") == NOME_RECURSO and (r.get("format") or "").upper() == "CSV"]
    if len(candidatos) != 1:
        raise LookupError(f"esperava 1 recurso CSV {NOME_RECURSO!r}, achei {len(candidatos)}")
    return candidatos[0]


def ler_cauc(dados: bytes) -> tuple[dict, list[str], list[list[str]], dict[str, str]]:
    """Devolve (metadados, cabeçalho, entes, legenda).

    - metadados: data_pesquisa (date), tipo_ente, abrangencia;
    - entes: linhas com a largura do cabeçalho;
    - legenda: código do item (ou do grupo, em algarismos romanos) -> exigência. Fica no fim do
      arquivo, em linhas de 2 colunas; qualquer outra linha curta no meio dos dados é erro.
    """
    linhas = dados.decode(ENCODING).splitlines()
    brutos = [linha.strip().strip('"') for linha in linhas[:LINHAS_METADADOS]]
    achado = re.search(r"(\d{2}/\d{2}/\d{4})", brutos[0])
    if not achado:
        raise ValueError(f"data da pesquisa não encontrada em {brutos[0]!r}")
    meta = {
        "data_pesquisa": datetime.strptime(achado.group(1), "%d/%m/%Y").date(),
        "tipo_ente": brutos[1].split(":", 1)[1].strip(),
        "abrangencia": brutos[2].split(":", 1)[1].strip(),
    }
    tabela = list(csv.reader(linhas[LINHAS_METADADOS:], delimiter=";"))
    cabecalho, resto = tabela[0], tabela[1:]
    entes: list[list[str]] = []
    legenda_linhas: list[list[str]] = []
    for linha in resto:
        if len(linha) == len(cabecalho) and not legenda_linhas:
            entes.append(linha)
        elif len(linha) == 2:
            legenda_linhas.append(linha)
        else:
            raise ValueError(f"linha com {len(linha)} colunas fora da legenda: {linha[:3]}")
    legenda = {codigo: nome for codigo, nome in legenda_linhas[1:]}  # [0] é o cabeçalho "Código do Itens;Exigência"
    return meta, cabecalho, entes, legenda


def salvar(nome: str, dados: bytes, gravar: bool) -> None:
    if gravar:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / nome).write_bytes(dados)


def titulo(texto: str) -> None:
    print(f"\n=== {texto}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sem-fixtures", action="store_true")
    args = parser.parse_args(argv)
    gravar = not args.sem_fixtures

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    config = carregar_config()
    ibge = config.regras.municipio.codigo_ibge

    with httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "verba-a-vista/0.1"}) as http:
        titulo(f"CKAN: package_show id={DATASET}")
        pacote = http.get(f"{CKAN}/package_show", params={"id": DATASET}).json()["result"]
        recurso = escolher_recurso(pacote)
        print(f"  recurso: {recurso['name']} | last_modified={recurso['last_modified']} | size={recurso['size']}")
        print(f"  url: {recurso['url']}")
        print(f"  extras do dataset: {[(e['key'], e['value']) for e in pacote.get('extras', [])]}")
        resp = http.get(recurso["url"])
        resp.raise_for_status()
        print(f"  download: HTTP {resp.status_code}, {len(resp.content)} bytes, Last-Modified={resp.headers.get('last-modified')}, ETag={resp.headers.get('etag')}")

    meta, cabecalho, entes, legenda = ler_cauc(resp.content)
    titulo("Arquivo")
    print(f"  metadados: {meta}")
    print(f"  entes: {len(entes)}; colunas: {len(cabecalho)}; linhas de legenda: {len(legenda)}")
    idx = {c: i for i, c in enumerate(cabecalho)}
    itens = [c for c in cabecalho if COLUNA_ITEM.fullmatch(c)]
    print(f"  colunas de item: {len(itens)}; todas na legenda: {set(itens) <= set(legenda)}")
    print(f"  itens da legenda sem coluna: {sorted(k for k in legenda if COLUNA_ITEM.fullmatch(k) and k not in itens)}")

    titulo(f"Município {config.regras.municipio.nome} (IBGE {ibge})")
    meu = [linha for linha in entes if linha[idx["Código IBGE"]] == ibge]
    print(f"  linhas encontradas: {len(meu)}")
    (linha,) = meu
    print(f"  UF={linha[idx['UF']]} nome={linha[idx['Nome do Ente Federado']]!r} SIAFI={linha[idx['Código SIAFI']]} população={linha[idx['População']]}")
    resultado = {i: classificar_celula(linha[idx[i]]) for i in itens}
    print(f"  resumo: {dict(Counter(tipo for tipo, _ in resultado.values()))}")
    for i, (tipo, _) in resultado.items():
        if tipo == SEM_COMPROVACAO:
            print(f"  >>> SEM COMPROVAÇÃO: item {i} - {legenda[i]}")
    print(f"  desabilitados: {[i for i, (t, _) in resultado.items() if t == DESABILITADO]}")
    validades = sorted((v, i) for i, (t, v) in resultado.items() if t == REGULAR_ATE)
    print(f"  validades mais próximas: {[(v.isoformat(), i) for v, i in validades[:5]]}; mais distante: {validades[-1][0].isoformat()}")
    vencidas = [i for i, (t, v) in resultado.items() if t == REGULAR_ATE and v < meta["data_pesquisa"]]
    print(f"  datas anteriores à data da pesquisa (vencidas)? {vencidas or 'nenhuma'}")

    titulo("Contexto (todos os entes do arquivo)")
    celulas: Counter = Counter()
    por_ente: dict[str, int] = {}
    for outro in entes:
        tipos = [classificar_celula(outro[idx[i]])[0] for i in itens]
        celulas.update(tipos)
        por_ente[outro[idx["Código IBGE"]]] = tipos.count(SEM_COMPROVACAO)
    print(f"  células por tipo: {dict(celulas)}")
    sp = [o for o in entes if o[idx["UF"]] == config.regras.municipio.uf]
    com_pendencia = sum(1 for o in sp if por_ente[o[idx["Código IBGE"]]] > 0)
    print(f"  municípios de {config.regras.municipio.uf} no arquivo: {len(sp)}; com ao menos um item sem comprovação: {com_pendencia}")
    print(f"  municípios (Brasil) com ao menos um item sem comprovação: {sum(1 for n in por_ente.values() if n)} de {len(entes)}")

    # amostra (linhas originais): metadados + cabeçalho + o município + o ente com mais itens sem
    # comprovação + a legenda completa
    brutas = resp.content.decode(ENCODING).splitlines()
    inicio_dados = LINHAS_METADADOS + 1
    pior = max(entes, key=lambda o: por_ente[o[idx["Código IBGE"]]])[idx["Código IBGE"]]
    escolhidas = brutas[:inicio_dados]
    for posicao, outro in enumerate(entes):
        if outro[idx["Código IBGE"]] in {ibge, pior}:
            escolhidas.append(brutas[inicio_dados + posicao])
    escolhidas += brutas[inicio_dados + len(entes):]
    salvar("municipios_amostra.csv", ("\n".join(escolhidas) + "\n").encode(ENCODING), gravar)
    salvar(
        "recurso.json",
        json.dumps({"url": recurso["url"], "last_modified": recurso["last_modified"], "size": recurso["size"], "etag": resp.headers.get("etag"), "data_pesquisa": meta["data_pesquisa"].isoformat()}, ensure_ascii=False, indent=2).encode("utf-8"),
        gravar,
    )
    print("\nAmostra gravada em tests/fixtures/cauc/ (município, ente com mais pendências e legenda)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
