"""Normalização: retratos brutos -> `Verba[]` (spec §4, §8, §9; plano T2.2; decisões D8, D10, D11, D12).

Entrada: o último retrato válido de cada fonte em `dados/brutos/<fonte>/` (spec §9: fonte sem retrato do dia
usa o último que existe). Saída: `Normalizacao` com as verbas, a lista de situações não mapeadas e avisos.

Nesta etapa a verba sai sem risco, sem perda e sem histórico (T2.3 e T2.4): `em_risco=False`, `historico=[]`.

Fontes que criam verbas: Siconv (propostas e convênios, recorte da spec §2), `parcerias`, `fundoafundo` e as
oportunidades (programas do Siconv). Portal da Transparência e Obrasgov só **complementam** verbas do Siconv
(D11, D8). O CAUC e o Tesouro não são verbas. As propostas do Novo PAC Seleções ficam só no bruto (D12).
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from nucleo.config import Config, carregar_config, normalizar_situacao
from nucleo.dinheiro import centavos_reais, centavos_texto
from nucleo.modelo import FonteRef, Verba

RAIZ = Path(__file__).resolve().parents[1]
FONTES_BRUTAS = ("transferegov_discricionarias", "transferegov_api", "portal_transparencia", "obrasgov", "cauc", "tesouro_constitucionais")
CHAVE_SICONV_PROPOSTA = "transferegov_discricionarias_proposta"
CHAVE_SICONV_CONVENIO = "transferegov_discricionarias_convenio"
CHAVE_PARCERIAS = "transferegov_parcerias"
CHAVE_FUNDOAFUNDO = "transferegov_fundoafundo"
JANELAS_PROGRAMA = ("RECEB_PROP", "EMENDA_PAR", "BENEF_ESP")
NOME_MAX = 140
# campos opcionais do modelo que o schema não aceita como null: só entram quando há valor
_SO_COM_VALOR = ("valor_contrapartida", "valor_liberado", "valor_executado", "valor_devolvido", "execucao_fisica_pct")


@dataclass
class SituacaoNaoMapeada:
    """Uma situação de uma fonte que `status_map.yaml` ainda não conhece (spec §4)."""

    fonte: str  # chave de config/status_map.yaml
    campo: str
    valor: str
    verbas: list[str] = field(default_factory=list)


@dataclass
class ObraLigada:
    """Obra do Obrasgov ligada a uma verba do Siconv (D8): o que a regra `obra_parada` precisa saber."""

    id_projeto: str
    situacao: str | None  # `situacao` do projeto: Cadastrada, Em execução, Paralisada...
    ultima_atualizacao: date | None  # maior `dt_atualizacao_execucao` (ou, sem ela, `dt_cadastro_execucao`); None: sem execução física
    paralisada_desde: date | None  # data do último registro de paralisação no histórico, se houver


@dataclass
class ImpedimentoEmenda:
    """Situação de impedimento técnico de uma emenda (módulo `especiais`). Ainda sem fonte real: ver D13."""

    situacao: str  # situação atual do plano de ação (`IMPEDIDO` = impedimento não superado)
    motivo: str | None = None


@dataclass
class Normalizacao:
    data: date
    verbas: list[Verba]
    nao_mapeadas: list[SituacaoNaoMapeada]
    avisos: list[str]
    retratos: dict[str, date | None]  # fonte -> data do retrato usado (None: sem retrato)
    obras: dict[str, ObraLigada] = field(default_factory=dict)  # id da verba -> obra ligada
    impedimentos: dict[str, ImpedimentoEmenda] = field(default_factory=dict)  # id da verba -> impedimento (vazio até haver emendas Pix)


# --- utilidades --------------------------------------------------------------------------------


def data_br(texto: str | None) -> date | None:
    """`dd/mm/aaaa` (Siconv) ou `aaaa-mm-dd[...]` (APIs) -> date; vazio -> None; outro formato é erro."""
    if not texto or not texto.strip():
        return None
    texto = texto.strip()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", texto):
        dia, mes, ano = texto.split("/")
        return date(int(ano), int(mes), int(dia))
    if re.match(r"\d{4}-\d{2}-\d{2}", texto):
        return date.fromisoformat(texto[:10])
    raise ValueError(f"data em formato desconhecido: {texto!r}")


def normalizar_numero(numero: str | None) -> str:
    """Chave de junção entre fontes: sem zeros à esquerda (`04431/2016` e `4431/2016` são o mesmo número)."""
    return (numero or "").strip().lstrip("0")


def resumo(texto: str | None, limite: int = NOME_MAX) -> str:
    """Primeira linha útil do texto em até `limite` caracteres, cortando em palavra."""
    limpo = re.sub(r"\s+", " ", texto or "").strip()
    if len(limpo) <= limite:
        return limpo
    corte = limpo[:limite].rsplit(" ", 1)[0].rstrip(",;:- ")
    return f"{corte}…"


def _limpar(campos: dict) -> dict:
    return {k: v for k, v in campos.items() if not (k in _SO_COM_VALOR and v is None)}


def _fonte(nome: str, url: str, retrato: dict) -> dict:
    return {"nome": nome, "url": url, "data_coleta": retrato["coletado_em"]}


def _id(prefixo: str, id_fonte: str) -> str:
    return f"{prefixo}-{id_fonte}"


# --- leitura dos retratos ----------------------------------------------------------------------


def carregar_retratos(raiz: Path, data: date) -> dict[str, dict | None]:
    """Último retrato com data <= `data` de cada fonte (spec §9); None se a fonte nunca foi coletada."""
    retratos: dict[str, dict | None] = {}
    for fonte in FONTES_BRUTAS:
        candidatos = sorted(p for p in (raiz / "dados" / "brutos" / fonte).glob("????-??-??.json") if p.stem <= data.isoformat())
        retratos[fonte] = json.loads(candidatos[-1].read_text(encoding="utf-8")) if candidatos else None
    return retratos


# --- status ------------------------------------------------------------------------------------


class MapaStatus:
    """`status_map.yaml` pronto para consulta; guarda as situações que não casaram."""

    def __init__(self, config: Config) -> None:
        self._config = config.status_map.fontes
        self._tabelas = {
            chave: {normalizar_situacao(s): status for status, situacoes in fonte.mapa.items() for s in situacoes}
            for chave, fonte in self._config.items()
        }
        self._nao_mapeadas: dict[tuple[str, str], SituacaoNaoMapeada] = {}

    def mapear(self, chave: str, situacao: str | None, verba_id: str) -> str | None:
        """status_site da situação, ou None (e registro no relatório) se o mapa não a conhece."""
        valor = (situacao or "").strip()
        status = self._tabelas[chave].get(normalizar_situacao(valor)) if valor else None
        if status is None:
            campo = self._config[chave].campo or "?"
            registro = self._nao_mapeadas.setdefault((chave, valor), SituacaoNaoMapeada(chave, campo, valor or "(vazia)"))
            registro.verbas.append(verba_id)
        return status

    def nao_mapeadas(self) -> list[SituacaoNaoMapeada]:
        return sorted(self._nao_mapeadas.values(), key=lambda r: (r.fonte, r.valor))


def relatorio_nao_mapeadas(nao_mapeadas: list[SituacaoNaoMapeada]) -> str:
    """Texto do relatório de situações não mapeadas (spec §4)."""
    if not nao_mapeadas:
        return "Situações não mapeadas: nenhuma."
    linhas = [f"Situações não mapeadas: {len(nao_mapeadas)} (as verbas saem com status_site nulo e o selo \"situação em análise\")"]
    for r in nao_mapeadas:
        exemplo = ", ".join(r.verbas[:3]) + (f" e mais {len(r.verbas) - 3}" if len(r.verbas) > 3 else "")
        linhas.append(f"  - {r.fonte} / {r.campo} = {r.valor!r}: {len(r.verbas)} verba(s) ({exemplo})")
    return "\n".join(linhas)


# --- contexto ----------------------------------------------------------------------------------


@dataclass
class _Contexto:
    config: Config
    data: date
    mapa: MapaStatus
    avisos: list[str] = field(default_factory=list)

    @property
    def inicio_recorte(self) -> date:
        return self.config.regras.municipio.inicio_recorte

    @property
    def cnpj_prefeitura(self) -> str | None:
        return self.config.regras.municipio.cnpj_prefeitura


# --- Siconv ------------------------------------------------------------------------------------


def _por_chave(registros: list[dict], chave: str) -> dict[str, list[dict]]:
    agrupado: dict[str, list[dict]] = defaultdict(list)
    for r in registros:
        agrupado[r[chave]].append(r)
    return agrupado


def _escolher_convenio(candidatos: list[dict], ctx: _Contexto, id_proposta: str) -> dict | None:
    if not candidatos:
        return None
    if len(candidatos) > 1:
        ctx.avisos.append(f"Siconv: proposta {id_proposta} tem {len(candidatos)} convênios; usado o ativo (ou o de maior NR_CONVENIO)")
        candidatos = sorted(candidatos, key=lambda c: (c["INSTRUMENTO_ATIVO"] == "SIM", int(c["NR_CONVENIO"])))
    return candidatos[-1]


def _verbas_siconv(retrato: dict, ctx: _Contexto) -> list[tuple[Verba, dict | None, dict]]:
    """Verbas das propostas do Siconv no recorte. Devolve (verba, convênio ou None, proposta) para as junções."""
    d = retrato["dados"]
    convenios = _por_chave(d["convenio"], "ID_PROPOSTA")
    emendas = _por_chave(d["emenda"], "ID_PROPOSTA")
    meta = retrato["metadados"]
    carga = (meta.get("data_carga") or "")[:10]
    nome_fonte = "Transferegov — Discricionárias e Legais" + (f" (carga de {carga})" if carga else "")
    url = ctx.config.fontes.fontes["transferegov_discricionarias"].url
    saida = []
    for proposta in [*d["proposta"], *d["proposta_cancelada"]]:
        id_proposta = proposta["ID_PROPOSTA"]
        convenio = _escolher_convenio(convenios.get(id_proposta, []), ctx, id_proposta)
        data_proposta = data_br(proposta["DIA_PROPOSTA"])
        ativo = convenio is not None and convenio["INSTRUMENTO_ATIVO"] == "SIM"
        if not ((data_proposta and data_proposta >= ctx.inicio_recorte) or ativo):
            continue  # spec §2: proposta de 2024 em diante ou instrumento ainda ativo
        verba_id = _id("transferegov_discricionarias", id_proposta)
        objeto = re.sub(r"\s+", " ", proposta["OBJETO_PROPOSTA"]).strip()
        if convenio:
            chave, situacao = CHAVE_SICONV_CONVENIO, convenio["SIT_CONVENIO"]
        else:
            chave, situacao = CHAVE_SICONV_PROPOSTA, proposta["SIT_PROPOSTA"]
        deputados = list(dict.fromkeys(e["NOME_PARLAMENTAR"].strip() for e in emendas.get(id_proposta, []) if e["NOME_PARLAMENTAR"].strip()))
        origem = convenio or proposta
        sufixo = "CONV" if convenio else "PROP"
        clausula = data_br(convenio["DATA_SUSPENSIVA"]) if convenio and not convenio["DATA_RETIRADA_SUSPENSIVA"] else None
        prazos = {
            "proposta": data_proposta,
            "assinatura": data_br(convenio["DIA_ASSIN_CONV"]) if convenio else None,
            "clausula_suspensiva": clausula,
            "fim_vigencia": data_br(convenio["DIA_FIM_VIGENC_CONV"]) if convenio else None,
            "prestacao_contas": data_br(convenio["DIA_LIMITE_PREST_CONTAS"]) if convenio else None,
        }
        campos = {
            "id": verba_id,
            "fonte": "transferegov_discricionarias",
            "id_fonte": id_proposta,
            "numero_instrumento": convenio["NR_CONVENIO"] if convenio else proposta["NR_PROPOSTA"],
            "nome": resumo(objeto) or f"Proposta {proposta['NR_PROPOSTA']}",
            "objeto": objeto or None,
            "tipo": "emenda_finalidade" if id_proposta in emendas else "voluntaria",
            "instrumento": proposta["MODALIDADE"] or None,
            "orgao_concedente": proposta["DESC_ORGAO_SUP"] or None,
            "parlamentar": ", ".join(deputados) or None,
            "valor_total": centavos_texto(origem[f"VL_GLOBAL_{sufixo}"]),
            "valor_contrapartida": centavos_texto(origem[f"VL_CONTRAPARTIDA_{sufixo}"]),
            "valor_liberado": centavos_texto(convenio["VL_DESEMBOLSADO_CONV"]) if convenio else None,
            "valor_devolvido": centavos_texto(convenio["VL_SALDO_REMAN_TESOURO"]) if convenio else None,
            "status_site": ctx.mapa.mapear(chave, situacao, verba_id),
            "status_fonte": situacao or "(vazia)",
            "em_risco": False,
            "prazos": {k: v for k, v in prazos.items() if v is not None},
            "historico": [],
            "fontes": [_fonte(nome_fonte, url, retrato)],
        }
        saida.append((Verba.model_validate(_limpar(campos)), convenio, proposta))
    return saida


# --- junção com o Portal da Transparência (D11) ------------------------------------------------


def _juntar_portal(verbas_siconv: list[tuple[Verba, dict | None, dict]], portal: dict | None, ctx: _Contexto) -> None:
    """Atualiza `valor_liberado` e cita o Portal nos convênios que casam por proposta ou por processo."""
    if portal is None:
        ctx.avisos.append("Portal da Transparência sem retrato: valor_liberado fica como no Siconv")
        return
    convenios = portal["dados"]["convenios"]
    url = ctx.config.fontes.fontes["portal_transparencia"].base_url
    por_numero = _por_chave([{**c, "_k": normalizar_numero(c["dimConvenio"]["numero"])} for c in convenios], "_k")
    por_processo = _por_chave([{**c, "_k": normalizar_numero(c["numeroProcesso"])} for c in convenios if c.get("numeroProcesso")], "_k")
    usados: dict[int, str] = {}
    for verba, convenio, proposta in verbas_siconv:
        if convenio is None:
            continue
        achados = {}
        if proposta["NR_PROPOSTA"].strip():
            achados.update({c["id"]: c for c in por_numero.get(normalizar_numero(proposta["NR_PROPOSTA"]), [])})
        if convenio["NR_PROCESSO"].strip():
            achados.update({c["id"]: c for c in por_processo.get(normalizar_numero(convenio["NR_PROCESSO"]), [])})
        if len(achados) > 1:
            ctx.avisos.append(f"Portal: {len(achados)} convênios casam com {verba.id}; nenhum usado")
            continue
        if not achados:
            continue
        (c,) = achados.values()
        if c["id"] in usados:
            ctx.avisos.append(f"Portal: convênio {c['id']} casa com {usados[c['id']]} e {verba.id}; só o primeiro usado")
            continue
        usados[c["id"]] = verba.id
        liberado = centavos_reais(c["valorLiberado"])
        if liberado is not None:
            if verba.valor_liberado is not None and liberado < verba.valor_liberado:
                ctx.avisos.append(f"Portal: valorLiberado de {verba.id} ({liberado}) menor que o do Siconv ({verba.valor_liberado}); usado o do Portal")
            verba.valor_liberado = liberado
        verba.fontes.append(_fonte_modelo("Portal da Transparência", url, portal))


def _fonte_modelo(nome: str, url: str, retrato: dict) -> FonteRef:
    return FonteRef.model_validate(_fonte(nome, url, retrato))


# --- junção com o Obrasgov (D8) ----------------------------------------------------------------


def _juntar_obrasgov(verbas_siconv: list[tuple[Verba, dict | None, dict]], obras: dict | None, ctx: _Contexto) -> dict[str, ObraLigada]:
    """Percentual físico das obras em que a prefeitura é executora e que a ponte liga ao convênio.

    Devolve, por verba, os dados da obra ligada (insumo da regra `obra_parada`, T2.3).
    """
    ligadas: dict[str, ObraLigada] = {}
    if obras is None:
        ctx.avisos.append("Obrasgov sem retrato: execucao_fisica_pct fica vazio")
        return ligadas
    d = obras["dados"]
    url = ctx.config.fontes.fontes["obrasgov"].base_url
    ponte = {r["nr_instrumento"]: r["id_projeto_investimento"] for r in d["ponte_siconv"]}
    projetos = {p["id_projeto_investimento"]: p for p in d["projeto_investimento"]}
    execucoes = _por_chave(d["execucao_fisica"], "id_projeto_investimento")
    historicos = _por_chave(d["historico_situacao"], "id_projeto_investimento")
    for verba, convenio, _ in verbas_siconv:
        id_projeto = ponte.get(convenio["NR_CONVENIO"]) if convenio else None
        projeto = projetos.get(id_projeto) if id_projeto else None
        if projeto is None:
            continue
        executores = [e.get("cnpj_executor") for e in (projeto.get("executores") or [])]
        if ctx.cnpj_prefeitura not in executores:
            ctx.avisos.append(f"Obrasgov: projeto {id_projeto} ligado a {verba.id} não tem a prefeitura como executora; ignorado")
            continue
        registros = execucoes.get(id_projeto, [])
        atualizacao = None
        if registros:
            ultimo = max(registros, key=lambda r: (r.get("dt_atualizacao_execucao") or "", r.get("dt_cadastro_execucao") or ""))
            if ultimo.get("percentual_execucao_fisica") is not None:
                verba.execucao_fisica_pct = float(ultimo["percentual_execucao_fisica"])
            atualizacao = data_br(ultimo.get("dt_atualizacao_execucao") or ultimo.get("dt_cadastro_execucao"))
        paralisacoes = [data_br(h["data_historico_situacao_investimento"]) for h in historicos.get(id_projeto, []) if h.get("descricao_historico_situacao_investimento") == "Paralisada"]
        ligadas[verba.id] = ObraLigada(id_projeto, projeto.get("situacao"), atualizacao, max((x for x in paralisacoes if x), default=None))
        verba.fontes.append(_fonte_modelo("Obrasgov", url, obras))
    return ligadas


# --- Transferegov API: parcerias e fundo a fundo -----------------------------------------------


def _verbas_parcerias(retrato: dict, ctx: _Contexto) -> list[Verba]:
    d = retrato["dados"]
    parcerias = _por_chave(d["parcerias.parceria"], "id_proposta")
    programas = {p["id_programa"]: p for p in d["parcerias.programa"]}
    url = ctx.config.fontes.fontes["transferegov_api"].base_url + "/parcerias/docs"
    saida = []
    for proposta in d["parcerias.proposta"]:
        data_proposta = data_br(proposta["dt_proposta"])
        if data_proposta is None or data_proposta < ctx.inicio_recorte:
            continue
        id_proposta = str(proposta["id_proposta"])
        verba_id = _id("transferegov_parcerias", id_proposta)
        programa = programas.get(proposta["id_programa"], {})
        parceria = parcerias.get(proposta["id_proposta"], [None])[0]
        situacao = parceria["in_situacao_parceria"] if parceria else proposta["situacao_proposta"]
        valor = proposta["nr_vlr_total"] if proposta["nr_vlr_total"] is not None else proposta["vl_total_planejamento_gastos"]
        so_emenda = programa.get("qualificacao_beneficiario") == "Beneficiário de Emenda Parlamentar"
        campos = {
            "id": verba_id,
            "fonte": "transferegov_parcerias",
            "id_fonte": id_proposta,
            "numero_instrumento": str(parceria["cd_parceria"]) if parceria else None,
            "nome": resumo(proposta["ds_objeto"]) or f"Proposta {id_proposta}",
            "objeto": re.sub(r"\s+", " ", proposta["ds_objeto"] or "").strip() or None,
            "tipo": "emenda_finalidade" if so_emenda else "fundo_a_fundo",
            "instrumento": programa.get("tp_instrumento"),
            "orgao_concedente": programa.get("nm_ente_superior"),
            "valor_total": centavos_reais(valor),
            "status_site": ctx.mapa.mapear(CHAVE_PARCERIAS, situacao, verba_id),
            "status_fonte": situacao or "(vazia)",
            "em_risco": False,
            "prazos": {k: v for k, v in {"proposta": data_proposta, "assinatura": data_br(parceria["dh_assinatura"]) if parceria else None}.items() if v is not None},
            "historico": [],
            "fontes": [_fonte("Transferegov — Gestão de Parcerias (API)", url, retrato)],
        }
        saida.append(Verba.model_validate(_limpar(campos)))
    return saida


def _verbas_fundoafundo(retrato: dict, ctx: _Contexto) -> list[Verba]:
    d = retrato["dados"]
    termos = _por_chave(d["fundoafundo.termos_adesao"], "id_plano_acao")
    programas = {p["id_programa"]: p for p in d["fundoafundo.programas"]}
    url = ctx.config.fontes.fontes["transferegov_api"].base_url + "/fundoafundo/docs"
    saida = []
    for plano in d["fundoafundo.planos_acao"]:
        fim = data_br(plano["data_fim_vigencia_plano_acao"])
        inicio = data_br(plano["data_inicio_vigencia_plano_acao"])
        if not ((fim and fim >= ctx.inicio_recorte) or (inicio and inicio >= ctx.inicio_recorte)):
            continue  # a vigência não toca o recorte da spec §2
        id_plano = str(plano["id_plano_acao"])
        verba_id = _id("transferegov_fundoafundo", id_plano)
        programa = programas.get(plano["id_programa"], {})
        termo = (termos.get(plano["id_plano_acao"]) or [None])[0]
        situacao = plano["situacao_plano_acao"]
        campos = {
            "id": verba_id,
            "fonte": "transferegov_fundoafundo",
            "id_fonte": id_plano,
            "numero_instrumento": plano["codigo_plano_acao"],
            "nome": resumo(programa.get("nome_programa") or plano["objetivos_plano_acao"]) or f"Plano de ação {id_plano}",
            "objeto": re.sub(r"\s+", " ", plano["objetivos_plano_acao"] or "").strip() or None,
            "tipo": "fundo_a_fundo",
            "instrumento": programa.get("modalidade_programa"),
            "orgao_concedente": plano["nome_orgao_repassador_plano_acao"],
            "valor_total": centavos_reais(plano["valor_total_plano_acao"]),
            "valor_contrapartida": centavos_reais(plano["valor_recursos_proprios_plano_acao"]),
            "status_site": ctx.mapa.mapear(CHAVE_FUNDOAFUNDO, situacao, verba_id),
            "status_fonte": situacao or "(vazia)",
            "em_risco": False,
            "prazos": {k: v for k, v in {"assinatura": data_br(termo["data_assinatura_termo_adesao"]) if termo else None, "fim_vigencia": fim}.items() if v is not None},
            "historico": [],
            "fontes": [_fonte("Transferegov — Fundo a Fundo (API)", url, retrato)],
        }
        saida.append(Verba.model_validate(_limpar(campos)))
    return saida


# --- oportunidades (D10) -----------------------------------------------------------------------


def _janela_aberta(linha: dict, janela: str, data: date) -> date | None:
    """Fim da janela se ela está aberta em `data` (início vazio vale como já aberta); senão None."""
    fim, inicio = data_br(linha[f"DT_PROG_FIM_{janela}"]), data_br(linha[f"DT_PROG_INI_{janela}"])
    if fim is None or fim < data or (inicio is not None and inicio > data):
        return None
    return fim


def _verbas_oportunidades(retrato: dict, ctx: _Contexto) -> list[Verba]:
    """Programas `DISPONIBILIZADO` com janela de propostas aberta (as linhas já são de natureza municipal e da UF)
    ou dirigidos à prefeitura com alguma janela aberta. O fim da janela vira o prazo `adesao`."""
    d = retrato["dados"]
    dirigidos = {r["ID_PROGRAMA"] for r in d["programa_proponentes"]}
    meta = retrato["metadados"]
    carga = (meta.get("data_carga") or "")[:10]
    nome_fonte = "Transferegov — Programas (Siconv)" + (f" (carga de {carga})" if carga else "")
    url = ctx.config.fontes.fontes["transferegov_discricionarias"].url
    fins: dict[str, list[date]] = defaultdict(list)
    linhas: dict[str, dict] = {}
    for linha in d["programa"]:
        if linha["SIT_PROGRAMA"] != "DISPONIBILIZADO":
            continue
        id_programa = linha["ID_PROGRAMA"]
        abertas = {j: _janela_aberta(linha, j, ctx.data) for j in JANELAS_PROGRAMA}
        qualificantes = [fim for j, fim in abertas.items() if fim is not None and (j == "RECEB_PROP" or id_programa in dirigidos)]
        if qualificantes:
            fins[id_programa] += qualificantes
            linhas.setdefault(id_programa, linha)
    saida = []
    for id_programa, linha in sorted(linhas.items()):
        nome = re.sub(r"\s+", " ", linha["NOME_PROGRAMA"]).strip()
        saida.append(
            Verba.model_validate(
                _limpar(
                    {
                        "id": _id("siconv_programa", id_programa),
                        "fonte": "siconv_programa",
                        "id_fonte": id_programa,
                        "numero_instrumento": linha["COD_PROGRAMA"] or None,
                        "nome": resumo(nome) or f"Programa {id_programa}",
                        "objeto": nome or None,
                        "tipo": "programa_adesao",
                        "instrumento": linha["MODALIDADE_PROGRAMA"] or None,
                        "orgao_concedente": linha["DESC_ORGAO_SUP_PROGRAMA"] or None,
                        "valor_total": None,
                        "status_site": "oportunidade",
                        "status_fonte": linha["SIT_PROGRAMA"],
                        "em_risco": False,
                        "prazos": {"adesao": min(fins[id_programa])},
                        "historico": [],
                        "fontes": [_fonte(nome_fonte, url, retrato)],
                    }
                )
            )
        )
    return saida


# --- linha de comando --------------------------------------------------------------------------


def resumo_normalizacao(resultado: Normalizacao) -> str:
    """Texto do resumo da normalização: contagens, retratos usados, situações não mapeadas e avisos."""
    linhas = [
        f"Normalização de {resultado.data.isoformat()}: {len(resultado.verbas)} verbas",
        "Retratos usados: " + ", ".join(f"{f}={d.isoformat() if d else 'SEM RETRATO'}" for f, d in resultado.retratos.items()),
    ]
    for rotulo, valores in (("fonte", [v.fonte for v in resultado.verbas]), ("tipo", [v.tipo for v in resultado.verbas]), ("status", [str(v.status_site) for v in resultado.verbas])):
        contagem = sorted(((valores.count(x), x) for x in set(valores)), reverse=True)
        linhas.append(f"  por {rotulo}: " + ", ".join(f"{x}={c}" for c, x in contagem))
    linhas.append(relatorio_nao_mapeadas(resultado.nao_mapeadas))
    linhas += [f"AVISO: {aviso}" for aviso in resultado.avisos]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    """`python -m nucleo.normaliza`: normaliza os retratos mais recentes e imprime o resumo e o relatório.

    Nesta etapa (T2.2) não grava nada: risco, perda e publicação vêm nas T2.3 a T2.5.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="python -m nucleo.normaliza", description=main.__doc__.split("\n")[0])
    parser.add_argument("--data", type=date.fromisoformat, default=None, help="data de referência, AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--raiz", type=Path, default=RAIZ, help="raiz com dados/brutos (padrão: o repositório)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    data = args.data or date.today()
    retratos = carregar_retratos(args.raiz, data)
    print(resumo_normalizacao(normalizar(retratos, data=data)))
    return 0


# --- conjunto ----------------------------------------------------------------------------------


def normalizar(retratos: dict[str, dict | None], config: Config | None = None, data: date | None = None) -> Normalizacao:
    config = config or carregar_config()
    data = data or date.today()
    ctx = _Contexto(config, data, MapaStatus(config))
    verbas: list[Verba] = []
    obras: dict[str, ObraLigada] = {}

    siconv = retratos.get("transferegov_discricionarias")
    if siconv is None:
        ctx.avisos.append("Siconv sem nenhum retrato: sem convênios, propostas e oportunidades do Siconv (o Portal não os substitui, D11)")
    else:
        do_siconv = _verbas_siconv(siconv, ctx)
        _juntar_portal(do_siconv, retratos.get("portal_transparencia"), ctx)
        obras = _juntar_obrasgov(do_siconv, retratos.get("obrasgov"), ctx)
        verbas += [v for v, _, _ in do_siconv]
        verbas += _verbas_oportunidades(siconv, ctx)

    api = retratos.get("transferegov_api")
    if api is None:
        ctx.avisos.append("Transferegov API sem nenhum retrato: sem verbas de parcerias e fundo a fundo")
    else:
        verbas += _verbas_parcerias(api, ctx)
        verbas += _verbas_fundoafundo(api, ctx)
        for recurso in ("especiais.planos_acao", "especiais.planos_trabalho"):
            if api["dados"].get(recurso):
                ctx.avisos.append(f"Transferegov {recurso} tem {len(api['dados'][recurso])} registro(s) e a normalização ainda não os trata (emendas Pix)")

    ids = [v.id for v in verbas]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ValueError(f"ids de verba repetidos: {repetidos}")
    return Normalizacao(
        data=data,
        verbas=sorted(verbas, key=lambda v: v.id),
        nao_mapeadas=ctx.mapa.nao_mapeadas(),
        avisos=ctx.avisos,
        retratos={f: (date.fromisoformat(r["data"]) if r else None) for f, r in retratos.items()},
        obras=obras,
    )


if __name__ == "__main__":
    raise SystemExit(main())
