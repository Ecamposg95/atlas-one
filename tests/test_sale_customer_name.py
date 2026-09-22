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
from app.models.organization import Organization
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


def test_customer_id_de_otra_organizacion_se_rechaza(client, auth_cajero_a, db, org, branch_a, cajero_a):
    """Un `customer_id` que existe pero pertenece a OTRA organización se
    rechaza con 404.

    Antes la venta se completaba "solo sin nombre", pero
    `sales_documents.customer_id` quedaba apuntando al cliente ajeno: fuga
    multi-tenant en historial y reportes por cliente (auditoría funcional
    2026-09-22, hallazgo A-2). Ahora el cliente se valida contra la org una
    sola vez, arriba de `create_sale`, y la venta ni siquiera se crea.
    """
    _preparar_pos(db, org, branch_a, cajero_a)
    _make_product(db, org, "Pluma", "SKU-CLI-4", 10.0, branches_active=[(branch_a.id, True)])
    otra_org = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra_org); db.flush()
    cliente_ajeno = Customer(name="Cliente de Otra Org", organization_id=otra_org.id)
    db.add(cliente_ajeno); db.flush()
    r = _venta(client, auth_cajero_a, "SKU-CLI-4", customer_id=cliente_ajeno.id)
    assert r.status_code == 404, r.text
    assert db.query(SalesDocument).filter(
        SalesDocument.organization_id == org.id,
        SalesDocument.customer_id == cliente_ajeno.id,
    ).count() == 0


def _render_ticket_html(cliente_display):
    """Renderiza app/templates/print/ticket.html directo (sin pasar por el
    router/DB) para probar solo la línea `Cliente:` — igual de aislado que
    `tests/test_ticket_layout.py` prueba `_build_header` con SimpleNamespace.

    `lineas` es el contexto que arma `get_sale_print_view` con las cantidades
    ya en Decimal (antes el template multiplicaba el Float de `sale.lines` por
    un Decimal y el endpoint devolvía 500 — auditoría M-6). El endpoint real
    tiene su propia prueba en `tests/test_regresion_ventas.py`."""
    from datetime import datetime, timezone
    from decimal import Decimal
    from types import SimpleNamespace
    from starlette.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")
    line = SimpleNamespace(description="Playera", quantity=Decimal("1"),
                            unit_price=Decimal("100"), variant_id=1)
    sale = SimpleNamespace(
        series="A", folio=1, created_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        requires_invoice=False, tax_amount=Decimal("0"), subtotal=Decimal("100"),
        lines=[line], payments=[],
    )
    tpl = templates.get_template("print/ticket.html")
    return tpl.render({
        "sale": sale, "lineas": [vars(line)], "organization": None,
        "branch": None, "seller": None,
        "approved_returns": None, "cliente_display": cliente_display,
    })


def test_print_view_html_imprime_cliente_cuando_hay_nombre():
    """El ticket HTML sigue el mismo criterio que el térmico: imprime
    "Cliente: <nombre>" cuando `get_sale_print_view` pasó un nombre limpio
    (ver app/routers/sales.py::get_sale_print_view, ~línea 1349)."""
    html = _render_ticket_html("Ana López")
    assert "Cliente: Ana López" in html


def test_print_view_html_sin_nombre_no_imprime_linea():
    """`cliente_display=None` (sin nombre, o "Público General") no agrega la
    línea — ni el `or 'Público General'` que había antes en el template."""
    html = _render_ticket_html(None)
    assert "Cliente:" not in html
