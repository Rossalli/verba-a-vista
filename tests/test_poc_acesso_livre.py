"""POC Acesso Livre: as partes do script que não dependem da rede (HTML de exemplo, sem credenciais reais)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import poc_acesso_livre as poc  # noqa: E402

PAGINA = """<html><body>
<a href="https://discricionarias.exemplo.gov.br/voluntarias/ForwardAction.do?Usr=visitante&Pwd=segredo&modulo=Proposta&path=x">Consultar Propostas</a>
<a href="https://discricionarias.exemplo.gov.br/voluntarias/ForwardAction.do?Usr=visitante&Pwd=segredo&modulo=Programa&path=y">Consultar Programas</a>
<a href="/outra">Outra coisa</a></body></html>"""

FORMULARIO_SAML = """<form method="POST" action="https://idp.exemplo.gov.br/idp/"><INPUT TYPE="HIDDEN" NAME="SAMLRequest" VALUE="abc123=="><input type="submit"></form>"""


def test_acha_o_link_pelo_texto():
    assert poc.link_de_visitante(PAGINA).endswith("modulo=Proposta&path=x")
    assert "Programa" in poc.link_de_visitante(PAGINA, "Consultar Programas")
    assert poc.link_de_visitante(PAGINA, "Não existe") is None


def test_o_que_se_imprime_nunca_traz_usuario_nem_senha():
    texto = poc.sem_credenciais(poc.link_de_visitante(PAGINA))
    assert texto == "discricionarias.exemplo.gov.br/voluntarias/ForwardAction.do (parâmetros: Pwd, Usr, modulo, path)"
    assert "visitante" not in texto and "segredo" not in texto


def test_le_formulario_com_atributos_em_maiusculas():
    f = poc.Formularios()
    f.feed(FORMULARIO_SAML)
    (form,) = f.formularios
    assert form["acao"] == "https://idp.exemplo.gov.br/idp/" and form["metodo"] == "post"
    assert form["campos"] == {"SAMLRequest": "abc123=="}  # o HTML real usa HIDDEN/NAME em maiúsculas


def test_o_script_se_identifica_e_nao_imita_navegador():
    assert poc.UA.startswith("verba-a-vista/") and "Mozilla" not in poc.UA
