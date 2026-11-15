"""API de catálogo del canal «Tienda en línea» (/api/channel/v1)."""
import itertools
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event

from conftest import TEST_ENGINE, _auth_header, _make_user
from app.core.security import channel_keys
from app.core.security.channel_keys import MODULO_CANAL, invalidar_cache_canal
from app.models import Organization, Product, ProductVariant
from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch, BranchType
from app.models.platform import ApiKey
from app.models.products import ProductBranchStatus
from app.models.users import Role
from app.modules.canal import router as canal_router
from app.modules.canal.cursor import codificar_cursor, decodificar_cursor
from app.modules.canal.models import ChannelAvailability
from app.modules.platform.api_keys import generate_api_key
from app.modules.products.imagenes import ProductImage
from app.modules.products.models import Brand, Department
from app.modules.products.services.web import publicar_en_web
from app.services import canal_disponibilidad as cd

_n = itertools.count(1)
PROHIBIDAS = re.compile(r"price|cost|tax|iva|supplier|proveedor|qty|stock|barcode", re.I)
BASE = "/api/channel/v1"


@pytest.fixture(autouse=True)
def _limpiar():
    invalidar_cache_canal()
    channel_keys.reiniciar_rate_limit()
    cd.registrar_listener()
    yield
    invalidar_cache_canal()
    channel_keys.reiniciar_rate_limit()


def _encender(db, org, sucursales_web=None):
    if db.query(Module).filter(Module.key == MODULO_CANAL).first() is None:
        db.add(Module(key=MODULO_CANAL, name="Tienda en línea"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key=MODULO_CANAL,
                              is_enabled=True, config_json={"sucursales_web": sucursales_web}))
    db.flush()
    invalidar_cache_canal(org.id)


def _llave(db, org):
    full, prefix, hashed = generate_api_key()
    db.add(ApiKey(organization_id=org.id, name="t", prefix=prefix, hashed_key=hashed,
                  scopes=json.dumps(["catalog:read"])))
    db.flush()
    return {"Authorization": f"Bearer {full}"}


@pytest.fixture()
def h(db, org, branch_a):
    _encender(db, org, [branch_a.id])
    return _llave(db, org)


def _producto(db, org, branch, qty=3, publicar=True, nombre=None, **kw):
    n = next(_n)
    p = Product(name=nombre or f"Bolsa {n}", organization_id=org.id, is_active=True,
                approval_status="APPROVED", **kw)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=f"API-{n}", price=Decimal("100"),
                       cost=Decimal("50"), organization_id=org.id, color="Negro", size="M")
    db.add(v)
    db.flush()
    db.add(ProductBranchStatus(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                       qty_on_hand=Decimal(str(qty)), is_active=True))
    db.flush()
    if publicar:
        publicar_en_web(db, org.id, [p.id], True)
        db.expire_all()
    return p, v


