"""La columna que atribuye un pago a la caja que lo recibio.

Hasta ahora el efectivo se atribuia por el DOCUMENTO de venta. Eso hace que
liquidar una venta a credito en otro turno mueva el efectivo de ayer al corte
de hoy, y que un abono de cliente cuente en la caja de la venta original en vez
de la que recibio el dinero.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument


def test_el_pago_puede_apuntar_a_una_sesion(db, org, branch_a, cajero_a):
    sesion = CashSession(user_id=cajero_a.id, branch_id=branch_a.id,
                         organization_id=org.id, opening_balance=Decimal("0"), status="OPEN")
    db.add(sesion); db.commit(); db.refresh(sesion)

    venta = SalesDocument(
        organization_id=org.id, branch_id=branch_a.id, seller_id=cajero_a.id,
        folio=1, series="A", subtotal=Decimal("50"), tax_amount=Decimal("0"),
        total_amount=Decimal("50"), status=DocumentStatus.PAID, doc_type="ORDER",
    )
    db.add(venta); db.flush()
    pago = Payment(sales_document_id=venta.id, amount=Decimal("50"),
                   method=PaymentMethod.CASH, organization_id=org.id,
                   cash_session_id=sesion.id)
    db.add(pago); db.commit(); db.refresh(pago)

    assert pago.cash_session_id == sesion.id


def test_la_columna_admite_nulo(db, org, branch_a, cajero_a):
    """Los pagos historicos y los de ventas sin caja quedan en nulo a proposito."""
    venta = SalesDocument(
        organization_id=org.id, branch_id=branch_a.id, seller_id=cajero_a.id,
        folio=2, series="A", subtotal=Decimal("10"), tax_amount=Decimal("0"),
        total_amount=Decimal("10"), status=DocumentStatus.PAID, doc_type="ORDER",
    )
    db.add(venta); db.flush()
    pago = Payment(sales_document_id=venta.id, amount=Decimal("10"),
                   method=PaymentMethod.CASH, organization_id=org.id)
    db.add(pago); db.commit(); db.refresh(pago)

    assert pago.cash_session_id is None
