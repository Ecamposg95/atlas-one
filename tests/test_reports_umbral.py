# tests/test_reports_umbral.py
"""Umbral único de "poca existencia" (SP6 vista del dueño, 2026-10).

`organization.umbral_poca_existencia` (3 si no está capturado) es EL criterio en
`/dashboard` (`low_stock`), `/command-center/stats` (`critical_stock`, `alerts`)
y `/inicio`. Antes `/dashboard` y `/command-center` marcaban ≤ 5 fijo.
"""
from decimal import Decimal

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
    r = client.get("/api/reports/dashboard", headers=auth)
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
