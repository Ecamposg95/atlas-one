"""Publicar en tienda web, galería de imágenes y sucursales del canal (Tarea 3)."""
import io
import itertools
from decimal import Decimal

import pytest

from app.core.security.channel_keys import MODULO_CANAL, invalidar_cache_canal
from app.models import Organization, Product, ProductVariant
from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch, BranchType
from app.modules.products.imagenes import ProductImage

_contador = itertools.count(1)


@pytest.fixture(autouse=True)
def _limpiar_cache():
    invalidar_cache_canal()
    yield
    invalidar_cache_canal()


@pytest.fixture(autouse=True)
def _subida_falsa(monkeypatch):
    """upload_image sin disco ni Cloudinary: devuelve una URL por llamada."""
    from app.utils import image_storage

    def _fake(content, *, public_id, folder, content_type="image/jpeg"):
        return f"https://cdn.test/{public_id}.jpg"

    monkeypatch.setattr(image_storage, "upload_image", _fake)


def _encender(db, org, activo=True):
    if db.query(Module).filter(Module.key == MODULO_CANAL).first() is None:
        db.add(Module(key=MODULO_CANAL, name="Tienda en línea"))
        db.flush()
    om = db.query(OrganizationModule).filter_by(
        organization_id=org.id, module_key=MODULO_CANAL).first()
    if om is None:
        om = OrganizationModule(organization_id=org.id, module_key=MODULO_CANAL, is_enabled=activo)
        db.add(om)
    om.is_enabled = activo
    db.flush()
    invalidar_cache_canal(org.id)
    return om


def _producto(db, org, nombre="Bolsa"):
    n = next(_contador)
    p = Product(name=f"{nombre} {n}", organization_id=org.id, is_active=True)
    db.add(p)
    db.flush()
    db.add(ProductVariant(product_id=p.id, sku=f"WP-{n}", price=Decimal("100"),
                          cost=Decimal("50"), organization_id=org.id))
    db.flush()
    return p


def _png(nombre="a.png"):
    return {"file": (nombre, io.BytesIO(b"\x89PNG fake"), "image/png")}


# ── Publicar ─────────────────────────────────────────────────────────────────
def test_publicar_por_ids(client, db, org, auth_admin):
    _encender(db, org)
    p1, p2 = _producto(db, org), _producto(db, org)
    r = client.post("/api/products/web-publish",
                    json={"ids": [p1.id], "published": True}, headers=auth_admin)
    assert r.status_code == 200, r.text
    assert r.json() == {"processed": 1}
    db.refresh(p1); db.refresh(p2)
    assert p1.web_published is True and p1.web_published_at is not None
    assert p2.web_published is False


def test_publicar_por_filtro(client, db, org, auth_admin):
    _encender(db, org)
    a = _producto(db, org, "Zapato")
    b = _producto(db, org, "Zapato")
    c = _producto(db, org, "Camisa")
    r = client.post("/api/products/web-publish",
                    json={"filtro": {"search": "Zapato"}, "published": True}, headers=auth_admin)
    assert r.status_code == 200, r.text
    assert r.json()["processed"] == 2
    for p in (a, b, c):
        db.refresh(p)
    assert a.web_published and b.web_published and not c.web_published


def test_filtro_solo_activos(client, db, org, auth_admin):
    _encender(db, org)
    a = _producto(db, org, "Gorra")
    b = _producto(db, org, "Gorra")
    b.is_active = False
    db.flush()
    r = client.post("/api/products/web-publish",
                    json={"filtro": {"search": "Gorra"}, "published": True}, headers=auth_admin)
    assert r.json()["processed"] == 1
    db.refresh(b)
    assert b.web_published is False


def test_despublicar(client, db, org, auth_admin):
    _encender(db, org)
    p = _producto(db, org)
    client.post("/api/products/web-publish", json={"ids": [p.id], "published": True}, headers=auth_admin)
    r = client.post("/api/products/web-publish", json={"ids": [p.id], "published": False}, headers=auth_admin)
    assert r.json() == {"processed": 1}
    db.refresh(p)
    assert p.web_published is False


