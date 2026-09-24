"""Cobrar propina o marcar factura exige la capacidad, no solo la pantalla.

Antes del 24/09/26 el servidor aceptaba propina de cualquier tienda y lo unico
que validaba era que no fuera negativa, asi que esconder el boton no bastaba.

Se reusan los helpers y fixtures de tests/test_checkout_atribuye_caja.py:
`products_setup["product_a"]` es una variante de $100 habilitada en la sucursal A.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule


def _prender(db, org, clave):
    if db.query(Module).filter(Module.key == clave).first() is None:
        db.add(Module(key=clave, name=clave))
        db.flush()
    fila = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == clave,
    ).first()
    if fila is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=clave, is_enabled=True))
    else:
        fila.is_enabled = True
    db.commit()


def _preparar(db, org, branch, user):
    """Habilita el POS y abre caja, igual que test_checkout_atribuye_caja.py."""
    _prender(db, org, "pos")
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _vender(client, auth, org, variant, total, **extra):
    cuerpo = {
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": str(total)}],
    }
    cuerpo.update(extra)
    return client.post("/api/sales/", json=cuerpo,
                       headers={**auth, "X-Organization-ID": str(org.id)})


def test_sin_el_modulo_la_propina_se_rechaza(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "150.00", tip_amount=50)
    assert r.status_code == 403, r.text
    assert "propina" in r.json()["detail"].lower()


def test_con_el_modulo_la_propina_pasa(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _prender(db, org, "tips")
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "150.00", tip_amount=50)
    assert r.status_code in (200, 201), r.text


def test_una_venta_sin_propina_no_se_estorba(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "100.00")
    assert r.status_code in (200, 201), r.text


def test_sin_el_modulo_la_factura_se_rechaza(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "100.00", requires_invoice=True)
    assert r.status_code == 403, r.text
    assert "factura" in r.json()["detail"].lower()
