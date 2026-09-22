"""El efectivo cuenta en la caja que lo recibio, no en la de la venta."""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument
from app.services.cash_reconciliation import compute_expected_cash


def _sesion(db, org, branch, user, fondo="0"):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal(fondo), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _venta(db, org, branch, user, folio, total, sesion_doc=None):
    v = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=folio, series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=DocumentStatus.PAID, doc_type="ORDER",
        cash_session_id=sesion_doc.id if sesion_doc else None,
    )
    db.add(v); db.flush()
    return v


class TestAtribucionPorPago:
    def test_el_pago_cuenta_en_su_propia_caja(self, db, org, branch_a, cajero_a):
        """La venta nacio en la sesion 1; el dinero entro en la sesion 2."""
        s1 = _sesion(db, org, branch_a, cajero_a)
        venta = _venta(db, org, branch_a, cajero_a, 1, "100", sesion_doc=s1)
        s1.status = "CLOSED"; db.commit()
        s2 = _sesion(db, org, branch_a, cajero_a)

        db.add(Payment(sales_document_id=venta.id, amount=Decimal("100"),
                       method=PaymentMethod.CASH, organization_id=org.id,
                       cash_session_id=s2.id))
        db.commit()

        assert Decimal(str(compute_expected_cash(db, s2).expected)) == Decimal("100.00"), (
            "el dinero entro en la sesion 2 y ahi debe contar"
        )
        assert Decimal(str(compute_expected_cash(db, s1).expected)) == Decimal("0.00"), (
            "la sesion 1 no recibio ese dinero y no debe verse alterada"
        )

    def test_un_pago_sin_atribucion_sigue_contando_como_antes(self, db, org, branch_a, cajero_a):
        """Retrocompatibilidad: el respaldo por documento no se rompe."""
        s = _sesion(db, org, branch_a, cajero_a)
        venta = _venta(db, org, branch_a, cajero_a, 2, "40", sesion_doc=s)
        db.add(Payment(sales_document_id=venta.id, amount=Decimal("40"),
                       method=PaymentMethod.CASH, organization_id=org.id))
        db.commit()

        assert Decimal(str(compute_expected_cash(db, s).expected)) == Decimal("40.00")

    def test_no_se_cuenta_dos_veces(self, db, org, branch_a, cajero_a):
        """Un pago atribuido a la MISMA sesion del documento cuenta una sola vez."""
        s = _sesion(db, org, branch_a, cajero_a)
        venta = _venta(db, org, branch_a, cajero_a, 3, "60", sesion_doc=s)
        db.add(Payment(sales_document_id=venta.id, amount=Decimal("60"),
                       method=PaymentMethod.CASH, organization_id=org.id,
                       cash_session_id=s.id))
        db.commit()

        assert Decimal(str(compute_expected_cash(db, s).expected)) == Decimal("60.00")
