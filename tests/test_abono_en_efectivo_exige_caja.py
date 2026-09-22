"""Un abono en EFECTIVO tambien necesita una caja abierta que responda por el.

`POST /api/customers/{id}/pay` no exigia turno: el `Payment` nacia con
`cash_session_id` en NULL, caia a la rama de respaldo por documento de
`session_payments_filter` y aterrizaba en la sesion de la venta original —
tipicamente cerrada dias antes. El lunes cuadrado pasaba a mostrar un faltante
del monto del abono, imputado a un cajero que no estuvo ahi, y ningun corte
vivo veia ese dinero.

El criterio es el mismo que ya rige el checkout
(`app/routers/sales.py::create_sale`, guard H-5): el efectivo es fisico y no
admite excepciones de rol; lo que no toca el cajon (tarjeta, transferencia)
sigue permitido sin turno.
"""
from decimal import Decimal

import pytest

from app.models.cash import CashSession
from app.models.sales import DocumentStatus, Payment, SalesDocument
from app.modules.customers.models import Customer, CustomerLedgerEntry
from app.services.cash_reconciliation import compute_expected_cash


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _cliente_con_venta_a_credito(db, org, branch, user, sesion, total="1000.00", folio=3001):
    cliente = Customer(
        name="Cliente a credito", organization_id=org.id,
        has_credit=True, credit_limit=Decimal("5000"), current_balance=Decimal(total),
    )
    db.add(cliente); db.flush()
    venta = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=folio, series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=DocumentStatus.PENDING, doc_type="ORDER",
        cash_session_id=sesion.id, customer_id=cliente.id,
    )
    db.add(venta); db.commit(); db.refresh(venta); db.refresh(cliente)
    return cliente, venta


def test_el_abono_en_efectivo_sin_caja_abierta_se_rechaza(
    client, db, org, branch_a, cajero_a, auth_cajero_a, gerente_a
):
    """El escenario del hallazgo: la venta nacio en el turno S1 del cajero A,
    S1 cerro cuadrado, y dos dias despues alguien cobra el abono en efectivo
    sin caja abierta. Antes, esos pesos se sumaban al esperado de S1 —un corte
    cerrado— y lo dejaban en faltante."""
    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    cliente, venta = _cliente_con_venta_a_credito(db, org, branch_a, cajero_a, sesion_1)

    sesion_1.status = "CLOSED"
    db.commit(); db.refresh(sesion_1)
    esperado_antes = Decimal(str(compute_expected_cash(db, sesion_1).expected))

    resp = client.post(
        f"/api/customers/{cliente.id}/pay",
        json={"amount": "400", "method": "CASH", "sales_document_id": venta.id},
        headers=auth_cajero_a,
    )
    assert resp.status_code == 409, (
        f"cobrar efectivo sin caja abierta debe rechazarse igual que en el "
        f"checkout; respondio {resp.status_code}: {resp.text[:300]}"
    )
    assert "caja" in resp.json()["detail"].lower()

    # Nada se movio: ni el pago, ni el ledger, ni el saldo del cliente.
    db.expire_all()
    assert db.query(Payment).filter(Payment.organization_id == org.id).count() == 0
    assert db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.organization_id == org.id).count() == 0
    assert db.query(Customer).get(cliente.id).current_balance == Decimal("1000.00")

    esperado_despues = Decimal(str(compute_expected_cash(db, sesion_1).expected))
    assert esperado_despues == esperado_antes == Decimal("0.00"), (
        "el corte ya cerrado no puede moverse por un abono cobrado despues"
    )


def test_el_abono_por_transferencia_sigue_sin_exigir_caja(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    """Lo que no toca el cajon se registra igual sin turno, y sin atribucion."""
    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    cliente, venta = _cliente_con_venta_a_credito(
        db, org, branch_a, cajero_a, sesion_1, folio=3002)
    sesion_1.status = "CLOSED"
    db.commit()

    resp = client.post(
        f"/api/customers/{cliente.id}/pay",
        json={"amount": "400", "method": "TRANSFER", "sales_document_id": venta.id},
        headers=auth_cajero_a,
    )
    assert resp.status_code == 200, resp.text

    pago = db.query(Payment).filter(Payment.organization_id == org.id).one()
    assert pago.cash_session_id is None


def test_el_abono_en_efectivo_con_caja_abierta_se_atribuye_a_esa_caja(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    cliente, venta = _cliente_con_venta_a_credito(
        db, org, branch_a, cajero_a, sesion_1, folio=3003)
    sesion_1.status = "CLOSED"
    db.commit()

    sesion_2 = _abrir_caja(db, org, branch_a, cajero_a)
    resp = client.post(
        f"/api/customers/{cliente.id}/pay",
        json={"amount": "400", "method": "CASH", "sales_document_id": venta.id},
        headers=auth_cajero_a,
    )
    assert resp.status_code == 200, resp.text

    pago = db.query(Payment).filter(Payment.organization_id == org.id).one()
    assert pago.cash_session_id == sesion_2.id
    assert Decimal(str(compute_expected_cash(db, sesion_2).expected)) == Decimal("400.00")


def test_el_rol_de_oficina_sin_sucursal_sigue_exento(
    client, db, org, branch_a, cajero_a, admin_user, auth_admin
):
    """Misma exencion que el checkout: sin `branch_id` no hay cajon fisico del
    que responder (cobro de back-office, migracion de saldos). El pago se
    registra sin atribucion y cae al respaldo por documento."""
    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    cliente, venta = _cliente_con_venta_a_credito(
        db, org, branch_a, cajero_a, sesion_1, folio=3004)
    admin_user.branch_id = None
    db.commit()

    resp = client.post(
        f"/api/customers/{cliente.id}/pay",
        json={"amount": "400", "method": "CASH", "sales_document_id": venta.id},
        headers={**auth_admin, "X-Organization-ID": str(org.id)},
    )
    assert resp.status_code == 200, resp.text
    pago = db.query(Payment).filter(Payment.organization_id == org.id).one()
    assert pago.cash_session_id is None
