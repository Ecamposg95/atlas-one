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


def _build_raw(sale, ancho=80) -> bytes:
    p = PosPrinter(paper_width_mm=ancho)
    return p.build_ticket_bytes(
        sale, paid=Decimal("0"), change=Decimal("0"), method="CASH",
        cashier="Cajero Test", is_reprint=False, organization=_org(),
        branch=None, returns=None, payments_detail=None,
    )


def _build(sale, ancho=80):
    return _build_raw(sale, ancho).decode("latin-1", "replace")


def _lineas_visibles(sale, ancho=80):
    """Lineas del ticket tal como saldrian en el papel: sin los comandos
    ESC/POS de control (BOLD, CENTER, tamaño de fuente, corte...) que en el
    buffer quedan pegados justo antes o despues de un texto sin un '\\n' de
    por medio y que, medidos como caracteres normales, inflan el ancho de la
    linea aunque el papel real no les de columna ninguna."""
    p = PosPrinter(paper_width_mm=ancho)
    raw = _build_raw(sale, ancho)
    for nombre, secuencia in p.CMD.items():
        if nombre == "LF":  # el salto de linea SI debe quedarse: es el separador
            continue
        raw = raw.replace(secuencia, b"")
    texto = raw.decode("latin-1", "replace")
    return [l.rstrip() for l in texto.split("\n")]


def test_sin_tipo_de_cambio_no_imprime_nada():
    # Neutralidad: una organizacion sin la funcion encendida imprime el mismo
    # ticket de siempre, byte por byte.
    assert "USD" not in _build(_sale())


def test_imprime_el_equivalente_y_el_tipo():
    texto = _build(_sale(usd_rate="18.5000"))
    assert "USD (T.C. 18.5000):" in texto
    assert "10.00" in texto  # 185.00 / 18.50


def _contenido_usd(linea: str):
    """Desde la etiqueta 'USD' en adelante, con `partition` para no medir mal
    si algun dia un nombre de producto contiene la subcadena 'USD' antes de
    la etiqueta real. None si la línea no la trae."""
    antes, sep, despues = linea.partition("USD")
    if not sep:
        return None
    return (sep + despues).rstrip()


def test_la_linea_cabe_en_papel_de_58mm():
    lineas = _lineas_visibles(_sale(usd_rate="18.5000"), ancho=58)
    # Cobertura del ticket completo (no solo la línea nueva): el papel de
    # 58mm/32 cols no debe desbordarse en ningún renglón.
    for l in lineas:
        assert len(l) <= 32, f"línea de {len(l)} columnas: {l!r}"
    # Ajuste exacto de la línea USD en particular.
    usd = [c for c in (_contenido_usd(l) for l in lineas) if c is not None]
    assert usd, "debe imprimirse la línea USD"
    for c in usd:
        assert len(c) <= 32, f"línea USD de {len(c)} columnas: {c!r}"


def test_la_linea_cabe_en_papel_de_80mm():
    lineas = _lineas_visibles(_sale(usd_rate="18.5000"), ancho=80)
    # Cobertura del ticket completo en 80mm/56 cols, igual que en 58mm.
    for l in lineas:
        assert len(l) <= 56, f"línea de {len(l)} columnas: {l!r}"
    usd = [c for c in (_contenido_usd(l) for l in lineas) if c is not None]
    assert usd, "debe imprimirse la línea USD"
    for c in usd:
        assert len(c) <= 56, f"línea USD de {len(c)} columnas: {c!r}"


def test_tipo_invalido_se_ignora():
    assert "USD" not in _build(_sale(usd_rate="0"))


def test_el_reemitido_usa_el_mismo_tipo():
    p = PosPrinter(paper_width_mm=80)
    raw = p.build_reissued_ticket_bytes(
        sale=_sale(usd_rate="18.5000"), cashier="Cajero Test",
        organization=_org(), branch=None, returns=[],
    )
    assert "USD (T.C. 18.5000):" in raw.decode("latin-1", "replace")
