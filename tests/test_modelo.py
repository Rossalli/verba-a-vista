import json
import typing
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from nucleo import modelo
from nucleo.modelo import Verba

RAIZ = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((RAIZ / "schemas" / "verba.schema.json").read_text(encoding="utf-8"))
VALIDADOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

MINIMO = {
    "id": "transferegov-123456",
    "fonte": "transferegov",
    "id_fonte": "123456",
    "nome": "Pavimentação",
    "tipo": "voluntaria",
    "valor_total": 150000000,
    "status_site": "aprovada",
    "status_fonte": "Assinado",
    "em_risco": False,
    "historico": [],
    "fontes": [
        {
            "nome": "Transferegov",
            "url": "https://api-publica.transferegov.gestao.gov.br/parcerias/docs",
            "data_coleta": "2026-10-29T06:00:00-03:00",
        }
    ],
}

COMPLETO = {
    **MINIMO,
    "numero_instrumento": "123456/2024",
    "objeto": "Pavimentação de vias urbanas",
    "area": "infraestrutura",
    "orgao_concedente": "Ministério das Cidades",
    "parlamentar": None,
    "valor_contrapartida": 5000000,
    "valor_liberado": 0,
    "valor_executado": 0,
    "valor_devolvido": 0,
    "status_site": "perdida",
    "em_risco": True,
    "motivos_risco": [
        {"codigo": "prazo_proximo", "texto": "Prazo em 38 dias", "data_limite": "2026-12-06"},
        {"codigo": "cauc_sem_comprovacao", "texto": "CAUC: item 4.2 sem comprovação (Regularidade Previdenciária)"},
    ],
    "prazos": {"proposta": "2024-03-01", "fim_vigencia": "2027-01-31"},
    "execucao_fisica_pct": 12.5,
    "perda": {
        "categoria": "clausula_suspensiva",
        "texto": "O instrumento foi extinto [1].",
        "citacoes": [
            {
                "n": 1,
                "documento_id": "doc-1",
                "titulo": "Situação da proposta",
                "url": "https://example.gov.br/doc-1",
                "trecho": "Convênio Extinto",
            }
        ],
        "evitavel": "sim",
        "data": "2026-10-01",
        "valor_perdido": 150000000,
        "gerado_por_ia": True,
        "revisado_por": None,
        "revisado_em": None,
    },
    "historico": [
        {"data": "2026-10-01", "de": "aprovada", "para": "perdida", "fonte": "transferegov", "nota": None}
    ],
}


def validar_no_schema(dados: dict) -> None:
    erros = sorted(VALIDADOR.iter_errors(dados), key=lambda e: list(e.path))
    assert not erros, [f"{list(e.path)}: {e.message}" for e in erros]


def com(base: dict, **mudancas) -> dict:
    novo = deepcopy(base)
    novo.update(mudancas)
    return novo


def test_exemplo_minimo_exporta_json_valido_no_schema():
    verba = Verba.model_validate(MINIMO)
    saida = verba.para_dict()
    validar_no_schema(saida)
    # campos opcionais não preenchidos não saem como null (o schema não aceita null neles)
    assert "valor_contrapartida" not in saida
    assert "prazos" not in saida
    assert "motivos_risco" not in saida


def test_exemplo_completo_exporta_json_valido_no_schema():
    verba = Verba.model_validate(COMPLETO)
    validar_no_schema(verba.para_dict())
    validar_no_schema(json.loads(verba.para_json()))


def test_ida_e_volta_preserva_os_dados():
    verba = Verba.model_validate_json(Verba.model_validate(COMPLETO).para_json())
    assert verba.para_dict() == Verba.model_validate(COMPLETO).para_dict()


def test_rejeita_status_site_invalido():
    with pytest.raises(ValidationError):
        Verba.model_validate(com(MINIMO, status_site="em_risco"))


def test_status_site_nulo_e_aceito_e_exportado_como_null():
    saida = Verba.model_validate(com(MINIMO, status_site=None)).para_dict()
    assert saida["status_site"] is None
    validar_no_schema(saida)


def test_status_site_e_obrigatorio():
    dados = deepcopy(MINIMO)
    del dados["status_site"]
    with pytest.raises(ValidationError):
        Verba.model_validate(dados)


@pytest.mark.parametrize("campo", ["id", "nome", "tipo", "valor_total", "status_fonte", "em_risco", "historico", "fontes"])
def test_campos_obrigatorios(campo):
    dados = deepcopy(MINIMO)
    del dados[campo]
    with pytest.raises(ValidationError):
        Verba.model_validate(dados)


@pytest.mark.parametrize(
    "mudancas",
    [
        {"tipo": "outro"},
        {"id": "sem-prefixo maiusculo ERRADO"},
        {"id": "Maiuscula-1"},
        {"valor_total": -1},
        {"valor_total": 10.5},
        {"valor_total": True},
        {"valor_total": "100"},
        {"valor_contrapartida": None},
        {"execucao_fisica_pct": 101},
        {"execucao_fisica_pct": -1},
        {"fontes": []},
        {"campo_inexistente": 1},
    ],
)
def test_rejeita_valores_fora_do_schema(mudancas):
    with pytest.raises(ValidationError):
        Verba.model_validate(com(MINIMO, **mudancas))


def test_rejeita_data_de_coleta_sem_fuso():
    fonte = {**MINIMO["fontes"][0], "data_coleta": "2026-10-29T06:00:00"}
    with pytest.raises(ValidationError):
        Verba.model_validate(com(MINIMO, fontes=[fonte]))


def test_rejeita_motivo_de_risco_e_categoria_de_perda_invalidos():
    with pytest.raises(ValidationError):
        Verba.model_validate(com(COMPLETO, motivos_risco=[{"codigo": "x", "texto": "t"}]))
    perda = {**COMPLETO["perda"], "categoria": "inventada"}
    with pytest.raises(ValidationError):
        Verba.model_validate(com(COMPLETO, perda=perda))


def test_rejeita_citacao_com_trecho_curto():
    perda = deepcopy(COMPLETO["perda"])
    perda["citacoes"][0]["trecho"] = "ab"
    with pytest.raises(ValidationError):
        Verba.model_validate(com(COMPLETO, perda=perda))


def test_atribuicao_posterior_entra_na_exportacao():
    verba = Verba.model_validate(MINIMO)
    verba.valor_liberado = 100
    assert verba.para_dict()["valor_liberado"] == 100


def test_valores_literais_batem_com_os_enums_do_schema():
    props = SCHEMA["properties"]
    perda = props["perda"]["properties"]
    risco = props["motivos_risco"]["items"]["properties"]["codigo"]["enum"]
    esperado = {
        modelo.Tipo: props["tipo"]["enum"],
        modelo.StatusSite: [v for v in props["status_site"]["enum"] if v is not None],
        modelo.CodigoRisco: risco,
        modelo.Categoria: perda["categoria"]["enum"],
        modelo.Evitavel: perda["evitavel"]["enum"],
    }
    for literal, enum in esperado.items():
        assert list(typing.get_args(literal)) == enum
