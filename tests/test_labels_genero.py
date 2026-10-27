"""El género se imprime solo en lo que no tiene talla (cinturones, accesorios):
en la ropa el renglón ya trae la talla y el dueño la quiso igual que siempre."""
from decimal import Decimal

import pytest

from app.models import Product, ProductVariant
from app.modules.labels.services import datos_de_variante


def _par(gender, size):
    producto = Product(name="Cinturón", gender=gender)
    variante = ProductVariant(sku="X", barcode="2017000000013", price=Decimal("2300"), size=size)
    return producto, variante


@pytest.mark.parametrize("gender,esperado", [
    ("HOMBRE", "Hombre"), ("MUJER", "Mujer"), ("UNISEX", "Unisex"), ("NINO", "Niño"), (None, ""),
])
def test_sin_talla_lleva_el_genero(gender, esperado):
    assert datos_de_variante(*_par(gender, None)).gender == esperado


def test_con_talla_no_lleva_el_genero():
    assert datos_de_variante(*_par("HOMBRE", "M")).gender == ""
