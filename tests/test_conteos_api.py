# tests/test_conteos_api.py
"""`/api/inventory/counts`: permisos, alta, escaneo, líneas, cierre y reporte."""
from decimal import Decimal

import pytest

from app.models.inventory import InventoryMovement, StockOnHand
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


def test_borrado_forzado_de_org_con_conteo(client, db, auth_superadmin):
    """El cascade de plataforma debe llevarse conteos y líneas (FKs a variantes/sucursales)."""
    from app.models.organization import Branch, BranchType
    from app.modules.conteos.models import InventoryCount, InventoryCountLine

    # Org aparte: la del superadmin no se puede borrar (su bitácora apunta a su usuario).
    otra = Organization(name="Org a borrar", status="ACTIVE")
    db.add(otra)
    db.flush()
    suc = Branch(name="Matriz", organization_id=otra.id, branch_type=BranchType.STORE, can_sell=True, is_active=True)
    db.add(suc)
    dep = Department(name="Playeras", organization_id=otra.id)
    db.add(dep)
    db.flush()
    p = Product(name="Playera", organization_id=otra.id, is_active=True, department_id=dep.id)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="X-M", organization_id=otra.id,
                       price=Decimal("100"), cost=Decimal("50"), size="M")
    db.add(v)
    db.flush()
    c = InventoryCount(branch_id=suc.id, department_id=dep.id, organization_id=otra.id)
    db.add(c)
    db.flush()
    db.add(InventoryCountLine(count_id=c.id, variant_id=v.id, qty_contada=Decimal("2"), organization_id=otra.id))
    db.commit()
    org_id = otra.id

    r = client.delete(f"/api/platform/organizations/{org_id}?force=true", headers=auth_superadmin)
    assert r.status_code in (200, 204), r.text
    db.expire_all()
    assert db.query(InventoryCount).filter_by(organization_id=org_id).count() == 0
    assert db.query(InventoryCountLine).filter_by(organization_id=org_id).count() == 0


# ── Cancelar conteo ──────────────────────────────────────────────────────────
def test_cancelar_conteo_abierto(client, db, org, branch_a, auth_admin, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    h = _h(auth_admin, org)
    client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "2017000000013"})
    movimientos = db.query(InventoryMovement).filter_by(organization_id=org.id).count()
    r = client.post(f"/api/inventory/counts/{cid}/cancel", headers=h)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["id"] == cid and c["status"] == "CANCELADO" and c["closed_at"] is not None
    # Se descarta lo contado: no se congela nada y la existencia no se toca.
    from app.modules.conteos.models import InventoryCount, InventoryCountLine
    db.expire_all()
    fila = db.query(InventoryCount).filter_by(id=cid).one()
    assert fila.status == "CANCELADO" and fila.resumen is None and fila.aplicado_at is None
    assert all(l.qty_sistema is None for l in db.query(InventoryCountLine).filter_by(count_id=cid))
    stock = db.query(StockOnHand).filter_by(variant_id=tienda["v"].id, branch_id=branch_a.id).one()
    assert stock.qty_on_hand == Decimal("3")
    assert db.query(InventoryMovement).filter_by(organization_id=org.id).count() == movimientos


def test_cancelar_conteo_cerrado_o_cancelado_es_409(client, org, branch_a, auth_admin, tienda):
    h = _h(auth_admin, org)
    cerrado = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    assert client.post(f"/api/inventory/counts/{cerrado}/close", headers=h).status_code == 200
    r = client.post(f"/api/inventory/counts/{cerrado}/cancel", headers=h)
    assert r.status_code == 409 and "cerrado o cancelado" in r.json()["detail"]
    # Y el CERRADO sigue cerrado con su reporte congelado.
    assert client.get(f"/api/inventory/counts/{cerrado}", headers=h).json()["status"] == "CERRADO"
    cancelado = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    assert client.post(f"/api/inventory/counts/{cancelado}/cancel", headers=h).status_code == 200
    assert client.post(f"/api/inventory/counts/{cancelado}/cancel", headers=h).status_code == 409
    # Un cancelado tampoco se puede cerrar.
    assert client.post(f"/api/inventory/counts/{cancelado}/close", headers=h).status_code == 409


def test_conteo_cancelado_no_se_edita(client, org, branch_a, auth_admin, tienda):
    h = _h(auth_admin, org)
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    lid = client.post(f"/api/inventory/counts/{cid}/scan", headers=h,
                      json={"code": "2017000000013"}).json()["linea"]["id"]
    assert client.post(f"/api/inventory/counts/{cid}/cancel", headers=h).status_code == 200
    assert client.post(f"/api/inventory/counts/{cid}/scan", headers=h,
                       json={"code": "2017000000013"}).status_code == 409
    assert client.post(f"/api/inventory/counts/{cid}/lines", headers=h,
                       json={"variant_id": tienda["v"].id, "qty": "1"}).status_code == 409
    assert client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h,
                        json={"qty_contada": "5"}).status_code == 409
    assert client.delete(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h).status_code == 409
    assert client.post(f"/api/inventory/counts/{cid}/lines/{lid}/ajustar", headers=h).status_code == 409
    r = client.post(f"/api/inventory/counts/{cid}/apply", headers=h, json={"variant_ids": [tienda["v"].id]})
    assert r.status_code == 409 and r.json()["detail"] == "Este conteo fue cancelado."
    # Las lecturas siguen: las líneas quedan como rastro.
    r = client.get(f"/api/inventory/counts/{cid}", headers=h)
    assert r.status_code == 200 and [l["qty_contada"] for l in r.json()["lineas"]] == ["1"]
    assert client.get(f"/api/inventory/counts/{cid}/report", headers=h).status_code == 200
    assert client.get(f"/api/inventory/counts/{cid}/lista", headers=h).status_code == 200


