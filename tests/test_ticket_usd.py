"""Linea de equivalente en dolares en el ticket y en el reemitido.

SimpleNamespace en vez de MagicMock a proposito: con MagicMock cualquier
atributo no declarado sale truthy y la prueba de "no imprime nada" mentiria."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.pos_printer import PosPrinter


def _org():
    return SimpleNamespace(
        name="Tienda Demo", legal_name=None, tax_id=None, tax_regime=None,
        address=None, phone=None, logo_url=None,
        ticket_header=None, ticket_footer=None, price_includes_tax=False,
    )


def _line(description, quantity, unit_price):
    qty = Decimal(str(quantity))
    unit = Decimal(str(unit_price))
    return SimpleNamespace(description=description, quantity=qty, unit_price=unit,
                           total_line=qty * unit, variant_id="v1")


def _sale(usd_rate=None, total="185.00"):
    total_dec = Decimal(total)
    return SimpleNamespace(
        lines=[_line("Playera", 1, total_dec)],
        series="A", folio=123,
        subtotal=total_dec, tax_amount=Decimal("0"), total_amount=total_dec,
        customer_name="Cliente Test", customer=None,
        created_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        notes=None, requires_invoice=False,
        usd_rate=Decimal(usd_rate) if usd_rate is not None else None,
    )


def _build(sale, ancho=80):
    p = PosPrinter(paper_width_mm=ancho)
    raw = p.build_ticket_bytes(
        sale, paid=Decimal("0"), change=Decimal("0"), method="CASH",
        cashier="Cajero Test", is_reprint=False, organization=_org(),
        branch=None, returns=None, payments_detail=None,
    )
    return raw.decode("latin-1", "replace")


def test_sin_tipo_de_cambio_no_imprime_nada():
    # Neutralidad: una organizacion sin la funcion encendida imprime el mismo
    # ticket de siempre, byte por byte.
    assert "USD" not in _build(_sale())


def test_imprime_el_equivalente_y_el_tipo():
    texto = _build(_sale(usd_rate="18.5000"))
    assert "USD (T.C. 18.5000):" in texto
    assert "10.00" in texto  # 185.00 / 18.50


def _visible(linea: str) -> str:
    """Contenido imprimible de una línea, sin los bytes de control ESC/POS que
    quedan pegados antes del texto (p. ej. el BOLD_OFF del TOTAL): en el papel
    real esos bytes no ocupan columna, así que no cuentan para el ancho."""
    return linea[linea.index("USD"):].rstrip()


def test_la_linea_cabe_en_papel_de_58mm():
    texto = _build(_sale(usd_rate="18.5000"), ancho=58)
    renglones = [_visible(l) for l in texto.split("\n") if "USD" in l]
    assert renglones, "debe imprimirse la línea USD"
    for l in renglones:
        assert len(l) <= 32, f"línea de {len(l)} columnas: {l!r}"


def test_la_linea_cabe_en_papel_de_80mm():
    texto = _build(_sale(usd_rate="18.5000"), ancho=80)
    renglones = [_visible(l) for l in texto.split("\n") if "USD" in l]
    assert renglones, "debe imprimirse la línea USD"
    for l in renglones:
        assert len(l) <= 56, f"línea de {len(l)} columnas: {l!r}"


def test_tipo_invalido_se_ignora():
    assert "USD" not in _build(_sale(usd_rate="0"))


def test_el_reemitido_usa_el_mismo_tipo():
    p = PosPrinter(paper_width_mm=80)
    raw = p.build_reissued_ticket_bytes(
        sale=_sale(usd_rate="18.5000"), cashier="Cajero Test",
        organization=_org(), branch=None, returns=[],
    )
    assert "USD (T.C. 18.5000):" in raw.decode("latin-1", "replace")