def _claves(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _claves(v)
    elif isinstance(o, list):
        for x in o:
            yield from _claves(x)


# ── Cursor ───────────────────────────────────────────────────────────────────
def test_cursor_ida_y_vuelta():
    t = datetime(2026, 11, 14, 1, 2, 3, 456, tzinfo=timezone.utc)
    assert decodificar_cursor(codificar_cursor(t, "abc")) == (t, "abc")


# ── Lista blanca ─────────────────────────────────────────────────────────────
def test_lista_blanca(client, db, org, branch_a, h):
    marca = Brand(name="Gucci", organization_id=org.id, is_premium=True)
    dep = Department(name="Bolsas", organization_id=org.id)
    db.add_all([marca, dep])
    db.flush()
    p, v = _producto(db, org, branch_a, brand_id=marca.id, department_id=dep.id, gender="MUJER")
    db.add(ProductImage(organization_id=org.id, product_id=p.id, url="http://x/y.jpg",
                        position=0, is_primary=True))
    db.flush()
    cd.recalcular_disponibilidad(db, org.id)
    since = "?updated_since=2000-01-01T00:00:00Z"
    for ruta in ("/brands", "/departments", "/products", f"/products/{p.id}", "/availability"):
        r = client.get(BASE + ruta + since if "{" not in ruta and "products/" not in ruta else BASE + ruta, headers=h)
        assert r.status_code == 200, (ruta, r.text)
        malas = [k for k in _claves(r.json()) if PROHIBIDAS.search(k)]
        assert not malas, (ruta, malas)
    item = client.get(f"{BASE}/products/{p.id}", headers=h).json()
    assert item["images"][0]["is_primary"] is True and item["available"] is True
    assert item["variants"][0] == {"id": v.id, "sku": v.sku, "color": "Negro", "size": "M",
                                   "available": True}
    assert item["name"] == p.name and item["deleted"] is False


# ── Aislamiento ──────────────────────────────────────────────────────────────
def test_dos_orgs(client, db, org, branch_a, h):
    p, _ = _producto(db, org, branch_a)
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    _encender(db, otra)
    hb = _llave(db, otra)
    assert client.get(f"{BASE}/products", headers=hb).json()["items"] == []
    assert client.get(f"{BASE}/products/{p.id}", headers=hb).status_code == 404
    assert [i["id"] for i in client.get(f"{BASE}/products", headers=h).json()["items"]] == [p.id]
    assert client.get(f"{BASE}/availability", headers=hb).json()["items"] == []


def test_sin_llave_401(client):
    assert client.get(f"{BASE}/products").status_code == 401


# ── Altas y bajas ────────────────────────────────────────────────────────────
def test_solo_publicados_en_carga_inicial(client, db, org, branch_a, h):
    pub, _ = _producto(db, org, branch_a)
    _producto(db, org, branch_a, publicar=False)
    baja, _ = _producto(db, org, branch_a)
    publicar_en_web(db, org.id, [baja.id], False)
    db.expire_all()
    items = client.get(f"{BASE}/products", headers=h).json()["items"]
    assert [i["id"] for i in items] == [pub.id]


def test_despublicar_da_baja(client, db, org, branch_a, h):
    p, _ = _producto(db, org, branch_a)
    nunca, _ = _producto(db, org, branch_a, publicar=False)
    st = client.get(f"{BASE}/products", headers=h).json()["server_time"]
    publicar_en_web(db, org.id, [p.id], False)
    db.expire_all()
    r = client.get(f"{BASE}/products", params={"updated_since": st}, headers=h).json()
    assert len(r["items"]) == 1
    assert set(r["items"][0]) == {"id", "updated_at", "deleted"}
    assert r["items"][0]["id"] == p.id and r["items"][0]["deleted"] is True
    assert nunca.id not in [i["id"] for i in r["items"]]
    assert client.get(f"{BASE}/products/{nunca.id}", headers=h).status_code == 404
    assert client.get(f"{BASE}/products/{p.id}", headers=h).json()["deleted"] is True


def test_republicar_tras_baja(client, db, org, branch_a, h):
    p, _ = _producto(db, org, branch_a)
    publicar_en_web(db, org.id, [p.id], False)
    db.expire_all()
    p = db.get(Product, p.id)
    p.is_active = False
    db.flush()
    st = client.get(f"{BASE}/products", headers=h).json()["server_time"]
    p.is_active = True
    db.flush()
    publicar_en_web(db, org.id, [p.id], True)
    db.expire_all()
    it = client.get(f"{BASE}/products", params={"updated_since": st}, headers=h).json()["items"]
    assert len(it) == 1 and it[0]["deleted"] is False and it[0]["name"] == p.name


def test_inactivo_borrado_y_no_aprobado_son_baja(client, db, org, branch_a, h):
    a, _ = _producto(db, org, branch_a)
    b, _ = _producto(db, org, branch_a)
    c, _ = _producto(db, org, branch_a)
    since = "2000-01-01T00:00:00Z"
    db.get(Product, a.id).is_active = False
    db.get(Product, b.id).deleted_at = datetime.now(timezone.utc)
    db.get(Product, c.id).approval_status = "PENDING"
    db.flush()
    items = client.get(f"{BASE}/products", params={"updated_since": since}, headers=h).json()["items"]
    assert len(items) == 3 and all(i["deleted"] and set(i) == {"id", "updated_at", "deleted"} for i in items)
    assert client.get(f"{BASE}/products", headers=h).json()["items"] == []


def test_baja_por_ruta_masiva_mueve_updated_at(client, db, org, branch_a, h, auth_admin_a):
    """batch-action usa query.update: ¿onupdate de AuditMixin dispara?"""
    p, _ = _producto(db, org, branch_a)
    antes = db.get(Product, p.id).updated_at
    st = client.get(f"{BASE}/products", headers=h).json()["server_time"]
    r = client.post("/api/products/batch-action", headers=auth_admin_a,
                    json={"ids": [p.id], "action": "deactivate"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Product, p.id).updated_at > antes
    it = client.get(f"{BASE}/products", params={"updated_since": st}, headers=h).json()["items"]
    assert [i["id"] for i in it] == [p.id] and it[0]["deleted"] is True


# ── Paginación ───────────────────────────────────────────────────────────────
def test_cursor_estable_con_updated_at_iguales(client, db, org, branch_a, h):
    ids = []
    for _i in range(250):
        p = Product(name=f"P{_i}", organization_id=org.id, is_active=True,
                    approval_status="APPROVED", web_published=True)
        db.add(p)
        ids.append(p)
    db.flush()
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for p in ids:
        p.web_published_at = t
        p.updated_at = t
    db.flush()
    vistos, cursor, paginas = [], None, 0
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = client.get(f"{BASE}/products", params=params, headers=h).json()
        paginas += 1
        vistos += [i["id"] for i in r["items"]]
        cursor = r["next_cursor"]
        if cursor is None:
            break
    assert paginas == 3 and len(vistos) == 250 == len(set(vistos))


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_fuera_de_rango(client, h, limit):
    assert client.get(f"{BASE}/products", params={"limit": limit}, headers=h).status_code == 422


def test_cursor_basura(client, h):
    for ruta in ("/products", "/brands", "/availability"):
        assert client.get(BASE + ruta, params={"cursor": "%%%basura"}, headers=h).status_code == 400
    assert client.get(f"{BASE}/products", params={"cursor": "e30"}, headers=h).status_code == 400


# ── Disponibilidad ───────────────────────────────────────────────────────────
def test_availability_desde(client, db, org, branch_a, cajero_a, h):
    p, v = _producto(db, org, branch_a, qty=1)
    cd.recalcular_disponibilidad(db, org.id)
    r = client.get(f"{BASE}/availability", headers=h).json()
    assert [(i["variant_id"], i["available"]) for i in r["items"]] == [(v.id, True)]
    st = r["server_time"]
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("0"), status="OPEN"))
    db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    db.flush()
    s = client.post("/api/sales/", json={
        "doc_type": "ORDER", "items": [{"sku": v.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100"}],
    }, headers={**_auth_header(cajero_a), "X-Organization-ID": str(org.id)})
    assert s.status_code in (200, 201), s.text
    r = client.get(f"{BASE}/availability", params={"updated_since": st}, headers=h).json()
    assert [(i["variant_id"], i["available"], i["product_id"]) for i in r["items"]] == [(v.id, False, p.id)]
    prod = client.get(f"{BASE}/products/{p.id}", headers=h).json()
    assert prod["available"] is False and prod["variants"][0]["available"] is False


def test_disponible_sin_fila_usa_calculo_en_vivo(client, db, org, branch_a, h):
    # Existencia insertada por SQL crudo: el listener no la ve, no hay fila.
    p, v = _producto(db, org, branch_a, qty=0)
    db.execute(StockOnHand.__table__.update().where(StockOnHand.variant_id == v.id)
               .values(qty_on_hand=5))
    assert db.query(ChannelAvailability).count() == 0
    prod = client.get(f"{BASE}/products/{p.id}", headers=h).json()
    assert prod["available"] is True


# ── Marcas y departamentos ───────────────────────────────────────────────────
def test_marcas_y_departamentos(client, db, org, h):
    raiz = Department(name="Ropa", organization_id=org.id)
    db.add(raiz)
    db.flush()
    hijo = Department(name="Playeras", organization_id=org.id, parent_id=raiz.id)
    premium = Brand(name="Gucci", organization_id=org.id, is_premium=True, logo_url="http://l")
    muerta = Brand(name="Vieja", organization_id=org.id)
    db.add_all([hijo, premium, muerta])
    db.flush()
    muerta.deleted_at = datetime.now(timezone.utc)
    db.flush()
    deps = {d["id"]: d for d in client.get(f"{BASE}/departments", headers=h).json()["items"]}
    assert deps[hijo.id]["parent_id"] == raiz.id and deps[raiz.id]["parent_id"] is None
    marcas = client.get(f"{BASE}/brands", headers=h).json()["items"]
    assert [m["id"] for m in marcas] == [premium.id] and marcas[0]["is_premium"] is True
    con = {m["id"]: m for m in client.get(f"{BASE}/brands", params={"updated_since": "2000-01-01T00:00:00Z"},
                                          headers=h).json()["items"]}
    assert set(con[muerta.id]) == {"id", "updated_at", "deleted"} and con[muerta.id]["deleted"] is True
    assert con[premium.id]["deleted"] is False


# ── server_time ──────────────────────────────────────────────────────────────
def test_server_time_antes_de_consultar(client, db, org, branch_a, h, monkeypatch):
    _producto(db, org, branch_a)
    eventos = []
    real = canal_router._ahora

    def espia():
        eventos.append("tiempo")
        return real()

    monkeypatch.setattr(canal_router, "_ahora", espia)

    def _sql(conn, cursor, statement, *a):
        if "FROM products" in statement:
            eventos.append("consulta")

    event.listen(TEST_ENGINE, "before_cursor_execute", _sql)
    try:
        assert client.get(f"{BASE}/products", headers=h).status_code == 200
    finally:
        event.remove(TEST_ENGINE, "before_cursor_execute", _sql)
    assert eventos[0] == "tiempo" and "consulta" in eventos