def test_republicar_no_cambia_fecha(client, db, org, auth_admin):
    _encender(db, org)
    p = _producto(db, org)
    client.post("/api/products/web-publish", json={"ids": [p.id], "published": True}, headers=auth_admin)
    db.refresh(p)
    primera = p.web_published_at
    client.post("/api/products/web-publish", json={"ids": [p.id], "published": True}, headers=auth_admin)
    db.refresh(p)
    assert p.web_published_at == primera


def test_cajero_y_gerente_403(client, db, org, auth_cajero_a, auth_gerente_a):
    _encender(db, org)
    p = _producto(db, org)
    for h in (auth_cajero_a, auth_gerente_a):
        r = client.post("/api/products/web-publish", json={"ids": [p.id], "published": True}, headers=h)
        assert r.status_code == 403


def test_canal_apagado_404(client, db, org, auth_admin):
    p = _producto(db, org)
    r = client.post("/api/products/web-publish", json={"ids": [p.id], "published": True}, headers=auth_admin)
    assert r.status_code == 404


def test_ids_de_otra_org_no_se_tocan(client, db, org, auth_admin):
    _encender(db, org)
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajeno = _producto(db, otra)
    propio = _producto(db, org)
    r = client.post("/api/products/web-publish",
                    json={"ids": [ajeno.id, propio.id], "published": True}, headers=auth_admin)
    assert r.json() == {"processed": 1}
    db.refresh(ajeno)
    assert ajeno.web_published is False


def test_publicar_toca_updated_at(client, db, org, auth_admin):
    _encender(db, org)
    p = _producto(db, org)
    antes = p.updated_at
    client.post("/api/products/web-publish", json={"ids": [p.id], "published": True}, headers=auth_admin)
    db.refresh(p)
    assert p.updated_at is not None and (antes is None or p.updated_at.replace(tzinfo=None) >= antes.replace(tzinfo=None))


# ── Galería ──────────────────────────────────────────────────────────────────
def _subir(client, p, h, nombre="a.png", alt=None):
    data = {"alt": alt} if alt else None
    return client.post(f"/api/products/{p.id}/images", files=_png(nombre), data=data, headers=h)


def test_galeria_subir_dos_y_reordenar(client, db, org, auth_admin):
    p = _producto(db, org)
    r1 = _subir(client, p, auth_admin, alt="frente")
    r2 = _subir(client, p, auth_admin)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    i1, i2 = r1.json()["id"], r2.json()["id"]
    assert r1.json()["is_primary"] is True and r2.json()["is_primary"] is False
    db.refresh(p)
    url1 = r1.json()["url"]
    assert p.image_url == url1

    r = client.put(f"/api/products/{p.id}/images/order",
                   json={"ids": [i2, i1], "primary_id": i2}, headers=auth_admin)
    assert r.status_code == 200, r.text
    lista = client.get(f"/api/products/{p.id}/images", headers=auth_admin).json()
    assert [x["id"] for x in lista] == [i2, i1]
    assert lista[0]["is_primary"] is True and lista[1]["is_primary"] is False
    db.refresh(p)
    assert p.image_url == lista[0]["url"]


def test_borrar_primaria_promueve_siguiente(client, db, org, auth_admin):
    p = _producto(db, org)
    i1 = _subir(client, p, auth_admin).json()
    i2 = _subir(client, p, auth_admin).json()
    r = client.delete(f"/api/products/{p.id}/images/{i1['id']}", headers=auth_admin)
    assert r.status_code == 200, r.text
    lista = client.get(f"/api/products/{p.id}/images", headers=auth_admin).json()
    assert [x["id"] for x in lista] == [i2["id"]]
    assert lista[0]["is_primary"] is True
    db.refresh(p)
    assert p.image_url == i2["url"]
    # soft delete: la fila sigue
    fila = db.query(ProductImage).filter(ProductImage.id == i1["id"]).first()
    assert fila is not None and fila.deleted_at is not None


def test_borrar_todas_deja_image_url_nulo(client, db, org, auth_admin):
    p = _producto(db, org)
    i1 = _subir(client, p, auth_admin).json()
    client.delete(f"/api/products/{p.id}/images/{i1['id']}", headers=auth_admin)
    db.refresh(p)
    assert p.image_url is None


