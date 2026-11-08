"""Publicação (spec §9; plano T2.5): `dados/publicados/verbas.json` e `verbas.csv`.

- `verbas.json` é o que o site lê e o que o passo de histórico (T2.4) relê no dia seguinte: um objeto com a
  data de referência, a situação de cada fonte, as referências do Tesouro e a lista em `verbas`. Não leva hora
  de geração: reexecutar sem mudança nas fontes gera o mesmo arquivo e nenhum diff no Git.
- `verbas.csv` é para quem abre no Excel: UTF-8 com BOM, separador `;`, valores em reais com vírgula decimal,
  rótulos do site (`config/taxonomia.yaml`) e células de texto protegidas contra fórmulas.
- Tudo é validado contra schemas/ antes de gravar. Se algo falhar, nada é gravado (o publicado de ontem fica).
"""

import csv
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from nucleo.config import Config
from nucleo.dinheiro import centavos_reais
from nucleo.modelo import Verba

VERSAO = 1
ARQUIVO_JSON = Path("dados") / "publicados" / "verbas.json"
ARQUIVO_CSV = Path("dados") / "publicados" / "verbas.csv"
SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
NOMES_FONTES = {
    "transferegov_discricionarias": "Transferegov — Discricionárias e Legais (Siconv)",
    "transferegov_api": "Transferegov — API pública",
    "portal_transparencia": "Portal da Transparência",
    "obrasgov": "Obrasgov",
    "cauc": "CAUC (Tesouro Nacional)",
    "tesouro_constitucionais": "Tesouro — Transferências Constitucionais",
    "transferegov_acesso_livre": "Transferegov — Acesso Livre (conferência manual semanal)",
}
PRAZOS = ("proposta", "assinatura", "clausula_suspensiva", "fim_vigencia", "prestacao_contas", "adesao")
CABECALHO_CSV = [
    "id", "tipo", "instrumento", "nome", "objeto", "orgao_concedente", "parlamentar", "numero_instrumento",
    "situacao", "situacao_na_fonte", "em_risco", "alertas",
    "valor_total_reais", "contrapartida_reais", "liberado_reais", "executado_reais", "devolvido_reais",
    *(f"prazo_{p}" for p in PRAZOS), "execucao_fisica_pct",
    "perda_categoria", "perda_texto", "perda_evitavel", "perda_data", "perda_valor_reais", "perda_gerada_por_ia", "perda_revisada_por", "perda_revisada_em",
    "fontes", "ultima_coleta",
]


@dataclass
class ResultadoPublicacao:
    json: Path
    csv: Path
    verbas: int


# --- o que cada fonte informa sobre a data do dado ---------------------------------------------


def _data_do_dado(fonte: str, retrato: dict) -> date | None:
    meta = retrato["metadados"]
    if fonte == "transferegov_discricionarias" and meta.get("data_carga"):
        return datetime.strptime(meta["data_carga"][:10], "%d/%m/%Y").date()  # "17/07/2026 06:30:47"
    if fonte == "cauc":
        return date.fromisoformat(meta["data_pesquisa"])
    if fonte == "obrasgov" and meta.get("data_ultima_atualizacao"):
        return date.fromisoformat(meta["data_ultima_atualizacao"][:10])
    if fonte == "transferegov_api":
        datas = [date.fromisoformat(m["data_ultima_atualizacao"][:10]) for m in meta["data_atualizacao"].values() if m.get("data_ultima_atualizacao")]
        return min(datas) if datas else None  # o módulo mais atrasado
    return None


