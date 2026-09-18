"""El nombre del cliente viaja en la venta.

El POS manda `customer_id` y nunca `customer_name`, así que una venta a un cliente
de CRM quedaba con `customer_name = NULL` y el historial decía "Público general".
Y un nombre libre (sin CRM) debe guardarse tal cual.

Nota: se usa `cajero_a`/`auth_cajero_a` (no `auth_admin`) porque `admin_user` está
en `hq_branch` — una sucursal HQ sin stock ni caja propios en estos fixtures — y
`create_sale` exige stock y caja abierta en la sucursal del usuario que vende
(gate H-5), sin excepción por rol para el stock. `cajero_a` está en `branch_a`,
que es donde `_make_product` activa el producto.
"""
from decimal import Decimal

from conftest import _make_product
from app.modules.customers.models import Customer
from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import SalesDocument


def _preparar_pos(db, org, branch, user):
    """Habilita el módulo POS y abre una sesión de caja — mismo setup que
    tests/test_sales_idempotency.py, necesario para que create_sale acepte
    pagos en efectivo."""
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta")); db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "pos").first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    if db.query(CashSession).filter(
        CashSession.user_id == user.id, CashSession.closed_at.is_(None)).first() is None:
        db.add(CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                            opening_balance=Decimal("0"), status="OPEN"))
    db.commit()


def _venta(client, headers, sku, **extra):
    body = {
        "items": [{"sku": sku, "quantity": 1, "unit_price": 10}],
        "payments": [{"method": "CASH", "amount": 10}],
        "doc_type": "SALE",
    }
    body.update(extra)
    return client.post("/api/sales/", json=body, headers=headers)


def test_customer_id_sin_nombre_rellena_el_nombre(client, auth_cajero_a, db, org, branch_a, cajero_a):
    _preparar_pos(db, org, branch_a, cajero_a)
    _make_product(db, org, "Pluma", "SKU-CLI-1", 10.0, branches_active=[(branch_a.id, True)])
    cliente = Customer(name="Patricio Pérez", organization_id=org.id)
    db.add(cliente); db.flush()
    r = _venta(client, auth_cajero_a, "SKU-CLI-1", customer_id=cliente.id)
    assert r.status_code == 200, r.text
    doc = db.query(SalesDocument).filter(SalesDocument.customer_id == cliente.id).one()
    assert doc.customer_name == "Patricio Pérez"


def test_nombre_libre_se_guarda_sin_cliente(client, auth_cajero_a, db, org, branch_a, cajero_a):
    _preparar_pos(db, org, branch_a, cajero_a)
    _make_product(db, org, "Pluma", "SKU-CLI-2", 10.0, branches_active=[(branch_a.id, True)])
    r = _venta(client, auth_cajero_a, "SKU-CLI-2", customer_name="  Sr. Estadounidense ")
    assert r.status_code == 200, r.text
    doc = db.query(SalesDocument).filter(SalesDocument.customer_name.isnot(None)).order_by(SalesDocument.created_at.desc()).first()
    assert doc.customer_id is None
    assert doc.customer_name == "Sr. Estadounidense"


def test_nombre_explicito_gana_sobre_el_del_cliente(client, auth_cajero_a, db, org, branch_a, cajero_a):
    _preparar_pos(db, org, branch_a, cajero_a)
    _make_product(db, org, "Pluma", "SKU-CLI-3", 10.0, branches_active=[(branch_a.id, True)])
    cliente = Customer(name="Registrado", organization_id=org.id)
    db.add(cliente); db.flush()
    r = _venta(client, auth_cajero_a, "SKU-CLI-3", customer_id=cliente.id, customer_name="Como lo dijo la cajera")
    assert r.status_code == 200, r.text
    doc = db.query(SalesDocument).filter(SalesDocument.customer_id == cliente.id).one()
    assert doc.customer_name == "Como lo dijo la cajera"
