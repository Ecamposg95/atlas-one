"""Renglones de comision en el ticket y en el reemitido.

SimpleNamespace en vez de MagicMock a proposito: con MagicMock cualquier
atributo no declarado sale truthy y la prueba de "no imprime nada" mentiria
(mismo motivo documentado en tests/test_ticket_usd.py)."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

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


def _sale(pct=None, monto="0", total="1000.00", usd_rate=None):
    total_dec = Decimal(total)
    return SimpleNamespace(
        lines=[_line("Mercancia", 1, total_dec)],
        series="A", folio=123,
        subtotal=total_dec, tax_amount=Decimal("0"), total_amount=total_dec,
        customer_name="Cliente Test", customer=None,
        created_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        notes=None, requires_invoice=False,
        usd_rate=Decimal(usd_rate) if usd_rate is not None else None,
        card_surcharge_pct=Decimal(pct) if pct is not None else None,
        card_surcharge_amount=Decimal(monto),
    )


def _build_raw(sale, ancho=80) -> bytes:
    p = PosPrinter(paper_width_mm=ancho)
    return p.build_ticket_bytes(
        sale, paid=Decimal("0"), change=Decimal("0"), method="CARD",
        cashier="Cajero Test", is_reprint=False, organization=_org(),
        branch=None, returns=None, payments_detail=None,
    )


def _sin_comandos(raw: bytes, ancho: int) -> list:
    """Lineas tal como saldrian en el papel, sin los comandos ESC/POS.

    MISMO helper que `tests/test_ticket_usd.py::_lineas_visibles`, y por el
    mismo motivo: BOLD_ON/BOLD_OFF quedan pegados al texto sin un '\\n' de por
    medio (los renglones de TOTAL y TOTAL A PAGAR van en negritas), asi que
    medir la linea cruda daria 3 columnas de mas y la prueba de ancho mentiria.
    """
    p = PosPrinter(paper_width_mm=ancho)
    for nombre, secuencia in p.CMD.items():
        if nombre == "LF":  # el salto de linea SI se queda: es el separador
            continue
        raw = raw.replace(secuencia, b"")
    return [l.rstrip() for l in raw.decode("latin-1", "replace").split("\n")]


def _lineas(sale, ancho=80) -> list:
    return _sin_comandos(_build_raw(sale, ancho), ancho)


def _renglon(lineas, prefijo: str) -> str:
    return next(l for l in lineas if l.lstrip().startswith(prefijo))


def test_sin_comision_no_imprime_nada():
    # Neutralidad: una organizacion sin comision imprime el ticket de siempre.
    texto = "\n".join(_lineas(_sale()))
    assert "COM. TARJETA" not in texto
    assert "TOTAL A PAGAR" not in texto


def test_imprime_la_comision_y_el_total_a_pagar():
    lineas = _lineas(_sale(pct="3.50", monto="35.00"))
    assert _renglon(lineas, "COM. TARJETA 3.5%:").endswith("35.00")
    assert _renglon(lineas, "TOTAL A PAGAR:").endswith("1035.00")
    # El total de mercancia NO se mueve: la comision va aparte.
    assert _renglon(lineas, "TOTAL:").endswith("1000.00")


def test_el_porcentaje_entero_no_arrastra_decimales():
    assert _renglon(_lineas(_sale(pct="3.00", monto="30.00")), "COM. TARJETA 3%:")


def test_el_porcentaje_con_dos_decimales_se_conserva():
    assert _renglon(_lineas(_sale(pct="2.75", monto="27.50")), "COM. TARJETA 2.75%:")


@pytest.mark.parametrize("ancho,cols", [(58, 32), (80, 56)])
def test_los_renglones_caben_en_el_papel(ancho, cols):
    # `_total_line` NO trunca la etiqueta: si no cabe, desborda el papel. Se
    # usa el porcentaje mas largo posible (el tope de 20 %, dos decimales),
    # que a 58 mm ocupa las 32 columnas EXACTAS.
    lineas = _lineas(_sale(pct="19.99", monto="199.90"), ancho=ancho)
    assert len([l for l in lineas if "COM. TARJETA" in l or "TOTAL A PAGAR" in l]) == 2
    # Cobertura del ticket completo, no solo de los renglones nuevos.
    for l in lineas:
        assert len(l) <= cols, f"línea de {len(l)} columnas: {l!r}"


def test_comision_en_cero_no_imprime_aunque_haya_porcentaje():
    assert "COM. TARJETA" not in "\n".join(_lineas(_sale(pct="3.50", monto="0")))


def test_la_linea_usd_usa_el_total_a_pagar():
    # El equivalente en dolares es lo que el cliente entrega, comision incluida:
    # 1035.00 / 18.50 = 55.95
    lineas = _lineas(_sale(pct="3.50", monto="35.00", usd_rate="18.5000"))
    assert _renglon(lineas, "USD (T.C. 18.5000):").endswith("55.95")


def test_sin_comision_la_linea_usd_no_se_mueve():
    # Neutralidad de la Task anterior: 1000.00 / 18.50 = 54.05
    lineas = _lineas(_sale(usd_rate="18.5000"))
    assert _renglon(lineas, "USD (T.C. 18.5000):").endswith("54.05")


def test_el_reemitido_conserva_la_comision_original():
    # La comision NO se devuelve (diseño §7): el ticket reemitido baja el TOTAL
    # pero sigue mostrando la comision que el banco ya se quedo.
    p = PosPrinter(paper_width_mm=80)
    raw = p.build_reissued_ticket_bytes(
        sale=_sale(pct="3.50", monto="35.00"), cashier="Cajero Test",
        organization=_org(), branch=None, returns=[],
    )
    lineas = _sin_comandos(raw, 80)
    assert _renglon(lineas, "COM. TARJETA 3.5%:").endswith("35.00")
    assert _renglon(lineas, "TOTAL A PAGAR:").endswith("1035.00")
