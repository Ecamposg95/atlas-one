"""Helpers de las pruebas de cobranza (spec 2026-10-29): caja abierta,
cliente, venta fiada por la API y abono por la API."""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.modules.customers.models import Customer


def _habilitar(db, org, *keys):
    for key in keys:
        if db.query(Module).filter(Module.key == key).first() is None:
            db.add(Module(key=key, name=key)); db.flush()
        if db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == key).first() is None:
            db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _cliente(db, org, nombre="Clienta"):
    c = Customer(name=nombre, organization_id=org.id, has_credit=False,
                 credit_limit=Decimal("0"), current_balance=Decimal("0"))
    db.add(c); db.commit(); db.refresh(c)
    return c


def _fiar(client, h, cliente, sku, pagos=None):
    """Venta con cliente dejando saldo (el producto A vale 100)."""
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER", "customer_id": cliente.id,
        "items": [{"sku": sku, "quantity": 1}], "payments": pagos or [],
    }, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _abonar(client, h, cliente, monto, metodo="CASH", documento=None):
    body = {"amount": str(monto), "method": metodo}
    if documento:
        body["sales_document_id"] = documento
    r = client.post(f"/api/customers/{cliente.id}/pay", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Módulos pos+crm, caja abierta de la cajera A; devuelve (headers, variante A, sesión)."""
    _habilitar(db, org, "pos", "crm")
    _, variant = products_setup["product_a"]
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    return h, variant, sesion
