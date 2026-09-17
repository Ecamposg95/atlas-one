"""La variante "principal" de las rutas de escritura debe ser la primera VIVA.

`product.variants[0]` incluye las retiradas (soft delete): tras retirar la
talla S, editar el producto escribia precio/SKU en una variante que ya no se
vende, la matriz comercial mostraba el PBS de la retirada y `target_branch_ids`
reescribia la disponibilidad de la retirada dejando a las vivas sin sucursal.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.products import ProductBranchStatus, ProductVariant
from conftest import _make_product


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def playera(db, org, branch_a):
    """PLY-S (primera, retirada) + PLY-M (viva)."""
    p, v_s = _make_product(db, org, "Playera", "PLY-S", 100, [(branch_a.id, True)])
    v_s.color, v_s.size, v_s.variant_name = "Rojo", "S", "Rojo / S"
    v_m = ProductVariant(
        product_id=p.id, sku="PLY-M", price=Decimal("120"), cost=Decimal("60"),
        color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id,
        created_at=v_s.created_at + timedelta(seconds=1),
    )
    db.add(v_m)
    db.flush()
    db.add(ProductBranchStatus(variant_id=v_m.id, branch_id=branch_a.id,
                               organization_id=org.id, is_active_pos=True, is_visible=True))
    v_s.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return p, v_s, v_m


def test_editar_precio_escribe_en_la_variante_viva(client, db, org, playera, auth_admin):
    p, v_s, v_m = playera
    r = client.put(f"/api/products/{p.id}", json={"price": "199", "cost": "99"},
                   headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text

    db.expire_all()
    v_s = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-S").one()
    v_m = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-M").one()
    assert Decimal(str(v_m.price)) == Decimal("199"), "el precio debe ir a la variante viva"
    assert Decimal(str(v_s.price)) == Decimal("100"), "la retirada no se toca"


def test_la_matriz_comercial_lee_la_variante_viva(client, db, org, branch_a, playera, auth_admin):
    p, v_s, v_m = playera
    r = client.get(f"/api/products/{p.id}/branch-status", headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    filas = r.json()
    assert filas, "la matriz no debe quedar vacia por leer la variante retirada"
    assert {f["variant_id"] for f in filas} == {v_m.id}


def test_target_branch_ids_alcanza_a_todas_las_variantes_vivas(
    client, db, org, branch_a, branch_b, auth_admin
):
    """Con 2 tallas vivas, cambiar las sucursales del producto debe reescribir
    el PBS de las dos: si solo se toca `variants[0]`, la otra talla se queda
    vendible en una sucursal que el usuario acaba de quitar."""
    p, v_s = _make_product(db, org, "Gorra", "GOR-S", 80, [(branch_a.id, True)])
    v_m = ProductVariant(
        product_id=p.id, sku="GOR-M", price=Decimal("80"), cost=Decimal("40"),
        organization_id=org.id, created_at=v_s.created_at + timedelta(seconds=1),
    )
    db.add(v_m)
    db.flush()
    db.add(ProductBranchStatus(variant_id=v_m.id, branch_id=branch_a.id,
                               organization_id=org.id, is_active_pos=True, is_visible=True))
    db.commit()

    r = client.put(f"/api/products/{p.id}", json={"target_branch_ids": [branch_b.id]},
                   headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text

    db.expire_all()
    for sku in ("GOR-S", "GOR-M"):
        v = db.query(ProductVariant).filter(ProductVariant.sku == sku).one()
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all()
        assert [x.branch_id for x in pbs] == [branch_b.id], f"{sku} quedo con el PBS viejo"
