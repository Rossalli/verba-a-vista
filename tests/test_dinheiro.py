import pytest

from nucleo.dinheiro import centavos_reais, centavos_texto


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1.234,56", 123456),
        ("650.000,00", 65000000),
        ("126207,45", 12620745),  # Siconv: vírgula decimal, sem milhar
        ("130000", 13000000),  # Siconv: inteiro sem decimais
        ("130.000", 13000000),  # ponto só como milhar
        ("0,29", 29),
        ("0,5", 50),  # um decimal vale 50 centavos, não 5
        ("0", 0),
        ("- 7.174,10", -717410),  # estorno do Portal: sinal e espaço
        ("-7.174,10", -717410),
        ("  1.000,00 ", 100000),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_centavos_texto(texto, esperado):
    assert centavos_texto(texto) == esperado


@pytest.mark.parametrize("texto", ["12.5", "1,234", "R$ 10,00", "abc", "1,2,3", "1.23,45", "--5", "1e3"])
def test_centavos_texto_formato_desconhecido_e_erro(texto):
    with pytest.raises(ValueError, match="formato desconhecido"):
        centavos_texto(texto)


@pytest.mark.parametrize(
    ("reais", "esperado"),
    [(91673.94, 9167394), (0.29, 29), (1.15, 115), (4.35, 435), (1000410.68, 100041068), (0, 0), (2850000.0, 285000000), ("486124.06", 48612406), (None, None)],
)
def test_centavos_reais_arredonda_em_vez_de_truncar(reais, esperado):
    assert centavos_reais(reais) == esperado


def test_centavos_reais_meio_centavo_sobe():
    assert centavos_reais(0.005) == 1 and centavos_reais(2.675) == 268  # 2,675 em float é 2,67499..., por isso passa por str
