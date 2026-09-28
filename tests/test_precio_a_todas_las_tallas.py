"""Al editar el producto, la casilla `precio_a_todas_las_tallas` baja el precio
nuevo a todas las tallas vivas. Sin ella, solo cambia la principal (como antes)."""
from decimal import Decimal

import pytest

from app.models.modules import Module, OrganizationModule
from app.models.products import ProductVariant
from conftest import _make_product


def _habilitar(db, org, key):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key)); db.flush()
    om = db.query(OrganizationModule).filter(OrganizationModule.organization_id == org.id,
                                             OrganizationModule.module_key == key).first()
    if om is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    else:
        om.is_enabled = True
    db.commit()


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def playera_con_tallas(client, db, org, branch_a, auth_admin):
    _habilitar(db, org, "variants")
    p, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
    v.size = "Ch"
    db.commit()
    r = client.post(f"/api/products/{p.id}/variants", json={"variants": [
        {"size": "M", "sku": "PLY-M", "price": "100"},
        {"size": "G", "sku": "PLY-G", "price": "120"},
    ]}, headers=_h(auth_admin, org))
    assert r.status_code == 201, r.text
    return p


def _precios(db, product_id):
    db.expire_all()
    return {v.sku: Decimal(str(v.price))
            for v in db.query(ProductVariant).filter(ProductVariant.product_id == product_id)}


def test_con_la_casilla_todas_las_tallas_toman_el_precio(client, db, org, playera_con_tallas, auth_admin):
    r = client.put(f"/api/products/{playera_con_tallas.id}",
                   json={"price": "150", "precio_a_todas_las_tallas": True}, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    assert _precios(db, playera_con_tallas.id) == {"PLY": Decimal("150"), "PLY-M": Decimal("150"), "PLY-G": Decimal("150")}


def test_sin_la_casilla_solo_cambia_la_principal(client, db, org, playera_con_tallas, auth_admin):
    r = client.put(f"/api/products/{playera_con_tallas.id}", json={"price": "150"}, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    assert _precios(db, playera_con_tallas.id) == {"PLY": Decimal("150"), "PLY-M": Decimal("100"), "PLY-G": Decimal("120")}


def test_una_talla_retirada_conserva_su_precio(client, db, org, playera_con_tallas, auth_admin):
    g = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-G").one()
    r = client.delete(f"/api/products/variants/{g.id}", headers=_h(auth_admin, org))
    assert r.status_code in (200, 204), r.text
    r = client.put(f"/api/products/{playera_con_tallas.id}",
                   json={"price": "150", "precio_a_todas_las_tallas": True}, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    assert _precios(db, playera_con_tallas.id) == {"PLY": Decimal("150"), "PLY-M": Decimal("150"), "PLY-G": Decimal("120")}
