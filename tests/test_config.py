import shutil
from pathlib import Path

import pytest
import yaml

from nucleo.config import DIRETORIO_PADRAO, ConfigErro, carregar_config, normalizar_situacao


@pytest.fixture
def copia(tmp_path: Path) -> Path:
    destino = tmp_path / "config"
    shutil.copytree(DIRETORIO_PADRAO, destino)
    return destino


def editar(diretorio: Path, arquivo: str, mudanca) -> None:
    caminho = diretorio / arquivo
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    mudanca(dados)
    caminho.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")


def test_config_real_do_repositorio_e_valida():
    config = carregar_config()
    assert config.regras.municipio.codigo_ibge == "3532504"
    assert config.regras.risco.dias_alerta_prazo == 60
    assert config.regras.curadoria.auto_publicar is False
    assert "perdida" in config.status_map.fontes["transferegov_discricionarias_convenio"].mapa
    assert config.status_map.fontes["obrasgov"].mapa == {}  # fonte auxiliar, não define status (D8)
    assert len(config.taxonomia.categorias) == 10
    assert config.fontes.fontes["portal_transparencia"].auth.env == "PORTAL_TRANSPARENCIA_KEY"


def test_config_valida_em_copia(copia):
    assert carregar_config(copia).regras.municipio.nome == "Neves Paulista"


def test_chave_obrigatoria_ausente(copia):
    editar(copia, "regras.yaml", lambda d: d["risco"].pop("dias_alerta_prazo"))
    with pytest.raises(ConfigErro, match=r"regras\.yaml: risco\.dias_alerta_prazo: chave obrigatória ausente"):
        carregar_config(copia)


def test_chave_desconhecida_acusa_erro_de_digitacao(copia):
    editar(copia, "regras.yaml", lambda d: d["risco"].update(dias_alerta_prazzo=5))
    with pytest.raises(ConfigErro, match=r"risco\.dias_alerta_prazzo: chave desconhecida"):
        carregar_config(copia)


@pytest.mark.parametrize("valor", [0, -5, "sessenta"])
def test_valor_invalido(copia, valor):
    editar(copia, "regras.yaml", lambda d: d["risco"].update(dias_alerta_prazo=valor))
    with pytest.raises(ConfigErro, match=r"risco\.dias_alerta_prazo"):
        carregar_config(copia)


def test_fuso_e_horario_invalidos(copia):
    editar(copia, "regras.yaml", lambda d: d["coleta"].update(fuso="Marte/Olimpo", horario="25:00"))
    with pytest.raises(ConfigErro) as e:
        carregar_config(copia)
    assert "coleta.fuso" in str(e.value) and "coleta.horario" in str(e.value)


def test_categoria_de_curadoria_desconhecida(copia):
    editar(copia, "regras.yaml", lambda d: d["curadoria"].update(auto_publicar_categorias=["inventada"]))
    with pytest.raises(ConfigErro, match="auto_publicar_categorias"):
        carregar_config(copia)


def test_status_map_com_status_inexistente(copia):
    editar(copia, "status_map.yaml", lambda d: d["fontes"]["obrasgov"]["mapa"].update(em_risco=["X"]))
    with pytest.raises(ConfigErro, match=r"status_map\.yaml: fontes\.obrasgov\.mapa\.em_risco"):
        carregar_config(copia)


def test_status_map_situacao_em_dois_status_mesmo_com_acento_e_caixa(copia):
    def mudar(d):
        mapa = d["fontes"]["obrasgov"]["mapa"]
        mapa["concluida"] = ["CONCLUÍDA  "]
        mapa["perdida"] = ["concluida"]

    editar(copia, "status_map.yaml", mudar)
    with pytest.raises(ConfigErro, match="aparece em"):
        carregar_config(copia)


def test_status_map_status_fora_de_status_validos(copia):
    editar(copia, "status_map.yaml", lambda d: d["status_validos"].remove("perdida"))
    with pytest.raises(ConfigErro, match="não está em status_validos"):
        carregar_config(copia)


def test_taxonomia_sem_categoria(copia):
    editar(copia, "taxonomia.yaml", lambda d: d["categorias"].pop("cauc"))
    with pytest.raises(ConfigErro, match="categorias ausentes na taxonomia: cauc"):
        carregar_config(copia)


def test_limite_do_portal_acima_do_permitido_pela_fonte(copia):
    editar(copia, "regras.yaml", lambda d: d["coleta"].update(portal_transparencia_req_por_min=500))
    with pytest.raises(ConfigErro, match="maior que"):
        carregar_config(copia)


def test_arquivo_ausente(copia):
    (copia / "fontes.yaml").unlink()
    with pytest.raises(ConfigErro, match=r"fontes\.yaml: arquivo não encontrado"):
        carregar_config(copia)


def test_yaml_quebrado(copia):
    (copia / "taxonomia.yaml").write_text("categorias: [\n", encoding="utf-8")
    with pytest.raises(ConfigErro, match=r"taxonomia\.yaml: YAML inválido"):
        carregar_config(copia)


def test_arquivo_que_nao_e_mapa(copia):
    (copia / "regras.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigErro, match="deve ser um mapa"):
        carregar_config(copia)


def test_normalizar_situacao():
    assert normalizar_situacao("  Prestação   de  Contas ") == "prestacao de contas"
    assert normalizar_situacao("EM EXECUÇÃO") == normalizar_situacao("em execucao")
