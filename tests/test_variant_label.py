"""Etiqueta derivada de color/talla. Es lo que se guarda en `variant_name` y
lo que imprime el ticket entre parentesis."""
import pytest

from app.modules.products.variant_label import clean_attr, variant_label


@pytest.mark.parametrize("color,size,esperado", [
    ("Rojo", "M", "Rojo / M"),
    ("Rojo", None, "Rojo"),
    (None, "M", "M"),
    (None, None, "Estándar"),
    ("  ", "", "Estándar"),
])
def test_variant_label(color, size, esperado):
    assert variant_label(color, size) == esperado


def test_clean_attr_recorta_y_colapsa():
    assert clean_attr("  Azul   marino ", 60) == "Azul marino"
    assert clean_attr("", 60) is None
    assert clean_attr(None, 60) is None


def test_clean_attr_respeta_el_largo():
    with pytest.raises(ValueError):
        clean_attr("x" * 61, 60)
