"""La talla debe verse donde hoy solo se ve el producto: ticket de devolucion
y reportes de existencia."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.products import Product, ProductBranchStatus, ProductVariant
from app.pos_printer import _describe_variant
from conftest import _make_product

# NOTA: `ProductVariant.product` es una relationship con back_populates hacia
# `Product.variants`; SQLAlchemy sincroniza el lado inverso al asignarla, lo
# que exige un objeto ORM real (con _sa_instance_state). Por eso se usa un
# `Product(...)` transitorio (nunca se agrega a `db`) en vez de un objeto
# `type(...)` suelto — el objetivo de la prueba (texto que devuelve
# `_describe_variant`) es el mismo.


def test_describe_variant_agrega_la_talla():
    v = ProductVariant(sku="PLY-M", variant_name="Rojo / M")
    v.product = Product(name="Playera")
    assert _describe_variant(v) == "Playera (Rojo / M)"


def test_describe_variant_omite_estandar():
    v = ProductVariant(sku="GOR", variant_name="Estándar")
    v.product = Product(name="Gorra")
    assert _describe_variant(v) == "Gorra"


@pytest.fixture()
def playera(db, org, branch_a):
    p, v_s = _make_product(db, org, "Playera", "PLY-S", 100, [(branch_a.id, True)])
    v_s.color, v_s.size, v_s.variant_name = "Rojo", "S", "Rojo / S"
    v_m = ProductVariant(product_id=p.id, sku="PLY-M", barcode="7500000000002",
                         price=Decimal("120"), cost=Decimal("60"),
                         color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id)
    db.add(v_m); db.flush()
    db.add(ProductBranchStatus(variant_id=v_m.id, branch_id=branch_a.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v_m.id, branch_id=branch_a.id, organization_id=org.id,
                       qty_on_hand=Decimal("2"), is_active=True))
    db.flush()
    return p, v_s, v_m


def test_dashboard_low_stock_muestra_la_talla(client, db, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    r = client.get("/api/reports/dashboard",
                   headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    names = {row["name"] for row in r.json()["low_stock"]}
    assert "Playera (Rojo / M)" in names
