"""Fuente unica de IVA: `app/services/tax.py::compute_line_tax`.

Portado de Atlas-Rmazh (`tests/test_iva_calc.py`, hallazgo §3 de
docs/audits/2026-09-01-comparacion-atlas-rmazh.md). Antes de esto la formula
vivia repetida en el cobro, el ticket reemitido y la devolucion, y cada copia
redondeaba distinto: el ticket y el reporte podian discrepar en centavos.
"""
from decimal import Decimal

from app.services.tax import TaxResult, compute_line_tax

D = lambda s: Decimal(str(s))  # noqa: E731


def test_modo_incluido_desglosa_del_precio():
    # Precio 116 que YA trae el IVA: base 100, IVA 16, el total NO cambia.
    r = compute_line_tax(D("116.00"), D("16"), has_iva=True, price_includes_tax=True, requires_invoice=True)
    assert r == TaxResult(subtotal=D("100.00"), tax=D("16.00"), total=D("116.00"))


def test_modo_neto_suma_encima():
    # Precio 100 sin IVA: se suma 16 encima, total 116.
    r = compute_line_tax(D("100.00"), D("16"), has_iva=True, price_includes_tax=False, requires_invoice=True)
    assert r == TaxResult(subtotal=D("100.00"), tax=D("16.00"), total=D("116.00"))


def test_sin_factura_no_desglosa_en_ningun_modo():
    for incluido in (True, False):
        r = compute_line_tax(D("116.00"), D("16"), has_iva=True, price_includes_tax=incluido, requires_invoice=False)
        assert r == TaxResult(subtotal=D("116.00"), tax=D("0.00"), total=D("116.00"))


def test_producto_exento_no_causa_impuesto():
    r = compute_line_tax(D("100.00"), D("16"), has_iva=False, price_includes_tax=True, requires_invoice=True)
    assert r == TaxResult(subtotal=D("100.00"), tax=D("0.00"), total=D("100.00"))


def test_tasa_cero_es_exento():
    r = compute_line_tax(D("100.00"), D("0"), has_iva=True, price_includes_tax=True, requires_invoice=True)
    assert r.tax == D("0.00")


def test_tasa_frontera_8pct_incluida():
    r = compute_line_tax(D("108.00"), D("8"), has_iva=True, price_includes_tax=True, requires_invoice=True)
    assert r == TaxResult(subtotal=D("100.00"), tax=D("8.00"), total=D("108.00"))


def test_redondeo_half_up_modo_incluido():
    # 99.99 / 1.16 = 86.198... -> 86.20 ; IVA = 13.79 ; total 99.99 (invariante).
    r = compute_line_tax(D("99.99"), D("16"), has_iva=True, price_includes_tax=True, requires_invoice=True)
    assert r.subtotal == D("86.20")
    assert r.tax == D("13.79")
    assert r.subtotal + r.tax == r.total == D("99.99")


def test_tasa_nula_se_trata_como_exenta():
    # `variant.tax_rate` es nullable en el catalogo (app/modules/products/models.py).
    r = compute_line_tax(D("100.00"), None, has_iva=True, price_includes_tax=False, requires_invoice=True)
    assert r == TaxResult(subtotal=D("100.00"), tax=D("0.00"), total=D("100.00"))
