"""El pago nace atribuido a la caja de quien cobra.

Task 3 del plan `pago-atribuido-a-caja`: hasta aqui, `Payment.cash_session_id`
(Task 1) existe pero nadie lo escribe -- todo pago nace en NULL y cae al
respaldo por documento (`session_sales_filter`, va Task 2). Este archivo
prueba que el checkout (`POST /api/sales/`) lo puebla en las dos ramas que
resuelven la sesion de caja en `app/routers/sales.py`:

1. Venta nueva: el `Payment` se crea con la sesion OPEN del cajero.
2. `existing_sale` (completar una venta PENDING): los pagos nuevos deben
   quedar en la sesion de HOY, no en la sesion (probablemente ya cerrada) que
   abrio la venta a credito. Este es justo el defecto que motivo todo el plan
   (ver cabecera de `tests/test_cash_credito_y_abonos.py`).

   Ronda de correcciones final (MAYOR-1): esa rama ya no borra y recrea los
   `Payment` del documento. Los abonos ya cobrados se conservan con su propia
   atribucion y `sale_in.payments` son solo los pagos nuevos.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, Payment, SalesDocument


def _habilitar_pos(db, org):
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta")); db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "pos").first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    db.commit()


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _preparar(db, org, branch, user):
    """Alias del helper del brief: habilita POS y abre caja."""
    _habilitar_pos(db, org)
    return _abrir_caja(db, org, branch, user)


def test_el_pago_del_checkout_lleva_la_caja(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    sesion = _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]

    resp = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert resp.status_code in (200, 201), resp.text

    pago = db.query(Payment).filter(Payment.organization_id == org.id).one()
    assert pago.cash_session_id == sesion.id, (
        "el pago debe quedar atribuido a la caja abierta del cajero que cobro"
    )


def _venta_pendiente(db, org, branch, user, sesion, total="100.00", folio=999):
    """Venta a credito (PENDING) ya vinculada a una sesion de caja, sin pagos
    todavia -- mimetiza lo que deja `/api/sales/` para una venta a plazos
    (mismo helper que `tests/test_cash_credito_y_abonos.py`)."""
    s = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=folio, series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=DocumentStatus.PENDING, doc_type="ORDER",
        cash_session_id=sesion.id,
    )
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_pagos_recreados_al_completar_venta_pendiente_quedan_en_la_sesion_nueva(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """El defecto que motivo este plan: al liquidar en un turno posterior una
    venta a credito, el checkout borra los pagos viejos y crea unos nuevos
    (rama `existing_sale`). Esos pagos nuevos deben llevar la sesion de HOY,
    no la sesion (ya cerrada) con la que se abrio la venta original.
    """
    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]
    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion_1)

    # El turno 1 cierra sin que el cliente haya liquidado nada.
    close_resp = client.post(
        "/api/cash/close", json={"closing_balance": "0.00"},
        headers={**auth_cajero_a, "X-Organization-ID": str(org.id)},
    )
    assert close_resp.status_code in (200, 201), close_resp.text

    # Turno 2 (mismo cajero, sesion distinta): el cliente liquida el total.
    sesion_2 = _abrir_caja(db, org, branch_a, cajero_a)

    resp2 = client.post("/api/sales/", json={
        "id": venta.id,
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert resp2.status_code in (200, 201), resp2.text

    pago = db.query(Payment).filter(Payment.sales_document_id == venta.id).one()
    assert pago.cash_session_id == sesion_2.id, (
        "el pago recreado al completar la venta pendiente debe quedar en la "
        "sesion nueva (turno 2), no en la sesion original (turno 1, ya "
        "cerrada) -- ese es justo el defecto que este plan existe para cerrar"
    )
    assert pago.cash_session_id != sesion_1.id


def test_liquidar_en_otro_turno_conserva_la_atribucion_del_abono_previo(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """Ronda de correcciones final (MAYOR-1): la prueba de arriba siembra la
    venta PENDING SIN pagos, asi que el `delete()` de la rama `existing_sale`
    no destruye nada y el caso que motivo el plan —abono cobrado en el turno 1
    y liquidacion en el turno 2— nunca se ejercitaba.

    Con un abono previo, borrar y recrear los `Payment` movia los $40 ya
    cobrados del turno 1 al turno 2: el turno 1, cerrado y cuadrado, aparecia
    con un sobrante fantasma de +$40 y el turno 2 con un faltante de -$40.
    La atribucion de un pago ya cobrado no puede perderse al reprocesar el
    documento.
    """
    from app.modules.customers.models import Customer
    from app.services.cash_reconciliation import compute_expected_cash

    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]

    cliente = Customer(
        name="Cliente a credito", organization_id=org.id,
        has_credit=True, credit_limit=Decimal("1000"), current_balance=Decimal("100"),
    )
    db.add(cliente); db.flush()

    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion_1, folio=4001)
    venta.customer_id = cliente.id
    db.commit(); db.refresh(venta); db.refresh(cliente)

    # Turno 1: el cliente abona 40 de los 100, en efectivo, con caja abierta.
    abono = client.post(
        f"/api/customers/{cliente.id}/pay",
        json={"amount": "40", "method": "CASH", "sales_document_id": venta.id},
        headers=auth_cajero_a,
    )
    assert abono.status_code == 200, abono.text
    assert Decimal(str(compute_expected_cash(db, sesion_1).expected)) == Decimal("40.00")

    # El turno 1 cierra contando los 40 reales: cuadra.
    cierre = client.post(
        "/api/cash/close", json={"closing_balance": "40.00"},
        headers={**auth_cajero_a, "X-Organization-ID": str(org.id)},
    )
    assert cierre.status_code in (200, 201), cierre.text
    db.refresh(sesion_1)
    assert Decimal(str(sesion_1.difference)) == Decimal("0.00")

    # Turno 2: se liquida el resto (60) por `/api/sales/`.
    sesion_2 = _abrir_caja(db, org, branch_a, cajero_a)
    resp = client.post("/api/sales/", json={
        "id": venta.id,
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "60.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert resp.status_code in (200, 201), resp.text

    pagos = db.query(Payment).filter(Payment.sales_document_id == venta.id).all()
    por_monto = {Decimal(str(p.amount)): p.cash_session_id for p in pagos}
    assert por_monto == {Decimal("40.00"): sesion_1.id, Decimal("60.00"): sesion_2.id}, (
        f"el abono de 40 debe seguir vivo y en el turno que lo recibio; hay {por_monto}"
    )

    # Ningun corte se mueve: cada turno ve solo el dinero que entro en el.
    assert Decimal(str(compute_expected_cash(db, sesion_1).expected)) == Decimal("40.00"), (
        "el turno 1, cerrado y cuadrado, no puede quedar con sobrante fantasma"
    )
    assert Decimal(str(compute_expected_cash(db, sesion_2).expected)) == Decimal("60.00"), (
        "el turno 2 solo recibio los 60 de la liquidacion"
    )

    db.refresh(venta); db.refresh(cliente)
    assert venta.status == DocumentStatus.PAID
    assert cliente.current_balance == Decimal("0.00"), (
        "el cliente pago 40 + 60 por una venta de 100: no le puede quedar saldo"
    )
