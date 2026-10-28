"""Auditoría del módulo de crédito / clientes (2026-10-28).

Cada prueba fija un hallazgo: fiar sin la casilla de crédito dejaba la deuda
sin rastro; cancelar una venta fiada tronaba con 500 (`entry_type` no existe
en el modelo); el abono libre bajaba el saldo pero dejaba los tickets PENDING
para siempre; el abono a un ticket se comparaba contra el saldo TOTAL del
cliente; la antigüedad de saldos sumaba todos los cargos históricos sin restar
abonos; una devolución en efectivo de una venta fiada le entregaba dinero a
quien no había pagado; y `unpaid-documents` seguía mostrando tickets
cancelados.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.crud import returns as crud_returns
from app.models.cash import CashMovement, CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, PaymentMethod, SalesDocument
from app.modules.customers.models import Customer, CustomerLedgerEntry
from app.modules.customers.services import antiguedad_por_cargo
from app.schemas.returns import SaleReturnCreate


def _habilitar(db, org, *keys):
    for key in keys:
        if db.query(Module).filter(Module.key == key).first() is None:
            db.add(Module(key=key, name=key)); db.flush()
        if db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == key).first() is None:
            db.add(OrganizationModule(
                organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _cliente(db, org, nombre="Clienta", has_credit=False):
    c = Customer(name=nombre, organization_id=org.id, has_credit=has_credit,
                 credit_limit=Decimal("0"), current_balance=Decimal("0"))
    db.add(c); db.commit(); db.refresh(c)
    return c


def _fiar(client, h, cliente, sku, qty=1, pagos=None):
    """Venta con cliente dejando saldo (producto A vale 100)."""
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": sku, "quantity": qty}],
        "payments": pagos or [],
    }, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _asientos(db, cliente):
    return db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.customer_id == cliente.id,
    ).order_by(CustomerLedgerEntry.id.asc()).all()


def _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _habilitar(db, org, "pos", "crm")
    _, variant = products_setup["product_a"]
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    _abrir_caja(db, org, branch_a, cajero_a)
    return h, variant


# --------------------------------------------------------------------------
# Fiar
# --------------------------------------------------------------------------
def test_fiar_a_cliente_sin_casilla_de_credito_carga_su_cuenta(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """La cajera decide quién fía: cualquier cliente registrado. Antes, sin
    `has_credit`, la venta quedaba PENDING y la deuda no existía en ningún
    lado."""
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org, has_credit=False)

    venta = _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "40.00"}])
    assert venta["credit_debt"] == 60.0

    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("60.00")
    assert cliente.has_credit is True, "la casilla se enciende sola al fiar"
    asientos = _asientos(db, cliente)
    assert len(asientos) == 1
    assert asientos[0].sales_document_id == venta["sale_id"]
    assert Decimal(str(asientos[0].amount)) == Decimal("60.00")


# --------------------------------------------------------------------------
# Cancelar
# --------------------------------------------------------------------------
def test_cancelar_una_venta_fiada_revierte_la_deuda_en_vez_de_tronar(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku)

    r = client.delete(f"/api/sales/{venta['sale_id']}", params={"reason": "Se arrepintió"}, headers=h)
    assert r.status_code == 200, r.text

    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00")
    doc = db.query(SalesDocument).filter(SalesDocument.id == venta["sale_id"]).one()
    assert doc.status == DocumentStatus.CANCELLED
    montos = [Decimal(str(a.amount)) for a in _asientos(db, cliente)]
    assert montos == [Decimal("100.00"), Decimal("-100.00")]

    r = client.get(f"/api/customers/{cliente.id}/unpaid-documents", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == [], "un ticket cancelado ya no está por cobrar"


# --------------------------------------------------------------------------
# Abonos
# --------------------------------------------------------------------------
def test_abono_libre_se_reparte_del_ticket_mas_viejo_al_mas_nuevo(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    v1 = _fiar(client, h, cliente, variant.sku)           # 100
    v2 = _fiar(client, h, cliente, variant.sku, qty=2)    # 200

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "150.00"}, headers=h)
    assert r.status_code == 200, r.text

    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("150.00")
    d1 = db.query(SalesDocument).filter(SalesDocument.id == v1["sale_id"]).one()
    d2 = db.query(SalesDocument).filter(SalesDocument.id == v2["sale_id"]).one()
    assert d1.status == DocumentStatus.PAID, "el ticket viejo se cubrió completo"
    assert d2.status == DocumentStatus.PENDING

    abonos = [a for a in _asientos(db, cliente) if a.amount < 0]
    assert [(a.sales_document_id, Decimal(str(a.amount))) for a in abonos] == [
        (v1["sale_id"], Decimal("-100.00")),
        (v2["sale_id"], Decimal("-50.00")),
    ]

    r = client.get(f"/api/customers/{cliente.id}/unpaid-documents", headers=h)
    assert [(d["id"], d["balance"]) for d in r.json()] == [(v2["sale_id"], 150.0)]


def test_abono_mayor_que_la_deuda_deja_saldo_a_favor(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    v1 = _fiar(client, h, cliente, variant.sku)  # 100

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "120.00"}, headers=h)
    assert r.status_code == 200, r.text
    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("-20.00")
    assert db.query(SalesDocument).filter(
        SalesDocument.id == v1["sale_id"]).one().status == DocumentStatus.PAID
    abonos = [(a.sales_document_id, Decimal(str(a.amount))) for a in _asientos(db, cliente) if a.amount < 0]
    assert abonos == [(v1["sale_id"], Decimal("-100.00")), (None, Decimal("-20.00"))]


def test_abono_a_un_ticket_no_puede_exceder_lo_que_debe_ese_ticket(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    v1 = _fiar(client, h, cliente, variant.sku, qty=2)  # 200
    v2 = _fiar(client, h, cliente, variant.sku)         # 100

    # Antes pasaba: 150 < saldo total (300), aunque el ticket vale 100.
    r = client.post(f"/api/customers/{cliente.id}/pay",
                    json={"amount": "150.00", "sales_document_id": v2["sale_id"]}, headers=h)
    assert r.status_code == 422, r.text
    assert "ticket" in r.json()["detail"].lower()

    r = client.post(f"/api/customers/{cliente.id}/pay",
                    json={"amount": "100.00", "sales_document_id": v2["sale_id"]}, headers=h)
    assert r.status_code == 200, r.text
    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("200.00")
    assert db.query(SalesDocument).filter(SalesDocument.id == v2["sale_id"]).one().status == DocumentStatus.PAID, (
        "el ticket liquidado pasa a PAID aunque el cliente siga debiendo otro"
    )
    assert db.query(SalesDocument).filter(SalesDocument.id == v1["sale_id"]).one().status == DocumentStatus.PENDING


# --------------------------------------------------------------------------
# Antigüedad de saldos
# --------------------------------------------------------------------------
def _asiento(fecha, monto, id_):
    e = CustomerLedgerEntry(customer_id=1, organization_id=1, amount=Decimal(str(monto)))
    e.created_at = fecha
    e.id = id_
    return e


def test_antiguedad_aplica_abonos_al_cargo_mas_viejo():
    hoy = datetime(2026, 10, 28, tzinfo=timezone.utc)
    asientos = [
        _asiento(hoy - timedelta(days=100), 1000, 1),
        _asiento(hoy - timedelta(days=50), -1000, 2),
        _asiento(hoy - timedelta(days=10), 200, 3),
        _asiento(hoy - timedelta(days=45), 300, 4),
        _asiento(hoy - timedelta(days=5), -100, 5),
    ]
    b = antiguedad_por_cargo(asientos, ahora=hoy)
    # Debe 400: el cargo de 300 (45 días) menos 100 abonados = 200, más 200 recientes.
    assert b == {
        "current": Decimal("200"),
        "31_60": Decimal("200"),
        "61_90": Decimal("0.00"),
        "91_plus": Decimal("0.00"),
    }


def test_antiguedad_con_saldo_a_favor_previo():
    hoy = datetime(2026, 10, 28, tzinfo=timezone.utc)
    asientos = [
        _asiento(hoy - timedelta(days=20), -50, 1),
        _asiento(hoy - timedelta(days=3), 80, 2),
    ]
    b = antiguedad_por_cargo(asientos, ahora=hoy)
    assert b["current"] == Decimal("30")
    assert sum(b.values()) == Decimal("30")


def test_reporte_de_antiguedad_cuadra_con_el_saldo(client, db, org, auth_admin):
    _habilitar(db, org, "crm")
    cliente = _cliente(db, org)
    hoy = datetime.now(timezone.utc)
    for dias, monto in ((120, 1000), (60, -1000), (12, 250)):
        e = CustomerLedgerEntry(customer_id=cliente.id, organization_id=org.id,
                                amount=Decimal(str(monto)))
        e.created_at = hoy - timedelta(days=dias)
        db.add(e)
    cliente.current_balance = Decimal("250")
    db.commit()

    r = client.get("/api/reports/aging-report", headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    fila = next(c for c in r.json()["customers"] if c["customer_id"] == cliente.id)
    assert Decimal(str(fila["total_balance"])) == Decimal("250")
    assert Decimal(str(fila["current_0_30"])) == Decimal("250")
    assert Decimal(str(fila["overdue_91_plus"])) == Decimal("0"), (
        "el cargo de hace 120 días ya se pagó: no puede seguir en +90"
    )


# --------------------------------------------------------------------------
# Devoluciones de ventas fiadas
# --------------------------------------------------------------------------
def _devolucion(db, org, branch, user, sale_id, variant, monto, qty=1, metodo=PaymentMethod.CASH):
    return crud_returns.create_return(
        db=db,
        return_in=SaleReturnCreate(
            sale_id=sale_id, reason="prueba", total_refunded=monto, refund_method=metodo,
            items=[{"variant_id": variant.id, "quantity": qty, "refund_amount": monto}],
        ),
        user_id=user.id, branch_id=branch.id, organization_id=org.id,
    )


def _salidas_de_caja(db):
    return db.query(CashMovement).filter(CashMovement.type == "OUT").all()


def test_devolver_mercancia_fiada_baja_la_deuda_y_no_saca_efectivo(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku, qty=2)  # 200, nada pagado

    d = _devolucion(db, org, branch_a, cajero_a, venta["sale_id"], variant, Decimal("100.00"))
    crud_returns.approve_return(db, d.id, supervisor_id=cajero_a.id, organization_id=org.id)
    db.commit()

    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("100.00")
    assert _salidas_de_caja(db) == [], "no se le entrega efectivo a quien no había pagado"
    doc = db.query(SalesDocument).filter(SalesDocument.id == venta["sale_id"]).one()
    assert doc.status == DocumentStatus.PENDING, "sigue debiendo la otra pieza"
    assert Decimal(str(doc.total_amount)) == Decimal("100.00")

    d2 = _devolucion(db, org, branch_a, cajero_a, venta["sale_id"], variant, Decimal("100.00"))
    crud_returns.approve_return(db, d2.id, supervisor_id=cajero_a.id, organization_id=org.id)
    db.commit()
    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00")
    assert _salidas_de_caja(db) == []
    assert db.query(SalesDocument).filter(
        SalesDocument.id == venta["sale_id"]).one().status == DocumentStatus.REFUNDED_TOTAL


def test_devolucion_mayor_que_la_deuda_entrega_solo_el_excedente(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku, qty=2, pagos=[{"method": "CASH", "amount": "170.00"}])  # debe 30

    d = _devolucion(db, org, branch_a, cajero_a, venta["sale_id"], variant, Decimal("100.00"))
    crud_returns.approve_return(db, d.id, supervisor_id=cajero_a.id, organization_id=org.id)
    db.commit()

    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00")
    salidas = _salidas_de_caja(db)
    assert [Decimal(str(m.amount)) for m in salidas] == [Decimal("70.00")], (
        "30 cubren la deuda; solo 70 salen del cajón"
    )
    doc = db.query(SalesDocument).filter(SalesDocument.id == venta["sale_id"]).one()
    assert doc.status == DocumentStatus.REFUNDED_PARTIAL


def test_devolucion_de_venta_pagada_no_toca_al_cliente(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """Regresión: la venta cobrada completa con cliente sigue devolviendo el
    dinero entero, como siempre."""
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "100.00"}])

    d = _devolucion(db, org, branch_a, cajero_a, venta["sale_id"], variant, Decimal("100.00"))
    crud_returns.approve_return(db, d.id, supervisor_id=cajero_a.id, organization_id=org.id)
    db.commit()
    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00")
    assert _asientos(db, cliente) == []
    assert [Decimal(str(m.amount)) for m in _salidas_de_caja(db)] == [Decimal("100.00")]
