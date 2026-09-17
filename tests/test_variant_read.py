"""Con dos variantes, GET /api/products/{id} devuelve las dos con nombre,
atributos y existencia propia, y los campos aplanados siguen siendo los de la
primera (compatibilidad con las 76 vistas)."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from conftest import _make_product


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
                       qty_on_hand=Decimal("7"), is_active=True))
    db.flush()
    return p, v_s, v_m


def test_detalle_trae_las_dos_variantes_con_stock(client, db, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    r = client.get(f"/api/products/{p.id}", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    data = r.json()
    por_sku = {v["sku"]: v for v in data["variants"]}
    assert por_sku["PLY-S"]["variant_name"] == "Rojo / S"
    assert por_sku["PLY-M"]["color"] == "Rojo" and por_sku["PLY-M"]["size"] == "M"
    assert Decimal(str(por_sku["PLY-S"]["stock_total"])) == Decimal("100")
    assert Decimal(str(por_sku["PLY-M"]["stock_total"])) == Decimal("7")
    # Aplanado = primera variante (orden de creacion), y se dice cual fue.
    assert data["sku"] == "PLY-S"
    assert data["matched_variant_id"] == v_s.id


def test_listado_trae_stock_de_todas_las_variantes(client, db, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    r = client.get("/api/products/", params={"search": "Playera"},
                   headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["id"] == p.id)
    stocks = {v["sku"]: Decimal(str(v["stock_total"])) for v in item["variants"]}
    assert stocks == {"PLY-S": Decimal("100"), "PLY-M": Decimal("7")}
