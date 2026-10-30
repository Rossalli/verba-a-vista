import shutil
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def raiz_sem_publicado(tmp_path_factory) -> Path:
    """Raiz isolada só com os retratos brutos reais, sem `dados/publicados` nem `dados/curadoria`.

    Os testes do pipeline usam esta raiz em vez da do repositório, para não depender de haver (ou não) um
    publicado anterior ou arquivos de curadoria no Git. Só leitura: quem publica usa o próprio `tmp_path`.
    """
    raiz = tmp_path_factory.mktemp("raiz_sem_publicado")
    shutil.copytree(RAIZ / "dados" / "brutos", raiz / "dados" / "brutos")
    return raiz
