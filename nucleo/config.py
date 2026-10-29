"""Leitura e validação de config/*.yaml (spec §4, §5, §6, §7; plano T0.3).

Qualquer problema (arquivo ausente, YAML inválido, chave faltando ou desconhecida, valor fora do
esperado) vira `ConfigErro` com o arquivo e o caminho da chave na mensagem.
"""

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from nucleo.modelo import Categoria, CodigoRisco, Evitavel, StatusSite, Tipo

DIRETORIO_PADRAO = Path(__file__).resolve().parents[1] / "config"

NomePrazo = Literal["proposta", "assinatura", "clausula_suspensiva", "fim_vigencia", "prestacao_contas", "adesao"]


class ConfigErro(Exception):
    """Configuração inválida; a mensagem diz o arquivo e a chave."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


def normalizar_situacao(texto: str) -> str:
    """Comparação do status_map: sem acentos, sem diferenciar caixa, espaços extras removidos."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().casefold()


# --- regras.yaml -----------------------------------------------------------------------------


class Municipio(_Base):
    nome: str
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    codigo_ibge: str = Field(pattern=r"^\d{7}$")
    cnpj_prefeitura: str | None
    cnpjs_fundos: list[str] = Field(default_factory=list, description="Fundos municipais que recebem em nome do município")
    inicio_recorte: date

    @field_validator("cnpj_prefeitura")
    @classmethod
    def _cnpj_prefeitura_14_digitos(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"\d{14}", v):
            raise ValueError("CNPJ deve ter 14 dígitos, sem pontuação")
        return v

    @field_validator("cnpjs_fundos")
    @classmethod
    def _cnpjs_fundos_14_digitos(cls, v: list[str]) -> list[str]:
        ruins = [c for c in v if not re.fullmatch(r"\d{14}", c)]
        if ruins:
            raise ValueError(f"CNPJ deve ter 14 dígitos, sem pontuação: {ruins}")
        return v


class TextosRisco(_Base):
    prazo_proximo: str
    cauc_sem_comprovacao: str
    obra_parada: str
    impedimento_emenda: str


class Risco(_Base):
    dias_alerta_prazo: int = Field(gt=0)
    dias_obra_parada: int = Field(gt=0)
    cauc_tipos: list[Tipo]
    cauc_status: list[StatusSite]
    prazos_monitorados: list[NomePrazo]
    textos: TextosRisco


class RegraPerda(_Base):
    valor_perdido: Literal["nao_liberado_mais_devolvido"]


class RegraCuradoria(_Base):
    modelo: str
    max_tokens: int = Field(gt=0)
    temperatura: float = Field(ge=0)
    auto_publicar: bool
    auto_publicar_categorias: list[Categoria]
    texto_em_apuracao: str
    selo_ia: str


class RegraColeta(_Base):
    horario: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    fuso: str
    portal_transparencia_req_por_min: int = Field(gt=0)
    tentativas: int = Field(ge=1)
    backoff_inicial_s: float = Field(gt=0)

    @field_validator("fuso")
    @classmethod
    def _fuso_existe(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"fuso horário desconhecido: {v}") from e
        return v


class Regras(_Base):
    municipio: Municipio
    risco: Risco
    perda: RegraPerda
    curadoria: RegraCuradoria
    coleta: RegraColeta


# --- status_map.yaml -------------------------------------------------------------------------


class FonteStatus(_Base):
    verificado: date | None
    campo: str | None
    mapa: dict[StatusSite, list[str]]
    sinais_risco: list[str] = []

    @model_validator(mode="after")
    def _situacao_em_um_so_status(self):
        vistas: dict[str, str] = {}
        for status, situacoes in self.mapa.items():
            for s in situacoes:
                chave = normalizar_situacao(s)
                if chave in vistas and vistas[chave] != status:
                    raise ValueError(f"situação {s!r} aparece em '{vistas[chave]}' e em '{status}'")
                vistas[chave] = status
        return self