def test_cancelar_libera_sucursal_y_departamento(client, org, branch_a, auth_admin, tienda):
    h = _h(auth_admin, org)
    primero = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    assert _crear(client, auth_admin, org, branch_a, tienda["playeras"]).status_code == 409
    assert client.post(f"/api/inventory/counts/{primero}/cancel", headers=h).status_code == 200
    r = _crear(client, auth_admin, org, branch_a, tienda["playeras"])
    assert r.status_code == 201 and r.json()["id"] != primero and r.json()["status"] == "ABIERTO"


def test_cancelar_conserva_los_ajustes_hechos_en_piso(client, db, org, branch_a, auth_admin, tienda):
    """Lo que promete el diálogo: lo contado se descarta, pero un ajuste en piso ya es kardex real."""
    h = _h(auth_admin, org)
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    lid = client.post(f"/api/inventory/counts/{cid}/scan", headers=h,
                      json={"code": "2017000000013"}).json()["linea"]["id"]
    # Contó 1 y el sistema dice 3: el ajuste en piso deja la existencia en 1 (movimiento de -2).
    r = client.post(f"/api/inventory/counts/{cid}/lines/{lid}/ajustar", headers=h)
    assert r.status_code == 200, r.text
    mov_id = r.json()["movimiento_id"]
    antes = db.query(InventoryMovement).filter_by(organization_id=org.id).count()
    r = client.post(f"/api/inventory/counts/{cid}/cancel", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "CANCELADO"
    db.expire_all()
    stock = db.query(StockOnHand).filter_by(variant_id=tienda["v"].id, branch_id=branch_a.id).one()
    assert stock.qty_on_hand == Decimal("1")        # el ajuste se conserva, no se revierte
    mov = db.query(InventoryMovement).filter_by(id=mov_id).one()
    assert mov.reference == "Conteo" and mov.qty_change == Decimal("-2") and mov.qty_after == Decimal("1")
    assert db.query(InventoryMovement).filter_by(organization_id=org.id).count() == antes
    # La línea sigue siendo rastro, con su marca de ajustada.
    lineas = client.get(f"/api/inventory/counts/{cid}", headers=h).json()["lineas"]
    assert [(l["qty_contada"], l["ajustada"]) for l in lineas] == [("1", True)]


def test_cancelar_conteo_de_otra_org_es_404(client, db, org, branch_a, auth_admin, tienda):
    from app.models.organization import Branch, BranchType
    from app.modules.conteos.models import InventoryCount
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    suc = Branch(name="Matriz", organization_id=otra.id, branch_type=BranchType.STORE, can_sell=True, is_active=True)
    db.add(suc)
    db.flush()
    ajeno = InventoryCount(branch_id=suc.id, organization_id=otra.id)
    db.add(ajeno)
    db.commit()
    r = client.post(f"/api/inventory/counts/{ajeno.id}/cancel", headers=_h(auth_admin, org))
    assert r.status_code == 404
    assert client.post("/api/inventory/counts/999999/cancel", headers=_h(auth_admin, org)).status_code == 404
    db.expire_all()
    assert db.query(InventoryCount).filter_by(id=ajeno.id).one().status == "ABIERTO"


def test_cajero_no_puede_cancelar(client, org, branch_a, auth_admin, auth_cajero_a, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    r = client.post(f"/api/inventory/counts/{cid}/cancel", headers=_h(auth_cajero_a, org))
    assert r.status_code == 403
    assert client.get(f"/api/inventory/counts/{cid}", headers=_h(auth_admin, org)).json()["status"] == "ABIERTO"


def test_lista_incluye_el_cancelado_con_su_status(client, org, branch_a, auth_admin, tienda):
    h = _h(auth_admin, org)
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    assert client.post(f"/api/inventory/counts/{cid}/cancel", headers=h).status_code == 200
    filas = client.get("/api/inventory/counts/", headers=h).json()
    assert [(f["id"], f["status"]) for f in filas] == [(cid, "CANCELADO")]
    filtrado = client.get("/api/inventory/counts/?status=CANCELADO", headers=h).json()
    assert [f["id"] for f in filtrado] == [cid]
    assert client.get("/api/inventory/counts/?status=ABIERTO", headers=h).json() == []