def test_image_legacy_crea_primaria(client, db, org, auth_admin):
    p = _producto(db, org)
    r = client.post(f"/api/products/{p.id}/image", files=_png(), headers=auth_admin)
    assert r.status_code == 200, r.text
    lista = client.get(f"/api/products/{p.id}/images", headers=auth_admin).json()
    assert len(lista) == 1 and lista[0]["is_primary"] is True
    db.refresh(p)
    assert p.image_url == lista[0]["url"]
    # subir otra vez reemplaza la primaria, sigue habiendo una sola
    client.post(f"/api/products/{p.id}/image", files=_png(), headers=auth_admin)
    assert len(client.get(f"/api/products/{p.id}/images", headers=auth_admin).json()) == 1


def test_galeria_toca_producto_y_aisla_orgs(client, db, org, auth_admin):
    otra = Organization(name="Otra2", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajeno = _producto(db, otra)
    assert _subir(client, ajeno, auth_admin).status_code == 404
    assert client.get(f"/api/products/{ajeno.id}/images", headers=auth_admin).status_code == 404


def test_galeria_rol_sin_permiso_403(client, db, org, auth_vendedor_sin_sucursal):
    # Mismos roles que `/{id}/image` (el cajero sí puede; un vendedor no).
    p = _producto(db, org)
    assert _subir(client, p, auth_vendedor_sin_sucursal).status_code == 403


def test_order_con_ids_ajenos_422(client, db, org, auth_admin):
    p = _producto(db, org)
    q = _producto(db, org)
    i1 = _subir(client, p, auth_admin).json()
    j = _subir(client, q, auth_admin).json()
    r = client.put(f"/api/products/{p.id}/images/order",
                   json={"ids": [i1["id"], j["id"]], "primary_id": i1["id"]}, headers=auth_admin)
    assert r.status_code == 422


# ── Config del canal ─────────────────────────────────────────────────────────
def test_config_apagado_devuelve_activo_false(client, db, org, auth_admin):
    r = client.get("/api/canal/config", headers=auth_admin)
    assert r.status_code == 200
    assert r.json()["activo"] is False


def test_config_put_apagado_404(client, db, org, auth_admin):
    r = client.put("/api/canal/config", json={"sucursales_web": None}, headers=auth_admin)
    assert r.status_code == 404


def test_config_get_lista_sucursales(client, db, org, auth_admin, branch_a, hq_branch):
    _encender(db, org)
    r = client.get("/api/canal/config", headers=auth_admin).json()
    assert r["activo"] is True and r["sucursales_web"] is None
    ids = {s["id"]: s for s in r["sucursales"]}
    assert ids[branch_a.id]["can_sell"] is True and ids[hq_branch.id]["can_sell"] is False
    assert set(ids[branch_a.id]) >= {"id", "name", "can_sell"}


def test_config_put_guarda_y_null_vuelve_a_todas(client, db, org, auth_admin, branch_a, monkeypatch):
    _encender(db, org)
    from app.modules.canal import config_router
    llamadas = []
    monkeypatch.setattr(config_router, "al_cambiar_sucursales", lambda d, o: llamadas.append(o))
    r = client.put("/api/canal/config", json={"sucursales_web": [branch_a.id]}, headers=auth_admin)
    assert r.status_code == 200, r.text
    assert client.get("/api/canal/config", headers=auth_admin).json()["sucursales_web"] == [branch_a.id]
    r = client.put("/api/canal/config", json={"sucursales_web": None}, headers=auth_admin)
    assert r.status_code == 200
    assert client.get("/api/canal/config", headers=auth_admin).json()["sucursales_web"] is None
    assert llamadas == [org.id, org.id]


def test_config_put_sucursal_ajena_422(client, db, org, auth_admin):
    _encender(db, org)
    otra = Organization(name="Otra3", status="ACTIVE")
    db.add(otra)
    db.flush()
    b = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True,
               organization_id=otra.id)
    db.add(b)
    db.flush()
    r = client.put("/api/canal/config", json={"sucursales_web": [b.id]}, headers=auth_admin)
    assert r.status_code == 422


def test_config_put_solo_admin(client, db, org, auth_cajero_a, auth_gerente_a):
    _encender(db, org)
    for h in (auth_cajero_a, auth_gerente_a):
        assert client.put("/api/canal/config", json={"sucursales_web": None}, headers=h).status_code == 403
