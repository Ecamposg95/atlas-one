"""Proporcion del IVA al aprobar una devolucion (`prorate_sale_after_refund`).

Portado y adaptado de Atlas-Rmazh (`tests/test_iva_returns_proration.py`). La
diferencia con el origen: aqui `SaleReturnItem.refund_amount` se calcula en
`app/crud/returns.py::create_return` como `qty * unit_price`, asi que su
naturaleza depende del modo de precio de la organizacion —en modo neto es
PRE-IVA, en modo "precio con IVA incluido" es BRUTO—. Por eso la funcion recibe
`refund_includes_tax` en vez del `price_includes_tax` del origen, que alli era
siempre bruto y quedaba ignorado dentro de la funcion.
"""
from decimal import Decimal

from app.services.tax import TaxResult, prorate_sale_after_refund

D = lambda s: Decimal(str(s))  # noqa: E731


# --- Modo neto (el de Atlas ONE hoy): el reembolso entra PRE-IVA ------------
def test_neto_devolver_una_de_dos_unidades():
    # Venta de 2 uds a 100 netos: subtotal 200, IVA 32, total 232. Se devuelve
    # una unidad (refund_amount = 100 neto). Queda 100 / 16 / 116.
    r = prorate_sale_after_refund(D("200"), D("32"), D("100"), refund_includes_tax=False)
    assert r == TaxResult(subtotal=D("100.00"), tax=D("16.00"), total=D("116.00"))


def test_neto_devolucion_total_deja_el_documento_en_cero():
    r = prorate_sale_after_refund(D("100"), D("16"), D("100"), refund_includes_tax=False)
    assert r == TaxResult(subtotal=D("0.00"), tax=D("0.00"), total=D("0.00"))


def test_neto_devolucion_secuencial_opera_sobre_el_estado_actual():
    # El documento ya refleja una aprobacion previa (100/16/116). Devolver la
    # otra mitad lo deja en cero: no se reconstruye el original.
    r = prorate_sale_after_refund(D("100"), D("16"), D("100"), refund_includes_tax=False)
    assert r == TaxResult(subtotal=D("0.00"), tax=D("0.00"), total=D("0.00"))


def test_venta_sin_iva_prorratea_igual():
    # Tasa efectiva 0: el reembolso baja el subtotal y el IVA sigue en cero.
    r = prorate_sale_after_refund(D("116"), D("0"), D("58"), refund_includes_tax=False)
    assert r == TaxResult(subtotal=D("58.00"), tax=D("0.00"), total=D("58.00"))


def test_nunca_deja_el_subtotal_en_negativo():
    # Un reembolso mayor que el restante (dato sucio) satura en cero en vez de
    # dejar totales negativos en el documento.
    r = prorate_sale_after_refund(D("50"), D("8"), D("100"), refund_includes_tax=False)
    assert r == TaxResult(subtotal=D("0.00"), tax=D("0.00"), total=D("0.00"))


# --- Modo "precio con IVA incluido": el reembolso entra BRUTO ---------------
def test_incluido_devolver_una_de_dos_unidades():
    # Venta de 2 uds a 116 brutos: subtotal 200, IVA 32, total 232. Se devuelve
    # una unidad (refund_amount = 116 bruto). Queda 100 / 16 / 116.
    r = prorate_sale_after_refund(D("200"), D("32"), D("116"), refund_includes_tax=True)
    assert r == TaxResult(subtotal=D("100.00"), tax=D("16.00"), total=D("116.00"))


def test_incluido_la_baja_del_total_es_el_bruto_devuelto():
    # Invariante de cuadre: total_antes - total_despues == bruto reembolsado.
    r = prorate_sale_after_refund(D("200"), D("32"), D("116"), refund_includes_tax=True)
    assert D("232.00") - r.total == D("116.00")


def test_incluido_tasa_frontera_8pct_parcial():
    r = prorate_sale_after_refund(D("100"), D("8"), D("54"), refund_includes_tax=True)
    assert r == TaxResult(subtotal=D("50.00"), tax=D("4.00"), total=D("54.00"))


def test_el_modo_importa_no_es_cosmetico():
    # Mismo monto, distinto modo: tratarlo como bruto cuando era neto
    # sub-descuenta (queda mas dinero vivo en el documento del que toca).
    neto = prorate_sale_after_refund(D("200"), D("32"), D("116"), refund_includes_tax=False)
    bruto = prorate_sale_after_refund(D("200"), D("32"), D("116"), refund_includes_tax=True)
    assert neto.total < bruto.total