def montar_fontes(retratos: dict[str, dict | None], config: Config, data: date) -> dict:
    fontes = {}
    for chave, nome in NOMES_FONTES.items():
        retrato = retratos.get(chave)
        cfg = config.fontes.fontes.get(chave)
        url = (cfg.url_consulta or cfg.url or cfg.base_url) if cfg else None
        if retrato is None:
            fontes[chave] = {"nome": nome, "url": url, "retrato": None, "coletado_em": None, "data_do_dado": None, "situacao": "sem_retrato"}
            continue
        dia = date.fromisoformat(retrato["data"])
        if cfg is not None and cfg.manual:  # D23: coleta feita por uma pessoa, fora da rotina diária; nunca "defasada" por não ser de hoje
            fontes[chave] = {"nome": nome, "url": url, "retrato": dia.isoformat(), "coletado_em": retrato["coletado_em"], "data_do_dado": dia.isoformat(), "situacao": "manual"}
            continue
        fontes[chave] = {
            "nome": nome, "url": url, "retrato": dia.isoformat(), "coletado_em": retrato["coletado_em"],
            "data_do_dado": (d.isoformat() if (d := _data_do_dado(chave, retrato)) else None),
            "situacao": "ok" if (data - dia).days < config.regras.coleta.retrato_valido_dias else "defasada",
        }
    return fontes


def montar_referencias(retrato_tesouro: dict | None) -> dict:
    """FPM e ITR por ano (centavos) e se o último mês pode estar incompleto. Só número de referência (spec §2)."""
    if retrato_tesouro is None:
        return {"transferencias_constitucionais": None}
    por_ano: dict[tuple[int, str], list[int]] = {}
    for linha in retrato_tesouro["dados"]["por_estado_municipio"]:
        if linha["TRANSFERENCIA"] in ("FPM", "ITR"):
            por_ano.setdefault((int(linha["ANO"]), linha["TRANSFERENCIA"]), []).append(centavos_reais(linha["VALOR"]))
    detalhe = [d for d in retrato_tesouro["dados"]["detalhe"] if d["SG_DETALHE"] == "FPM"]
    return {
        "transferencias_constitucionais": {
            "por_ano": [{"ano": ano, "transferencia": tipo, "valor": sum(v), "meses": len(v)} for (ano, tipo), v in sorted(por_ano.items())],
            "ultimo_mes": {
                "mes": retrato_tesouro["metadados"]["ultimo_mes_fpm"],
                "terceiro_decendio_zerado": (all(d["VA_TERCEIRO_DEC"] == 0 for d in detalhe) if detalhe else None),
            },
        }
    }


def montar_publicado(verbas: list[Verba], retratos: dict[str, dict | None], config: Config, data: date) -> dict:
    manuais = {c for c, f in config.fontes.fontes.items() if f.manual}  # a conferência semanal não diz quando o robô coletou (D23)
    coletas = [r["coletado_em"] for c, r in retratos.items() if r and c not in manuais]
    return {
        "versao": VERSAO,
        "data": data.isoformat(),
        "atualizado_em": max(coletas, key=datetime.fromisoformat) if coletas else None,
        "fontes": montar_fontes(retratos, config, data),
        "referencias": montar_referencias(retratos.get("tesouro_constitucionais")),
        "verbas": [v.para_dict() for v in verbas],
    }


# --- validação ---------------------------------------------------------------------------------


def _validador() -> Draft202012Validator:
    verba = json.loads((SCHEMAS / "verba.schema.json").read_text(encoding="utf-8"))
    publicado = json.loads((SCHEMAS / "publicado.schema.json").read_text(encoding="utf-8"))
    registro = Registry().with_resource(verba["$id"], Resource.from_contents(verba))
    return Draft202012Validator(publicado, registry=registro, format_checker=FormatChecker())


def validar_publicado(corpo: dict) -> None:
    """Valida o conjunto contra schemas/publicado.schema.json (que valida cada verba contra verba.schema.json)."""
    erros = sorted(_validador().iter_errors(corpo), key=lambda e: [str(p) for p in e.absolute_path])
    if erros:
        resumo = "; ".join(f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message[:120]}" for e in erros[:5])
        raise ValueError(f"publicado inválido ({len(erros)} erro(s)): {resumo}")
    ids = [v["id"] for v in corpo["verbas"]]
    if len(set(ids)) != len(ids):
        raise ValueError("publicado inválido: ids de verba repetidos")


# --- CSV ---------------------------------------------------------------------------------------


