# tests/test_reports_umbral.py
"""Umbral único de "poca existencia" (SP6 vista del dueño, 2026-10).

`organization.umbral_poca_existencia` (3 si no está capturado) es EL criterio en
`/dashboard` (`low_stock`), `/command-center/stats` (`critical_stock`, `alerts`)
y `/inicio`. Antes `/dashboard` y `/command-center` marcaban ≤ 5 fijo.
"""
from decimal import Decimal

from datetime import datetime, timezone

from conftest import _make_product

from app.models.inventory import StockOnHand
from app.models.products import Product, ProductVariant


def _variante(db, org, branch, nombre, existencia):
    p = Product(name=nombre, organization_id=org.id, is_active=True)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=nombre, price=Decimal("100"), cost=Decimal("40"),
                       organization_id=org.id)
    db.add(v)
    db.flush()
    db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                       qty_on_hand=Decimal(str(existencia)), is_active=True))
    db.flush()
    return v


def _sembrar(db, org, branch):
    for n in (0, 2, 3, 4, 5, 9):
        _variante(db, org, branch, f"E{n}", n)
    db.commit()


def _nombres_low_stock(client, auth):
    # branch_id=0 = toda la org (el admin de conftest vive en el HQ, que no tiene existencias)
    r = client.get("/api/reports/dashboard?branch_id=0", headers=auth)
    assert r.status_code == 200, r.text
    return sorted(row["name"] for row in r.json()["low_stock"])


def test_dashboard_marca_tres_por_defecto(client, db, org, branch_a, auth_admin):
    _sembrar(db, org, branch_a)
    assert _nombres_low_stock(client, auth_admin) == ["E0", "E2", "E3"]


def test_dashboard_respeta_el_umbral_de_la_empresa(client, db, org, branch_a, auth_admin):
    _sembrar(db, org, branch_a)
    org.umbral_poca_existencia = 5
    db.commit()
    assert _nombres_low_stock(client, auth_admin) == ["E0", "E2", "E3", "E4", "E5"]


def test_umbral_cero_solo_agotados(client, db, org, branch_a, auth_admin):
    _sembrar(db, org, branch_a)
    org.umbral_poca_existencia = 0
    db.commit()
    assert _nombres_low_stock(client, auth_admin) == ["E0"]


def test_command_center_usa_el_mismo_umbral(client, db, org, branch_a, auth_admin):
    _sembrar(db, org, branch_a)
    r = client.get("/api/reports/command-center/stats", headers=auth_admin)
    assert r.status_code == 200, r.text
    d = r.json()
    por_sucursal = {b["id"]: b["critical_stock"] for b in d["branches"]}
    assert por_sucursal[branch_a.id] == 3
    assert len(d["alerts"]) == 3

    org.umbral_poca_existencia = 4
    db.commit()
    d = client.get("/api/reports/command-center/stats", headers=auth_admin).json()
    assert {b["id"]: b["critical_stock"] for b in d["branches"]}[branch_a.id] == 4
    assert len(d["alerts"]) == 4


def test_dashboard_respeta_la_sucursal_pedida_tambien_para_la_duena(client, db, org, branch_a, branch_b, auth_admin):
    _variante(db, org, branch_a, "EnA", 1)
    _variante(db, org, branch_b, "EnB", 1)
    borrada = _variante(db, org, branch_a, "Borrada", 0)
    borrada.deleted_at = datetime.now(timezone.utc)
    db.commit()
    solo_a = client.get(f"/api/reports/dashboard?branch_id={branch_a.id}", headers=auth_admin).json()["low_stock"]
    assert sorted(r["name"] for r in solo_a) == ["EnA"]
    todas = client.get("/api/reports/dashboard?branch_id=0", headers=auth_admin).json()["low_stock"]
    assert sorted(r["name"] for r in todas) == ["EnA", "EnB"]


def test_csv_lista_stock_bajo_con_el_umbral(client, db, org, branch_a, auth_admin):
    _sembrar(db, org, branch_a)
    org.umbral_poca_existencia = 4
    db.commit()
    r = client.get("/api/reports/export/csv?branch_id=0", headers=auth_admin)
    assert r.status_code == 200, r.text
    seccion = r.text.split("Alertas Stock Bajo")[1]
    assert "E4" in seccion and "E5" not in seccion and "E9" not in seccion


def test_catalog_kpis_y_branch_kpis_usan_el_umbral(client, db, org, branch_a, auth_admin):
    for n in (1, 3, 4):
        _make_product(db, org, f"K{n}", f"K-{n}", 100, [(branch_a.id, True)])
    db.commit()
    from app.models.inventory import StockOnHand as S
    for n in (1, 3, 4):
        v = db.query(ProductVariant).filter(ProductVariant.sku == f"K-{n}").one()
        db.query(S).filter(S.variant_id == v.id).update({"qty_on_hand": n})
    db.commit()

    k = client.get("/api/products/stats/catalog-kpis", headers=auth_admin).json()
    assert (k["threshold"], k["critical_stock"]) == (3, 2)
    b = client.get("/api/products/stats/branch-kpis?branch_id=0", headers=auth_admin).json()
    assert b["low_stock"] == 2
    org.umbral_poca_existencia = 4
    db.commit()
    assert client.get("/api/products/stats/catalog-kpis", headers=auth_admin).json()["critical_stock"] == 3
    assert client.get(f"/api/products/stats/branch-kpis?branch_id={branch_a.id}", headers=auth_admin).json()["low_stock"] == 3


def test_hq_inventory_filtra_stock_bajo_con_el_umbral(client, db, org, branch_a, auth_admin):
    for n in (1, 3, 4):
        _make_product(db, org, f"K{n}", f"K-{n}", 100, [(branch_a.id, True)])
    db.commit()
    for n in (1, 3, 4):
        v = db.query(ProductVariant).filter(ProductVariant.sku == f"K-{n}").one()
        db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).update({"qty_on_hand": n})
    db.commit()
    r = client.get("/api/products/hq-inventory?stock_status=low_stock", headers=auth_admin).json()
    assert sorted(p["name"] for p in r["items"]) == ["K1", "K3"]
    assert r["kpis"]["low_stock_count"] == 2
