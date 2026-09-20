"""El ticket de prueba es la carta de presentación de Atlas Tech, no un
ticket de venta: lleva la marca del proveedor y una muestra del negocio."""
from types import SimpleNamespace

from app.pos_printer import PosPrinter


def _org(**kw):
    base = dict(name="Eleven Fashion", logo_url=None, phone=None, ticket_footer="Gracias por su compra!")
    base.update(kw)
    return SimpleNamespace(**base)


def _decode(raw: bytes) -> str:
    return raw.decode("latin-1", "replace")


def test_lleva_la_marca_atlas_tech_y_el_negocio_como_muestra():
    out = _decode(PosPrinter(paper_width_mm=80).build_test_ticket_bytes(_org(), branch=SimpleNamespace(name="Roma", city=None, phone="5512345678", logo_url=None, ticket_footer=None)))
    assert "ATLAS TECH" in out
    assert "IMPRESION DE PRUEBA" in out
    assert "Eleven Fashion" in out
    assert "Roma | 5512345678" in out
    assert "Gracias por su compra!" in out
    assert "rmazh" not in out.lower()


def test_en_58mm_ninguna_linea_excede_el_ancho():
    p = PosPrinter(paper_width_mm=58)
    out = _decode(p.build_test_ticket_bytes(_org(name="Un nombre de negocio larguisimo para probar el corte")))
    texto = [l for l in out.replace("\x1b", "").split("\n") if l.strip() and l.isprintable()]
    assert all(len(l) <= p.cols + 3 for l in texto), [l for l in texto if len(l) > p.cols + 3]


def test_sin_organizacion_no_revienta():
    out = _decode(PosPrinter(paper_width_mm=80).build_test_ticket_bytes(None))
    assert "ATLAS TECH" in out and "Tu negocio" in out
