"""Modelo Verba (spec §8), espelho de schemas/verba.schema.json.

Convenções:
- valores monetários em centavos (int estrito: float e bool são rejeitados);
- campo que o schema permite omitir mas não aceita `null` é tipado sem `None`, com default `None`;
  a exportação usa `exclude_unset`, então ele só sai no JSON se alguém o preencheu;
- campo que o schema aceita como `null` (ex.: `status_site`) é tipado com `None` e sai como `null`.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Centavos = Annotated[int, Field(ge=0, strict=True)]

Tipo = Literal[
    "voluntaria",
    "emenda_finalidade",
    "emenda_pix",
    "fundo_a_fundo",
    "programa_adesao",
    "constitucional",
]
StatusSite = Literal["oportunidade", "proposta", "aprovada", "execucao", "prestacao", "concluida", "perdida"]
CodigoRisco = Literal["prazo_proximo", "cauc_sem_comprovacao", "obra_parada", "impedimento_emenda"]
Categoria = Literal[
    "prazo_proposta",
    "reprovacao_tecnica",
    "impedimento_emenda",
    "cauc",
    "clausula_suspensiva",
    "execucao_nao_iniciada",
    "contrapartida",
    "glosa_devolucao",
    "decisao_externa",
    "em_apuracao",
]
Evitavel = Literal["sim", "em_parte", "nao", "indeterminado"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FonteRef(_Base):
    nome: str
    url: str
    data_coleta: AwareDatetime


class Citacao(_Base):
    n: int = Field(ge=1)
    documento_id: str
    titulo: str
    url: str
    trecho: str = Field(min_length=3)


class MotivoRisco(_Base):
    codigo: CodigoRisco
    texto: str
    data_limite: date = Field(default=None)


class Prazos(_Base):
    proposta: date = Field(default=None)
    assinatura: date = Field(default=None)
    clausula_suspensiva: date = Field(default=None)
    fim_vigencia: date = Field(default=None)
    prestacao_contas: date = Field(default=None)
    adesao: date = Field(default=None)


class Perda(_Base):
    categoria: Categoria
    texto: str
    citacoes: list[Citacao]
    evitavel: Evitavel
    data: date
    valor_perdido: Centavos
    gerado_por_ia: bool
    revisado_por: str | None = None
    revisado_em: date | None = None


class Historico(_Base):
    data: date
    de: str | None = None
    para: str
    fonte: str
    nota: str | None = None


class Verba(_Base):
    id: str = Field(pattern=r"^[a-z_]+-[A-Za-z0-9._-]+$")
    fonte: str
    id_fonte: str
    numero_instrumento: str | None = None
    nome: str
    objeto: str | None = None
    tipo: Tipo
    area: str | None = None
    orgao_concedente: str | None = None
    parlamentar: str | None = None
    valor_total: Centavos
    valor_contrapartida: Centavos = Field(default=None)
    valor_liberado: Centavos = Field(default=None)
    valor_executado: Centavos = Field(default=None)
    valor_devolvido: Centavos = Field(default=None)
    status_site: StatusSite | None
    status_fonte: str
    em_risco: bool
    motivos_risco: list[MotivoRisco] = Field(default=None)
    prazos: Prazos = Field(default=None)
    execucao_fisica_pct: float | None = Field(default=None, ge=0, le=100)
    perda: Perda | None = None
    historico: list[Historico]
    fontes: list[FonteRef] = Field(min_length=1)

    def para_dict(self) -> dict:
        """Dicionário JSON-compatível que valida em schemas/verba.schema.json."""
        return self.model_dump(mode="json", exclude_unset=True)

    def para_json(self) -> str:
        return self.model_dump_json(exclude_unset=True)
