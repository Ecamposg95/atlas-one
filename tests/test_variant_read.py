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
    # Aplanado = primera variante viva (orden de creacion). `matched_variant_id`
    # queda en None porque nadie empato un codigo: el detalle NO debe fingir que
    # la talla ya esta elegida (es lo que abre el selector en el POS).
    assert data["sku"] == "PLY-S"
    assert data["matched_variant_id"] is None


def test_listado_trae_stock_de_todas_las_variantes(client, db, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    r = client.get("/api/products/", params={"search": "Playera"},
                   headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["id"] == p.id)
    stocks = {v["sku"]: Decimal(str(v["stock_total"])) for v in item["variants"]}
    assert stocks == {"PLY-S": Decimal("100"), "PLY-M": Decimal("7")}


# --- effective_price: lo que el POS debe PINTAR por talla -------------------
# `create_sale` cobra el `price_override` de la sucursal (sales.py:611), pero el
# POS pintaba `variants[*].price` (el precio base): con override el cajero veia
# un precio y el ticket salia con otro. `effective_price` es lo que se cobra;
# `price` sigue siendo el base porque es lo que edita la ficha de variantes.

def test_effective_price_sin_override_es_el_precio_base(client, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    r = client.get(f"/api/products/{p.id}", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    por_sku = {v["sku"]: v for v in r.json()["variants"]}
    assert Decimal(str(por_sku["PLY-S"]["effective_price"])) == Decimal("100")
    assert Decimal(str(por_sku["PLY-M"]["effective_price"])) == Decimal("120")


def test_effective_price_toma_el_override_de_la_sucursal(client, db, org, branch_a, playera, auth_cajero_a):
    """Detalle (`read_product`, sin cache de PBS): las DOS tallas con override."""
    p, v_s, v_m = playera
    for v in (v_s, v_m):
        pbs = (
            db.query(ProductBranchStatus)
            .filter(ProductBranchStatus.variant_id == v.id,
                    ProductBranchStatus.branch_id == branch_a.id)
            .first()
        )
        pbs.price_override = Decimal("89.50")
    db.flush()

    r = client.get(f"/api/products/{p.id}", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    por_sku = {v["sku"]: v for v in r.json()["variants"]}
    for sku in ("PLY-S", "PLY-M"):
        assert Decimal(str(por_sku[sku]["effective_price"])) == Decimal("89.50")
    # El precio BASE no se toca: es el que edita el editor de variantes.
    assert Decimal(str(por_sku["PLY-S"]["price"])) == Decimal("100")
    assert Decimal(str(por_sku["PLY-M"]["price"])) == Decimal("120")


def test_listado_y_busqueda_pos_tambien_traen_effective_price(client, db, org, branch_a, playera, auth_cajero_a):
    """list/search pasan `branch_statuses_cache` con TODAS las variantes."""
    p, v_s, v_m = playera
    pbs_m = (
        db.query(ProductBranchStatus)
        .filter(ProductBranchStatus.variant_id == v_m.id,
                ProductBranchStatus.branch_id == branch_a.id)
        .first()
    )
    pbs_m.price_override = Decimal("99")
    db.flush()
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}

    r = client.get("/api/products/", params={"search": "Playera"}, headers=h)
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["id"] == p.id)
    precios = {v["sku"]: Decimal(str(v["effective_price"])) for v in item["variants"]}
    assert precios == {"PLY-S": Decimal("100"), "PLY-M": Decimal("99")}

    r = client.get("/api/products/pos/search", params={"q": "Playera"}, headers=h)
    assert r.status_code == 200, r.text
    item = next(i for i in r.json() if i["id"] == p.id)
    precios = {v["sku"]: Decimal(str(v["effective_price"])) for v in item["variants"]}
    assert precios == {"PLY-S": Decimal("100"), "PLY-M": Decimal("99")}


def test_producto_de_una_variante_sin_modulo_variantes_no_cambia(client, db, org, branch_a, auth_cajero_a):
    """Neutralidad: una sola variante y sin override -> effective_price == price."""
    p, v = _make_product(db, org, "Refresco", "REF-1", 25, [(branch_a.id, True)])
    db.flush()
    r = client.get(f"/api/products/{p.id}", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert Decimal(str(data["price"])) == Decimal("25")
    assert Decimal(str(data["variants"][0]["effective_price"])) == Decimal("25")
