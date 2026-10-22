# tests/test_conteos_api.py
"""`/api/inventory/counts`: permisos, alta, escaneo, líneas, cierre y reporte."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.organization import Organization
from app.models.products import Department, Product, ProductVariant


def _habilitar(db, org, key):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key))
        db.flush()
    if db.query(OrganizationModule).filter_by(organization_id=org.id, module_key=key).first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def tienda(db, org, branch_a):
    _habilitar(db, org, "inventory")
    playeras = Department(name="Playeras", organization_id=org.id)
    tenis = Department(name="Tenis", organization_id=org.id)
    db.add_all([playeras, tenis])
    db.flush()
    p = Product(name="Playera", organization_id=org.id, is_active=True, department_id=playeras.id)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="PLAY-M", barcode="2017000000013",
                       organization_id=org.id, price=Decimal("100"), cost=Decimal("50"), size="M")
    db.add(v)
    db.flush()
    db.add(StockOnHand(variant_id=v.id, branch_id=branch_a.id, organization_id=org.id,
                       qty_on_hand=Decimal("3"), is_active=True))
    db.commit()
    return {"playeras": playeras, "tenis": tenis, "v": v}


def _crear(client, auth, org, branch, depto=None, notes=None):
    return client.post("/api/inventory/counts/", headers=_h(auth, org), json={
        "branch_id": branch.id, "department_id": depto.id if depto else None, "notes": notes,
    })


def test_crear_lista_y_ver(client, db, org, branch_a, auth_admin, tienda):
    r = _crear(client, auth_admin, org, branch_a, tienda["playeras"], "pared izquierda")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["status"] == "ABIERTO" and c["department_name"] == "Playeras"
    assert c["avance"] == {"esperadas_variantes": 1, "esperadas_piezas": "3",
                           "contadas_variantes": 0, "contadas_piezas": "0", "desconocidos": 0}
    r = client.get("/api/inventory/counts/", headers=_h(auth_admin, org))
    assert [x["id"] for x in r.json()] == [c["id"]]
    r = client.get(f"/api/inventory/counts/{c['id']}", headers=_h(auth_admin, org))
    assert r.status_code == 200 and r.json()["lineas"] == []


def test_crear_duplicado_abierto_es_409(client, org, branch_a, auth_admin, tienda):
    assert _crear(client, auth_admin, org, branch_a, tienda["playeras"]).status_code == 201
    assert _crear(client, auth_admin, org, branch_a, tienda["playeras"]).status_code == 409


def test_crear_dos_departamentos_distintos_ok(client, org, branch_a, auth_admin, tienda):
    assert _crear(client, auth_admin, org, branch_a, tienda["playeras"]).status_code == 201
    assert _crear(client, auth_admin, org, branch_a, tienda["tenis"]).status_code == 201
    assert _crear(client, auth_admin, org, branch_a, None).status_code == 201


def test_sucursal_o_departamento_ajenos_son_404(client, db, org, branch_a, auth_admin, tienda):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajeno = Department(name="Ajeno", organization_id=otra.id)
    db.add(ajeno)
    db.commit()
    assert _crear(client, auth_admin, org, branch_a, ajeno).status_code == 404
    r = client.post("/api/inventory/counts/", headers=_h(auth_admin, org),
                    json={"branch_id": 999999})
    assert r.status_code == 404


def test_cajero_recibe_403(client, org, branch_a, auth_cajero_a, tienda):
    r = _crear(client, auth_cajero_a, org, branch_a, tienda["playeras"])
    assert r.status_code == 403
    r = client.get("/api/inventory/counts/", headers=_h(auth_cajero_a, org))
    assert r.status_code == 403


def test_escanear_lineas_cerrar_y_reporte(client, org, branch_a, auth_admin, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    h = _h(auth_admin, org)
    r = client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "2017000000013"})
    assert r.status_code == 200 and r.json()["resultado"] == "contado"
    assert r.json()["producto"]["sku"] == "PLAY-M" and r.json()["qty_sistema"] == "3"
    r = client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "nada"})
    assert r.json()["resultado"] == "desconocido"
    lid = r.json()["linea"]["id"]
    r = client.post(f"/api/inventory/counts/{cid}/lines", headers=h,
                    json={"variant_id": tienda["v"].id, "qty": "1"})
    assert r.status_code == 200 and r.json()["qty_contada"] == "2"
    vid_linea = r.json()["id"]
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{vid_linea}", headers=h,
                     json={"qty_contada": "1"})
    assert r.status_code == 200 and r.json()["qty_contada"] == "1"
    r = client.delete(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h)
    assert r.status_code == 204
    r = client.get(f"/api/inventory/counts/{cid}/report", headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "ABIERTO"
    assert r.json()["faltantes"][0]["diferencia"] == "-2"
    r = client.post(f"/api/inventory/counts/{cid}/close", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "CERRADO"
    assert r.json()["lineas"][0]["qty_sistema"] == "3"
    assert client.post(f"/api/inventory/counts/{cid}/close", headers=h).status_code == 409
    assert client.post(f"/api/inventory/counts/{cid}/scan", headers=h,
                       json={"code": "2017000000013"}).status_code == 409
    r = client.get(f"/api/inventory/counts/{cid}/report", headers=h)
    assert r.json()["estado"] == "CERRADO" and r.json()["totales"]["desconocidos"] == 0


def test_patch_negativo_es_422(client, org, branch_a, auth_admin, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    h = _h(auth_admin, org)
    lid = client.post(f"/api/inventory/counts/{cid}/scan", headers=h,
                      json={"code": "2017000000013"}).json()["linea"]["id"]
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={"qty_contada": "-1"})
    assert r.status_code == 422
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={"qty_contada": "0"})
    assert r.status_code == 200 and r.json() is None


def test_conteo_de_otra_org_es_404(client, db, org, branch_a, auth_admin, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.commit()
    r = client.get(f"/api/inventory/counts/{cid}", headers={**auth_admin, "X-Organization-ID": str(otra.id)})
    assert r.status_code in (403, 404)
    assert client.get("/api/inventory/counts/999999", headers=_h(auth_admin, org)).status_code == 404
