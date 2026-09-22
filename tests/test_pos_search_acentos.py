"""La búsqueda del POS ignora los acentos de TODO el latin-1, no solo los del español.

Regresión: la boutique tiene marcas con acento grave (Hermès) y cedilla
(Comme des Garçons). El mapa de `translate()` solo cubría el acento agudo, así
que la cajera escribía "hermes" y no encontraba nada.

En SQLite (donde corren las pruebas) no hay `translate()`, así que la normalización
real solo se ejercita en Postgres. Aquí se prueba el MAPA, que es donde estaba el
defecto, y que la búsqueda con el texto tal cual sigue funcionando.
"""
import pytest

from app.modules.products.router.search import _MAPA_ACENTOS


def test_el_mapa_esta_parejo():
    con, sin = _MAPA_ACENTOS
    assert len(con) == len(sin), "cada carácter acentuado necesita su equivalente sin acento"


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Hermès", "Hermes"),            # acento grave
        ("Comme des Garçons", "Comme des Garcons"),  # cedilla
        ("Enfants Riches Déprimés", "Enfants Riches Deprimes"),  # agudo
        ("Suéter", "Sueter"),
        ("Pantalón", "Pantalon"),
        ("Joyería", "Joyeria"),
        ("Niño", "Nino"),
        ("Möncler", "Moncler"),          # diéresis
        ("Sâo", "Sao"),                  # circunflejo
    ],
)
def test_quita_el_acento(texto, esperado):
    con, sin = _MAPA_ACENTOS
    assert texto.translate(str.maketrans(con, sin)) == esperado


def test_no_toca_lo_que_no_lleva_acento():
    con, sin = _MAPA_ACENTOS
    for texto in ("Louis Vuitton", "Chrome Hearts", "2017000000013", "CH-PLAY-EP-M"):
        assert texto.translate(str.maketrans(con, sin)) == texto
