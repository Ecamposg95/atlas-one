"""Escanear el codigo de la talla M debe devolver la talla M, no la S.

`contains_eager` sobre `Product.variants` carga solo las filas que empataron
el WHERE, asi que hoy `variants[0]` PUEDE ser la correcta por accidente. Esta
prueba fija el contrato para que no dependa de ese efecto colateral: campos
aplanados de la variante empatada, `matched_variant_id` explicito y
`variants[]` completo para el selector del POS."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from conftest import _make_product


@pytest.fixture()
def playera(db, org, branch_a):
    p, v_s = _make_product(db, org, "Playera Lisa", "PLY-S", 100, [(branch_a.id, True)])
    v_s.barcode, v_s.color, v_s.size, v_s.variant_name = "7500000000001", "Rojo", "S", "Rojo / S"
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


def _buscar(client, org, auth, **params):
    r = client.get("/api/products/pos/search", params=params,
                   headers={**auth, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    return r.json()


def test_escanear_la_talla_m_devuelve_la_talla_m(client, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    res = _buscar(client, org, auth_cajero_a, q="7500000000002", exact="true")
    assert len(res) == 1
    hit = res[0]
    assert hit["id"] == p.id
    assert hit["matched_variant_id"] == v_m.id
    assert hit["sku"] == "PLY-M"
    assert Decimal(str(hit["price"])) == Decimal("120")
    assert Decimal(str(hit["stock_total"])) == Decimal("7")


def test_teclear_el_sku_de_la_s_devuelve_la_s(client, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    hit = _buscar(client, org, auth_cajero_a, q="ply-s", exact="true")[0]
    assert hit["matched_variant_id"] == v_s.id
    assert hit["sku"] == "PLY-S"


def test_variants_viene_completo_aunque_empate_una_sola(client, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    hit = _buscar(client, org, auth_cajero_a, q="7500000000002", exact="true")[0]
    assert {v["sku"] for v in hit["variants"]} == {"PLY-S", "PLY-M"}
    stocks = {v["sku"]: Decimal(str(v["stock_total"])) for v in hit["variants"]}
    assert stocks["PLY-S"] == Decimal("100") and stocks["PLY-M"] == Decimal("7")


def test_buscar_por_nombre_no_duplica_el_producto(client, org, playera, auth_cajero_a):
    res = _buscar(client, org, auth_cajero_a, q="Playera")
    assert [r["id"] for r in res].count(playera[0].id) == 1
