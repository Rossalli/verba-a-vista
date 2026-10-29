"""Conversão de valores monetários das fontes para centavos inteiros (CLAUDE.md: dinheiro é `int` em centavos).

Nunca `int(valor * 100)`: `int(0.29 * 100)` dá 28. Formato desconhecido levanta ValueError, não é adivinhado.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

_TEXTO_BR = re.compile(r"^(?P<neg>-\s*)?(?P<int>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<dec>\d{1,2}))?$")


def centavos_texto(texto: str | None) -> int | None:
    """Texto brasileiro -> centavos. `"1.234,56"`, `"126207,45"`, `"130000"` e estornos `"- 7.174,10"`. Vazio -> None.

    O ponto só vale como separador de milhar (`1.234,56`, `130.000`); `"12.5"` é erro.
    """
    if texto is None or texto.strip() == "":
        return None
    achado = _TEXTO_BR.match(texto.strip())
    if not achado:
        raise ValueError(f"valor monetário em formato desconhecido: {texto!r}")
    inteiro = int(achado["int"].replace(".", ""))
    decimais = int((achado["dec"] or "0").ljust(2, "0"))
    valor = inteiro * 100 + decimais
    return -valor if achado["neg"] else valor


def centavos_reais(valor: float | int | str | Decimal | None) -> int | None:
    """Reais (como as APIs devolvem, `91673.94`) -> centavos, arredondando metade para cima. None -> None."""
    if valor is None:
        return None
    return int((Decimal(str(valor)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
