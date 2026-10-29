import os
import sys
from datetime import date
from pathlib import Path

import pytest

from coleta import __main__ as cli
from coleta import base
from coleta.base import Resultado, carregar_dotenv


def resultado(fonte, status="ok", erro=None, registros=None, caminho=None):
    return Resultado(fonte, status, erro=erro, caminho=caminho, registros=registros or {"a": 2, "b": 3}, requisicoes=7, duracao_s=1.5)


@pytest.fixture
def espiao(monkeypatch):
    """Troca `executar` por um espião que registra com que argumentos a CLI o chamou."""
    chamadas = []

    def falso(fontes=None, data=None, **kw):
        chamadas.append({"fontes": fontes, "data": data, **kw})
        return chamadas_resultados

    chamadas_resultados = [resultado("cauc"), resultado("obrasgov")]
    monkeypatch.setattr(cli, "executar", falso)
    monkeypatch.setattr(cli, "carregar_dotenv", lambda *a, **k: [])
    return chamadas, chamadas_resultados


def test_sem_argumentos_coleta_tudo_com_a_data_de_hoje(espiao, capsys):
    chamadas, _ = espiao
    assert cli.main([]) == 0
    assert chamadas == [{"fontes": None, "data": None, "raiz": base.RAIZ, "forcar": False}]
    saida = capsys.readouterr().out
    assert "cauc" in saida and "obrasgov" in saida and "5" in saida  # 2 + 3 registros


def test_argumentos_chegam_ao_executar(espiao):
    chamadas, _ = espiao
    cli.main(["--fonte", "cauc", "--fonte", "obrasgov", "--data", "2026-10-29", "--forcar", "--cache", "x", "--destino", "y"])
    assert chamadas == [{"fontes": ["cauc", "obrasgov"], "data": date(2026, 10, 29), "raiz": Path("y"), "forcar": True, "cache": Path("x")}]


def test_fonte_desconhecida_e_recusada_pelo_argparse(espiao):
    with pytest.raises(SystemExit) as e:
        cli.main(["--fonte", "inventada"])
    assert e.value.code == 2


def test_falha_de_uma_fonte_da_codigo_1_mas_mostra_todas(espiao, capsys):
    _, resultados = espiao
    resultados[1] = resultado("obrasgov", "erro", erro="ColetaErro: a fonte caiu", registros={})
    assert cli.main([]) == 1
    captura = capsys.readouterr()
    assert "ERRO: ColetaErro: a fonte caiu" in captura.out and "Falharam: obrasgov" in captura.err


def test_retrato_reaproveitado_nao_e_falha(espiao):
    _, resultados = espiao
    resultados[0] = resultado("cauc", "reaproveitado", registros={})
    assert cli.main([]) == 0


def test_dotenv_carrega_sem_sobrescrever_e_devolve_so_os_nomes(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text('# comentário\n\nPORTAL_TRANSPARENCIA_KEY="valor-secreto"\nANTHROPIC_API_KEY=\nJA_DEFINIDA=do-arquivo\nsem_igual\n', encoding="utf-8")
    monkeypatch.delenv("PORTAL_TRANSPARENCIA_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("JA_DEFINIDA", "do-ambiente")
    nomes = carregar_dotenv(tmp_path)
    assert nomes == ["PORTAL_TRANSPARENCIA_KEY"]  # só os nomes, nunca os valores
    assert os.environ["PORTAL_TRANSPARENCIA_KEY"] == "valor-secreto"
    assert os.environ["JA_DEFINIDA"] == "do-ambiente"  # o ambiente vence o arquivo
    assert "ANTHROPIC_API_KEY" not in os.environ  # linha sem valor é ignorada
    monkeypatch.delenv("PORTAL_TRANSPARENCIA_KEY")


def test_dotenv_ausente_nao_e_erro(tmp_path):
    assert carregar_dotenv(tmp_path) == []


def test_o_modulo_roda_com_python_m(monkeypatch):
    # garante que `python -m coleta` existe como ponto de entrada
    assert hasattr(cli, "main") and sys.modules["coleta.__main__"] is cli