class StatusMap(_Base):
    status_validos: list[StatusSite]
    fontes: dict[str, FonteStatus]

    @model_validator(mode="after")
    def _mapas_usam_status_validos(self):
        for nome, fonte in self.fontes.items():
            for status in fonte.mapa:
                if status not in self.status_validos:
                    raise ValueError(f"fontes.{nome}.mapa: status '{status}' não está em status_validos")
        return self


# --- taxonomia.yaml --------------------------------------------------------------------------


class CategoriaPerda(_Base):
    rotulo: str
    descricao: str
    evitavel_tipico: Evitavel


class Taxonomia(_Base):
    categorias: dict[Categoria, CategoriaPerda]

    @model_validator(mode="after")
    def _todas_as_categorias(self):
        faltam = set(get_args(Categoria)) - set(self.categorias)
        if faltam:
            raise ValueError(f"categorias ausentes na taxonomia: {', '.join(sorted(faltam))}")
        return self


# --- fontes.yaml -----------------------------------------------------------------------------


class AuthFonte(_Base):
    header: str
    env: str


class FonteConfig(_Base):
    base_url: str | None = None
    modulos: list[str] | None = None
    docs: str | None = None
    tipo: str | None = None
    url: str | None = None
    url_teste: str | None = None   # endereço que responde 200 sem parâmetros, para scripts/teste_acesso.py
    auth: AuthFonte | None = None
    limite_req_min: int | None = Field(default=None, gt=0)
    ativa: bool


class Fontes(_Base):
    fontes: dict[str, FonteConfig]


# --- conjunto --------------------------------------------------------------------------------


class Config(_Base):
    regras: Regras
    status_map: StatusMap
    taxonomia: Taxonomia
    fontes: Fontes

    @model_validator(mode="after")
    def _coerencia_entre_arquivos(self):
        limite = self.regras.coleta.portal_transparencia_req_por_min
        portal = self.fontes.fontes.get("portal_transparencia")
        if portal and portal.limite_req_min and limite > portal.limite_req_min:
            raise ValueError(
                f"regras.coleta.portal_transparencia_req_por_min ({limite}) maior que "
                f"fontes.portal_transparencia.limite_req_min ({portal.limite_req_min})"
            )
        return self


_ARQUIVOS = {
    "regras": ("regras.yaml", Regras),
    "status_map": ("status_map.yaml", StatusMap),
    "taxonomia": ("taxonomia.yaml", Taxonomia),
    "fontes": ("fontes.yaml", Fontes),
}


def _traduzir(erro: dict) -> str:
    tipo = erro["type"]
    if tipo == "missing":
        return "chave obrigatória ausente"
    if tipo == "extra_forbidden":
        return "chave desconhecida (erro de digitação?)"
    return erro["msg"].removeprefix("Value error, ")


def _carregar_arquivo(diretorio: Path, nome: str, modelo: type[_Base]):
    caminho = diretorio / nome
    rotulo = f"config/{nome}"
    try:
        texto = caminho.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigErro(f"{rotulo}: arquivo não encontrado em {caminho}") from None
    try:
        dados = yaml.safe_load(texto)
    except yaml.YAMLError as e:
        raise ConfigErro(f"{rotulo}: YAML inválido: {e}") from e
    if not isinstance(dados, dict):
        raise ConfigErro(f"{rotulo}: o arquivo deve ser um mapa de chaves")
    try:
        return modelo.model_validate(dados)
    except ValidationError as e:
        linhas = [
            f"{rotulo}: {'.'.join(str(p) for p in err['loc']) or '(raiz)'}: {_traduzir(err)}"
            for err in e.errors()
        ]
        raise ConfigErro("\n".join(linhas)) from e


def carregar_config(diretorio: Path | str = DIRETORIO_PADRAO) -> Config:
    """Carrega e valida os quatro arquivos de `diretorio` (padrão: config/ da raiz do repositório)."""
    diretorio = Path(diretorio)
    partes = {chave: _carregar_arquivo(diretorio, nome, modelo) for chave, (nome, modelo) in _ARQUIVOS.items()}
    try:
        return Config(**partes)
    except ValidationError as e:
        raise ConfigErro("config: " + "; ".join(_traduzir(err) for err in e.errors())) from e
