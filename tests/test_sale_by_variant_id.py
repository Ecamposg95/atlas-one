"""Vender la talla M debe descontar la talla M aunque el SKU del renglon sea
otro. Hoy `SaleItemCreate` no declara `variant_id` y Pydantic v2 lo descarta,
asi que el checkout resolvia siempre por SKU."""
from decimal import Decimal

from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from app.models.sales import SalesLineItem
from conftest import _make_product
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _playera(db, org, branch):
    _habilitar_pos(db, org)
    p, v_s = _make_product(db, org, "Playera", "PLY-S", 100, [(branch.id, True)])
    v_s.variant_name = "Rojo / S"
    v_m = ProductVariant(product_id=p.id, sku="PLY-M", price=Decimal("120"), cost=Decimal("60"),
                         color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id)
    db.add(v_m); db.flush()
    db.add(ProductBranchStatus(variant_id=v_m.id, branch_id=branch.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v_m.id, branch_id=branch.id, organization_id=org.id,
                       qty_on_hand=Decimal("7"), is_active=True))
    db.commit()
    return p, v_s, v_m


def test_variant_id_manda_sobre_el_sku(client, db, org, branch_a, cajero_a, auth_cajero_a):
    p, v_s, v_m = _playera(db, org, branch_a)
    _abrir_caja(db, org, branch_a, cajero_a)
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "PLY-S", "variant_id": v_m.id, "quantity": 2}],
        "payments": [{"method": "CARD", "amount": "240.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code in (200, 201), r.text

    stock_m = db.query(StockOnHand).filter(StockOnHand.variant_id == v_m.id, StockOnHand.branch_id == branch_a.id).one()
    stock_s = db.query(StockOnHand).filter(StockOnHand.variant_id == v_s.id, StockOnHand.branch_id == branch_a.id).one()
    assert stock_m.qty_on_hand == Decimal("5")
    assert stock_s.qty_on_hand == Decimal("100")

    linea = db.query(SalesLineItem).filter(SalesLineItem.variant_id == v_m.id).one()
    assert linea.description == "Playera (Rojo / M)"


def test_variant_id_de_otra_org_es_404(client, db, org, branch_a, cajero_a, auth_cajero_a):
    from app.models.organization import Organization
    otra = Organization(name="Otra", status="ACTIVE"); db.add(otra); db.flush()
    p_ajeno, v_ajeno = _make_product(db, otra, "Ajena", "AJ-1", 10)
    _playera(db, org, branch_a)
    _abrir_caja(db, org, branch_a, cajero_a)
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "AJ-1", "variant_id": v_ajeno.id, "quantity": 1}],
        "payments": [{"method": "CARD", "amount": "10.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 404
