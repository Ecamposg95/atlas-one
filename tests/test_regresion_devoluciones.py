"""Regresión de la auditoría funcional del backend (2026-09-22) — devoluciones.

C-6: `create_return` recalculaba el reembolso como `quantity * unit_price`
(precio PRE-descuento). Con 2 piezas de $100 al 50% (el cliente paga $100 en
total), devolver una reembolsaba $100 — el doble de lo pagado por esa pieza.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule


def _h(headers, org):
    return {**headers, "X-Organization-ID": str(org.id)}


def _preparar_pos(db, org, branch, user):
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta"))
        db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "pos",
    ).first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    if db.query(CashSession).filter(
        CashSession.user_id == user.id, CashSession.closed_at.is_(None)
    ).first() is None:
        db.add(CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                           opening_balance=Decimal("0"), status="OPEN"))
    db.commit()


def test_c6_la_devolucion_reembolsa_lo_realmente_cobrado(
    client, db, org, branch_a, admin_user, auth_admin, products_setup
):
    admin_user.branch_id = branch_a.id
    db.add(admin_user)
    db.commit()
    _preparar_pos(db, org, branch_a, admin_user)
    _, variant = products_setup["product_a"]  # precio 100
    h = _h(auth_admin, org)

    venta = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 2, "discount": 50.0}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=h)
    assert venta.status_code == 200, venta.text
    sale_id = venta.json()["sale_id"]

    detalle = client.get(f"/api/sales/{sale_id}", headers=h)
    assert detalle.status_code == 200, detalle.text
    linea = detalle.json()["lines"][0]
    pagado_por_unidad = Decimal(str(linea["total_line"])) / 2

    dev = client.post("/api/returns/", json={
        "sale_id": sale_id,
        "reason": "Regresión C-6",
        "total_refunded": "1.00",   # el server recalcula
        "refund_method": "CASH",
        "items": [{
            "variant_id": variant.id,
            "quantity": "1",
            "refund_amount": "1.00",  # idem
            "is_inventory_reentry": True,
        }],
    }, headers=h)
    assert dev.status_code in (200, 201), dev.text

    reembolso = Decimal(str(dev.json()["items"][0]["refund_amount"]))
    assert reembolso == pagado_por_unidad.quantize(Decimal("0.01"))
    assert reembolso == Decimal("50.00")
    assert Decimal(str(dev.json()["total_refunded"])) == Decimal("50.00")


def test_c6_sin_descuento_el_reembolso_no_cambia(
    client, db, org, branch_a, admin_user, auth_admin, products_setup
):
    admin_user.branch_id = branch_a.id
    db.add(admin_user)
    db.commit()
    _preparar_pos(db, org, branch_a, admin_user)
    _, variant = products_setup["product_a"]
    h = _h(auth_admin, org)

    venta = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 2}],
        "payments": [{"method": "CASH", "amount": "200.00"}],
    }, headers=h)
    assert venta.status_code == 200, venta.text
    sale_id = venta.json()["sale_id"]

    dev = client.post("/api/returns/", json={
        "sale_id": sale_id,
        "reason": "Regresión C-6 (control)",
        "total_refunded": "1.00",
        "refund_method": "CASH",
        "items": [{
            "variant_id": variant.id,
            "quantity": "1",
            "refund_amount": "1.00",
            "is_inventory_reentry": True,
        }],
    }, headers=h)
    assert dev.status_code in (200, 201), dev.text
    assert Decimal(str(dev.json()["items"][0]["refund_amount"])) == Decimal("100.00")
