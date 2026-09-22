"""Ronda de correcciones 1 sobre Task 5.

`compute_expected_cash` ya usa atribución por pago (`Payment.cash_session_id`)
desde la Task 1. Pero `payment_stats` en `get_session_audit_data` y en
`get_branch_cash_summary` (ambos en `app/routers/cash.py`) seguían filtrando
por `session_sales_filter` -- atribución a nivel DOCUMENTO -- así que al
reactivar `DocumentStatus.PENDING` en Task 5, el mismo defecto que este plan
existe para cerrar volvió a manifestarse en el ticket de sesión y en el
resumen de sucursal: un abono cobrado en el turno 1 y liquidado en el turno 2
se reportaba entero (total Y count) bajo la sesión del turno 1, aunque ya
estuviera cerrada.

El efectivo estaba parcialmente protegido porque ambos endpoints sobreescriben
`payments.cash.total` / `totals.cash` con `breakdown.net_cash` (ya correcto),
pero el `count` de pagos en efectivo y el total/count de métodos no-efectivo
(TRANSFER, CARD) seguían viniendo del query roto. Estas pruebas cubren ambos
endpoints, el `count`, y un método no-efectivo.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.sales import DocumentStatus, Payment, SalesDocument
from app.modules.customers.models import Customer


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                     opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _venta_pendiente(db, org, branch, user, sesion, customer, total, folio):
    s = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        customer_id=customer.id,
        folio=folio, series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=DocumentStatus.PENDING, doc_type="ORDER",
        cash_session_id=sesion.id,
    )
    db.add(s); db.commit(); db.refresh(s)
    return s


def _abonar(client, auth, customer, venta, amount, method):
    resp = client.post(
        f"/api/customers/{customer.id}/pay",
        json={"amount": str(amount), "method": method, "sales_document_id": venta.id},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    return resp


def test_ticket_de_sesion_no_se_reescribe_por_liquidacion_en_otro_turno(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    """`get_session_audit_data`: abono en turno 1 (TRANSFER y CASH), turno 1
    cerrado, liquidacion del resto en turno 2. El ticket del turno 1 no debe
    cambiar (ni el total ni el count de pagos), y el turno 2 solo debe ver
    el dinero que entro en el.
    """
    from app.routers.cash import get_session_audit_data

    customer_transfer = Customer(
        name="Cliente transferencia", organization_id=org.id,
        has_credit=True, credit_limit=Decimal("1000"), current_balance=Decimal("100"),
    )
    customer_cash = Customer(
        name="Cliente efectivo", organization_id=org.id,
        has_credit=True, credit_limit=Decimal("1000"), current_balance=Decimal("100"),
    )
    db.add_all([customer_transfer, customer_cash]); db.flush()

    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    venta_transfer = _venta_pendiente(db, org, branch_a, cajero_a, sesion_1, customer_transfer, "100.00", 5001)
    venta_cash = _venta_pendiente(db, org, branch_a, cajero_a, sesion_1, customer_cash, "100.00", 5002)

    # Abonos parciales en el turno 1: 40 de cada uno.
    _abonar(client, auth_cajero_a, customer_transfer, venta_transfer, "40", "TRANSFER")
    _abonar(client, auth_cajero_a, customer_cash, venta_cash, "40", "CASH")

    audit_1_antes = get_session_audit_data(db, sesion_1.id)
    assert audit_1_antes["payments"]["transfer"] == {"total": 40.0, "count": 1}
    assert audit_1_antes["payments"]["cash"] == {"total": 40.0, "count": 1}

    # El turno 1 cierra.
    close_resp = client.post(
        "/api/cash/close", json={"closing_balance": "40.00"},
        headers={**auth_cajero_a, "X-Organization-ID": str(org.id)},
    )
    assert close_resp.status_code in (200, 201), close_resp.text

    # Turno 2: liquidacion del resto (60 de cada uno).
    sesion_2 = _abrir_caja(db, org, branch_a, cajero_a)
    _abonar(client, auth_cajero_a, customer_transfer, venta_transfer, "60", "TRANSFER")
    _abonar(client, auth_cajero_a, customer_cash, venta_cash, "60", "CASH")

    db.refresh(venta_transfer); db.refresh(venta_cash)
    assert venta_transfer.status == DocumentStatus.PAID
    assert venta_cash.status == DocumentStatus.PAID

    # El ticket del turno 1, ya cerrado, no debe moverse ni un peso ni un pago.
    audit_1_despues = get_session_audit_data(db, sesion_1.id)
    assert audit_1_despues["payments"]["transfer"] == {"total": 40.0, "count": 1}, (
        f"el turno 1 (cerrado) no debe reescribirse por la liquidacion en el turno 2; "
        f"payments={audit_1_despues['payments']}"
    )
    assert audit_1_despues["payments"]["cash"] == {"total": 40.0, "count": 1}, (
        "el count de efectivo del turno 1 tampoco debe moverse "
        f"payments={audit_1_despues['payments']}"
    )

    # El turno 2 solo debe ver el dinero que entro en el (60 de cada uno).
    audit_2 = get_session_audit_data(db, sesion_2.id)
    assert audit_2["payments"]["transfer"] == {"total": 60.0, "count": 1}, (
        f"el turno 2 solo cobro 60 por transferencia; payments={audit_2['payments']}"
    )
    assert audit_2["payments"]["cash"] == {"total": 60.0, "count": 1}, (
        f"el turno 2 solo cobro 60 en efectivo; payments={audit_2['payments']}"
    )


def test_resumen_de_sucursal_no_se_reescribe_por_liquidacion_en_otro_turno(
    client, db, org, branch_a, cajero_a, auth_cajero_a, gerente_a, auth_gerente_a
):
    """`get_branch_cash_summary`: mismo escenario, endpoint de resumen de
    sucursal que consumen gerentes/admin (`/api/cash/branch-summary`)."""
    customer = Customer(
        name="Cliente transferencia sucursal", organization_id=org.id,
        has_credit=True, credit_limit=Decimal("1000"), current_balance=Decimal("100"),
    )
    db.add(customer); db.flush()

    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion_1, customer, "100.00", 5003)

    _abonar(client, auth_cajero_a, customer, venta, "40", "TRANSFER")

    close_resp = client.post(
        "/api/cash/close", json={"closing_balance": "0.00"},
        headers={**auth_cajero_a, "X-Organization-ID": str(org.id)},
    )
    assert close_resp.status_code in (200, 201), close_resp.text

    sesion_2 = _abrir_caja(db, org, branch_a, cajero_a)
    _abonar(client, auth_cajero_a, customer, venta, "60", "TRANSFER")

    db.refresh(venta)
    assert venta.status == DocumentStatus.PAID

    resp = client.get(
        f"/api/cash/branch-summary?branch_id={branch_a.id}",
        headers={**auth_gerente_a, "X-Organization-ID": str(org.id)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    fila_1 = next(c for c in data["cashiers"] if c["session_id"] == sesion_1.id)
    fila_2 = next(c for c in data["cashiers"] if c["session_id"] == sesion_2.id)

    assert fila_1["transfer"] == 40.0, (
        f"la fila del turno 1 (cerrado) no debe reescribirse por la liquidacion en el turno 2; fila={fila_1}"
    )
    assert fila_2["transfer"] == 60.0, (
        f"la fila del turno 2 solo debe ver los 60 que cobro; fila={fila_2}"
    )
    assert data["totals"]["transfer"] == 100.0, (
        f"el total consolidado de sucursal si debe sumar los 100 entre ambos turnos; totals={data['totals']}"
    )
