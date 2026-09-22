"""El efectivo entra al corte donde se recibio, no al de la venta original.

Historia (para quien encuentre referencias viejas a esto en el codigo o en
los commits): hubo una version de esta rama que agregaba
`DocumentStatus.PENDING` a `CASH_INCLUDED_STATUSES` para que el abono
parcial de una venta a credito contara en el esperado del turno que lo
recibia -- y los tres tests que hoy pasan sin marca se probaron entonces con
`@pytest.mark.xfail(strict=True)`. Se revirtio (hallazgo ALTA) porque el
mecanismo de esa version generaba un bug peor: la sesion de caja vivia en el
`SalesDocument`, asi que al liquidar el resto de una venta a credito en un
turno *posterior*, el documento entero se reatribuia al `cash_session_id` de
la sesion nueva (rama `existing_sale` en `app/routers/sales.py`) -- lo que
arrastraba consigo el abono que ya se habia cobrado en el turno viejo,
VACIANDO retroactivamente el esperado de un corte que un gerente ya pudo
haber cerrado y dado por bueno.

El arreglo real fue de modelo de datos, no de esta tupla: `Payment` gano su
propio `cash_session_id` (independiente del documento), y
`compute_expected_cash` prefiere esa atribucion por pago sobre la del
documento (ver `app/services/cash_reconciliation.py`). Con eso en pie,
liquidar el resto en otro turno ya no reatribuye el abono viejo -- cada pago
conserva la sesion que lo cobro -- y `DocumentStatus.PENDING` volvio a
`CASH_INCLUDED_STATUSES` sin reintroducir el bug. Los tres tests de abajo,
que antes fijaban el defecto con `xfail`, ahora fijan el comportamiento
correcto sin marca alguna.

Nota de diseño -- por que las ventas PENDING se siembran directo en BD (como
ya hace `test_cash_warning_ventas_sin_corte.py`) en vez de vía POST completo a
`/api/sales/`: el guard H-1 ("Pagos insuficientes") rechaza cualquier POST
cuyo `total_paid` no cubra el total con tolerancia de 1 centavo, y una venta a
credito puro (`payments: []`) dispara un bug preexistente y ajeno a esta tarea
-- `sum()` de una lista vacia devuelve `int 0` en vez de `Decimal(0)`, y
`total_paid.quantize(...)` truena luego con `AttributeError` -- asi que ese
camino no sirve hoy para sembrar el estado que este test necesita. Ese bug se
corrigio por separado en `app/routers/sales.py` (hallazgo #7 de la misma
revision), pero se dejo aqui la nota porque explica por que estos tests
siguen sembrando PENDING directo en BD en vez de vía POST.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, PaymentMethod, Payment, SalesDocument
from app.services.cash_reconciliation import compute_expected_cash


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


def _venta_pendiente(db, org, branch, user, sesion, total="100.00", folio=999):
    """Venta a credito (PENDING) ya vinculada a una sesion de caja, sin pagos
    todavia -- mimetiza lo que deja `/api/sales/` para una venta a plazos."""
    s = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=folio, series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=DocumentStatus.PENDING, doc_type="ORDER",
        cash_session_id=sesion.id,
    )
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_abono_parcial_en_efectivo_entra_al_esperado(db, org, branch_a, cajero_a):
    """Venta a credito con abono en efectivo: los pesos estan en el cajon."""
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion)

    # Abono parcial en efectivo (40 de los 100 que debe la venta).
    db.add(Payment(sales_document_id=venta.id, amount=Decimal("40.00"),
                   method=PaymentMethod.CASH, organization_id=org.id))
    db.commit()

    esperado = Decimal(str(compute_expected_cash(db, sesion).expected))
    assert esperado == Decimal("40.00"), (
        f"los 40 pesos del abono estan en el cajon; el esperado dice {esperado}"
    )


def test_completar_venta_pendiente_en_turno_posterior_reasigna_la_sesion(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """El resto de una venta a credito, liquidado en un turno distinto al que
    la abrio, debe contar para el corte de HOY -- no quedar atribuido a un
    turno viejo que probablemente ya esta cerrado.
    """
    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]
    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion_1)
    assert venta.cash_session_id == sesion_1.id

    # El turno 1 cierra sin que el cliente haya liquidado nada.
    close_resp = client.post(
        "/api/cash/close", json={"closing_balance": "0.00"},
        headers={**auth_cajero_a, "X-Organization-ID": str(org.id)},
    )
    assert close_resp.status_code in (200, 201), close_resp.text

    # Turno 2 (mismo cajero, sesion distinta): el cliente liquida el total via
    # el mismo endpoint de venta (rama `existing_sale`, `sale_in.id=venta.id`).
    sesion_2 = _abrir_caja(db, org, branch_a, cajero_a)

    resp2 = client.post("/api/sales/", json={
        "id": venta.id,
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert resp2.status_code in (200, 201), resp2.text

    db.refresh(venta)
    assert venta.status == DocumentStatus.PAID
    assert venta.cash_session_id == sesion_2.id, (
        "al liquidarse en un turno distinto al de apertura, el efectivo debe "
        "quedar acreditado al turno de HOY, no al turno (ya cerrado) de la venta original"
    )

    esperado_2 = Decimal(str(compute_expected_cash(db, sesion_2).expected))
    assert esperado_2 == Decimal("100.00"), (
        f"la venta liquidada por completo hoy debe contar entera en el corte de hoy; "
        f"el esperado dice {esperado_2}"
    )


# ── Reactivacion de credito (Task 5) ─────────────────────────────────────────

def test_abono_en_turno_1_y_liquidacion_en_turno_2_no_reescribe_el_corte_cerrado(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    """El escenario completo que motivo el plan: abono parcial en el turno 1,
    turno 1 CERRADO, y liquidacion del resto en el turno 2 -- via el mismo
    endpoint de abono (`/api/customers/{id}/pay`), sin volver a pasar por
    `/api/sales/` (esa ruta borra y recrea los Payment de la venta; no es el
    camino real para "abonar dos veces").

    El esperado del turno 1, ya cerrado, no debe moverse ni un peso cuando el
    cliente liquida el resto despues. El turno 2 solo debe ver el dinero que
    entro fisicamente en el (el resto de la deuda), no la venta completa.
    """
    from app.modules.customers.models import Customer

    customer = Customer(
        name="Cliente a credito", organization_id=org.id,
        has_credit=True, credit_limit=Decimal("1000"), current_balance=Decimal("100"),
    )
    db.add(customer); db.flush()

    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion_1, total="100.00", folio=2001)
    venta.customer_id = customer.id
    db.commit(); db.refresh(venta)

    # Abono parcial en efectivo, turno 1: 40 de los 100.
    resp1 = client.post(
        f"/api/customers/{customer.id}/pay",
        json={"amount": "40", "method": "CASH", "sales_document_id": venta.id},
        headers=auth_cajero_a,
    )
    assert resp1.status_code == 200, resp1.text

    esperado_1_antes = Decimal(str(compute_expected_cash(db, sesion_1).expected))
    assert esperado_1_antes == Decimal("40.00"), (
        f"los 40 del abono deben contar en el turno que los recibio; el esperado dice {esperado_1_antes}"
    )

    # El turno 1 cierra (el gerente ya dio el cuadre por bueno).
    close_resp = client.post(
        "/api/cash/close", json={"closing_balance": "40.00"},
        headers={**auth_cajero_a, "X-Organization-ID": str(org.id)},
    )
    assert close_resp.status_code in (200, 201), close_resp.text

    # Turno 2: mismo cajero, sesion distinta.
    sesion_2 = _abrir_caja(db, org, branch_a, cajero_a)

    # El cliente liquida el resto (60) en el turno 2, mismo endpoint de abono.
    resp2 = client.post(
        f"/api/customers/{customer.id}/pay",
        json={"amount": "60", "method": "CASH", "sales_document_id": venta.id},
        headers=auth_cajero_a,
    )
    assert resp2.status_code == 200, resp2.text

    db.refresh(venta)
    assert venta.status == DocumentStatus.PAID, "el saldo del cliente llego a cero, la venta debe quedar PAID"

    esperado_1_despues = Decimal(str(compute_expected_cash(db, sesion_1).expected))
    assert esperado_1_despues == esperado_1_antes == Decimal("40.00"), (
        "el corte del turno 1, ya cerrado, no debe moverse por una liquidacion "
        f"posterior en otro turno; antes={esperado_1_antes} despues={esperado_1_despues}"
    )

    esperado_2 = Decimal(str(compute_expected_cash(db, sesion_2).expected))
    assert esperado_2 == Decimal("60.00"), (
        "el turno 2 solo debe ver los 60 que entraron fisicamente en el, no "
        f"los 100 de la venta completa; el esperado dice {esperado_2}"
    )


# ── Ronda de correcciones 1 ──────────────────────────────────────────────────
#
# `CASH_INCLUDED_STATUSES` no es privado de `compute_expected_cash`: tambien
# lo reusan `get_session_audit_data` y `get_branch_cash_summary` en
# app/routers/cash.py, pero ahi suman `SalesDocument.total_amount` (no
# `Payment.amount`). Para PAID/REFUNDED_* eso es seguro porque
# `approve_return` reescribe `total_amount` al neto. PENDING NO tiene ese
# ajuste: su `total_amount` es la venta completa, deuda incluida -- agregar
# PENDING a esa misma tupla (como hizo la primera version de esta tarea)
# inflaba "ventas totales" y "tickets" del corte con dinero que el cliente
# todavia no termina de pagar. Ver `SALES_REPORT_STATUSES` en
# app/services/cash_reconciliation.py.

def test_venta_pendiente_no_infla_kpis_del_corte_de_sesion(db, org, branch_a, cajero_a):
    """Un abono en efectivo SI debe sumar al esperado y al desglose de pagos,
    pero la venta (PENDING, con deuda restante) NO debe aparecer como ingreso
    reconocido en total_sales/total_tickets -- ese dinero fantasma llegaria al
    ticket termico, al PDF y al dashboard de sesion que el dueño lee.
    """
    from app.routers.cash import get_session_audit_data

    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion, total="5000.00")
    db.add(Payment(sales_document_id=venta.id, amount=Decimal("200.00"),
                   method=PaymentMethod.CASH, organization_id=org.id))
    db.commit()

    audit = get_session_audit_data(db, sesion.id)

    assert audit["kpis"]["total_sales"] == 0.0, (
        f"la venta PENDING (deuda de 4800 sin cobrar) no debe contarse en "
        f"ventas totales; kpis={audit['kpis']}"
    )
    assert audit["kpis"]["total_tickets"] == 0, (
        f"un ticket sin liquidar no debe contarse como ticket vendido; kpis={audit['kpis']}"
    )
    assert audit["payments"]["cash"]["total"] == 200.0, (
        "los 200 del abono si deben aparecer en el desglose de efectivo cobrado por metodo"
    )
    assert audit["expected"]["cash_physical"] == 200.0, (
        "el efectivo fisico esperado si debe incluir el abono"
    )


def test_venta_pendiente_no_infla_el_corte_de_sucursal(
    client, db, org, branch_a, cajero_a, gerente_a, auth_gerente_a
):
    """Mismo defecto, endpoint de resumen de sucursal (`get_branch_cash_summary`,
    consumido por gerentes/admin para ver el corte consolidado del dia)."""
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    venta = _venta_pendiente(db, org, branch_a, cajero_a, sesion, total="5000.00")
    db.add(Payment(sales_document_id=venta.id, amount=Decimal("200.00"),
                   method=PaymentMethod.CASH, organization_id=org.id))
    db.commit()

    resp = client.get(
        f"/api/cash/branch-summary?branch_id={branch_a.id}",
        headers={**auth_gerente_a, "X-Organization-ID": str(org.id)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["totals"]["sales"] == 0.0, (
        f"la venta PENDING no debe contarse en las ventas totales de sucursal; totals={data['totals']}"
    )
    assert data["totals"]["tickets"] == 0, (
        f"un ticket sin liquidar no debe contarse en el corte de sucursal; totals={data['totals']}"
    )
    assert data["totals"]["cash"] == 200.0, (
        "los 200 del abono si deben sumar al efectivo consolidado de la sucursal"
    )

    cajero_row = next(c for c in data["cashiers"] if c["session_id"] == sesion.id)
    assert cajero_row["sales"] == 0.0
    assert cajero_row["tickets"] == 0
    assert cajero_row["expected_cash"] == 200.0
