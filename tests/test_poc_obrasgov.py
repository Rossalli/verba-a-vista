import importlib.util
import io
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

_spec = importlib.util.spec_from_file_location(
    "poc_obrasgov", Path(__file__).resolve().parents[1] / "scripts" / "poc_obrasgov.py"
)
poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poc)

OPENAPI = {"paths": {"/geometria": {"get": {"parameters": [{"name": "cod_ibge"}, {"name": "pagina"}, {"name": "tamanho_da_pagina"}]}}}}


@respx.mock
def test_validar_rejeita_parametro_fora_do_openapi():
    respx.get(f"{poc.BASE}/openapi.json").mock(return_value=httpx.Response(200, json=OPENAPI))
    c = poc.Cliente()
    c.validar("geometria", {"cod_ibge": 3532504})
    with pytest.raises(ValueError, match="cod_ibgex"):
        c.validar("geometria", {"cod_ibgex": 3532504})


@respx.mock
def test_todos_pagina_ate_o_fim(monkeypatch):
    monkeypatch.setattr(poc, "PAUSA_S", 0)
    respx.get(f"{poc.BASE}/openapi.json").mock(return_value=httpx.Response(200, json=OPENAPI))
    respx.get(f"{poc.BASE}/geometria").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"id": 1}], "total_pages": 2, "total_items": 2}),
            httpx.Response(200, json={"data": [{"id": 2}], "total_pages": 2, "total_items": 2}),
        ]
    )
    registros, total = poc.Cliente().todos("geometria", {"cod_ibge": 3532504})
    assert [r["id"] for r in registros] == [1, 2] and total == 2


@respx.mock
def test_carregar_ponte_le_zip_com_bom_e_ignora_o_link(monkeypatch):
    monkeypatch.setattr(poc, "PAUSA_S", 0)
    csv_texto = (
        "﻿id_projeto_investimento;nr_instrumento;programa_governo;link_transparencia\n"
        "106169.35-86;990509;;https://exemplo/x?Usr=guest&Pwd=guest\n"
        "25996.41-70;944436;;https://exemplo/y\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("siconv_dados_obrasgov_geral.csv", csv_texto.encode("utf-8"))
    respx.get(poc.PONTE_URL).mock(return_value=httpx.Response(200, content=buffer.getvalue()))
    ponte = poc.carregar_ponte(poc.Cliente())
    assert ponte == {"106169.35-86": "990509", "25996.41-70": "944436"}
    assert "guest" not in str(ponte)