def reais_csv(centavos: int | None) -> str:
    """Centavos -> `1234567,89` (vírgula decimal, sem milhar: o Excel em português reconhece como número)."""
    if centavos is None:
        return ""
    return f"{'-' if centavos < 0 else ''}{abs(centavos) // 100},{abs(centavos) % 100:02d}"


def texto_seguro(texto: str | None) -> str:
    """Impede que o Excel trate texto da fonte como fórmula (começa com =, +, -, @, tabulação ou retorno)."""
    texto = texto or ""
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _sim_nao(valor: bool) -> str:
    return "sim" if valor else "não"


def linha_csv(verba: Verba, config: Config) -> list[str]:
    tax = config.taxonomia
    prazos = verba.prazos
    perda = verba.perda
    coleta = max(f.data_coleta for f in verba.fontes)
    return [
        verba.id,
        tax.tipos[verba.tipo],
        texto_seguro(verba.instrumento),
        texto_seguro(verba.nome),
        texto_seguro(verba.objeto),
        texto_seguro(verba.orgao_concedente),
        texto_seguro(verba.parlamentar),
        texto_seguro(verba.numero_instrumento),
        tax.rotulo_status(verba.status_site, verba.status_fonte),
        texto_seguro(verba.status_fonte),
        _sim_nao(verba.em_risco),
        texto_seguro(" | ".join(m.texto for m in (verba.motivos_risco or []))),
        reais_csv(verba.valor_total),
        reais_csv(verba.valor_contrapartida),
        reais_csv(verba.valor_liberado),
        reais_csv(verba.valor_executado),
        reais_csv(verba.valor_devolvido),
        *((getattr(prazos, p).isoformat() if prazos and getattr(prazos, p) else "") for p in PRAZOS),
        "" if verba.execucao_fisica_pct is None else f"{verba.execucao_fisica_pct:.2f}".replace(".", ","),
        tax.categorias[perda.categoria].rotulo if perda else "",
        texto_seguro(perda.texto) if perda else "",
        perda.evitavel if perda else "",
        perda.data.isoformat() if perda else "",
        reais_csv(perda.valor_perdido) if perda else "",
        _sim_nao(perda.gerado_por_ia) if perda else "",
        texto_seguro(perda.revisado_por) if perda else "",
        perda.revisado_em.isoformat() if perda and perda.revisado_em else "",
        texto_seguro("; ".join(f.nome for f in verba.fontes)),
        coleta.isoformat(timespec="seconds"),
    ]


def publicar(verbas: list[Verba], retratos: dict[str, dict | None], config: Config, data: date, raiz: Path) -> ResultadoPublicacao:
    """Valida e grava `verbas.json` e `verbas.csv`. Falha de validação não grava nada."""
    corpo = montar_publicado(verbas, retratos, config, data)
    validar_publicado(corpo)
    texto_json = json.dumps(corpo, ensure_ascii=False, indent=1) + "\n"

    def escrever_json(caminho: Path) -> None:
        caminho.write_text(texto_json, encoding="utf-8", newline="\n")

    def escrever_csv(caminho: Path) -> None:
        with caminho.open("w", encoding="utf-8-sig", newline="") as f:  # BOM para o Excel reconhecer UTF-8
            escritor = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
            escritor.writerow(CABECALHO_CSV)
            escritor.writerows(linha_csv(v, config) for v in verbas)

    # os dois temporários ficam prontos antes de qualquer um ser trocado: uma falha no CSV não deixa o JSON novo sozinho
    caminho_json, caminho_csv = raiz / ARQUIVO_JSON, raiz / ARQUIVO_CSV
    caminho_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_json, tmp_csv = caminho_json.with_name(caminho_json.name + ".tmp"), caminho_csv.with_name(caminho_csv.name + ".tmp")
    try:
        escrever_json(tmp_json)
        escrever_csv(tmp_csv)
    except Exception:
        tmp_json.unlink(missing_ok=True)
        tmp_csv.unlink(missing_ok=True)
        raise
    os.replace(tmp_json, caminho_json)
    os.replace(tmp_csv, caminho_csv)
    return ResultadoPublicacao(caminho_json, caminho_csv, len(verbas))
