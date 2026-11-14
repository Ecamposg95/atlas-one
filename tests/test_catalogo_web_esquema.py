"""Esquema del catálogo web (canal tienda_en_linea): campos nuevos, galería,
departamento padre, módulo en catálogo sin presets."""
import time
from decimal import Decimal

from conftest import _make_product
from app.models import Department, Brand, Product
from app.modules.products.imagenes import ProductImage
from app.models.modules import IndustryPreset, Module
from app.models.organization import Organization
from app.modules.products.imagenes import backfill_imagenes
from app.services.capabilities_service import seed_global_modules


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


CLAVES_PREVIAS = {
    'approval_status', 'barcode', 'branch_statuses', 'brand_id', 'brand_name', 'cost',
    'department', 'department_name', 'description', 'gender', 'global_stock', 'has_iva',
    'id', 'image_url', 'is_active', 'main_packaging_name', 'main_packaging_price',
    'main_packaging_units', 'matched_variant_id', 'material', 'model', 'name',
    'packaging_units', 'price', 'prices', 'sale_name', 'sku', 'stock_levels',
    'stock_total', 'tax_rate', 'unit', 'variants',
}


def test_defaults_no_cambian_listado(client, db, org, branch_a, auth_admin):
    _make_product(db, org, "Camisa", "CAM-1", 100, [(branch_a.id, True)])
    r = client.get("/api/products/", headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
    assert items
    for it in items:
        assert set(it) == CLAVES_PREVIAS | {"web_published"}
        assert it["web_published"] is False


def test_backfill_imagen_primaria_idempotente(db, org):
    p, _ = _make_product(db, org, "Con foto", "FOTO-1", 10)
    p.image_url = "https://cdn.example/a.jpg"
    _make_product(db, org, "Sin foto", "FOTO-2", 10)
    db.flush()
    assert backfill_imagenes(db) == 1
    imgs = db.query(ProductImage).filter(ProductImage.product_id == p.id).all()
    assert len(imgs) == 1
    assert imgs[0].is_primary is True and imgs[0].position == 0
    assert imgs[0].url == p.image_url and imgs[0].organization_id == org.id
    assert backfill_imagenes(db) == 0


def _crear(client, org, auth, nombre, parent_id=None):
    body = {"name": nombre}
    if parent_id:
        body["parent_id"] = parent_id
    return client.post("/api/departments/", json=body, headers=_h(auth, org))


def test_parent_id_dos_niveles(client, org, auth_admin):
    ropa = _crear(client, org, auth_admin, "Ropa")
    assert ropa.status_code == 200 and ropa.json()["parent_id"] is None
    camisas = _crear(client, org, auth_admin, "Camisas", ropa.json()["id"])
    assert camisas.status_code == 200, camisas.text
    assert camisas.json()["parent_id"] == ropa.json()["id"]
    r = _crear(client, org, auth_admin, "Manga larga", camisas.json()["id"])
    assert r.status_code == 422


def test_parent_id_otra_org(client, db, org, auth_admin):
    otra = Organization(name="Otra org")
    db.add(otra)
    db.flush()
    ajeno = Department(name="Ajeno", organization_id=otra.id)
    db.add(ajeno)
    db.flush()
    r = _crear(client, org, auth_admin, "Hijo", ajeno.id)
    assert r.status_code == 422


def test_parent_id_ciclo(client, org, auth_admin):
    a = _crear(client, org, auth_admin, "A").json()
    b = _crear(client, org, auth_admin, "B", a["id"]).json()
    # A bajo B (B es hijo de A): ciclo.
    r = client.put(f"/api/departments/{a['id']}", json={"parent_id": b["id"]}, headers=_h(auth_admin, org))
    assert r.status_code == 422
    # A bajo si mismo.
    r = client.put(f"/api/departments/{a['id']}", json={"parent_id": a["id"]}, headers=_h(auth_admin, org))
    assert r.status_code == 422
    # Un departamento con hijos no puede volverse hijo.
    c = _crear(client, org, auth_admin, "C").json()
    r = client.put(f"/api/departments/{a['id']}", json={"parent_id": c["id"]}, headers=_h(auth_admin, org))
    assert r.status_code == 422


def test_marca_premium(client, db, org, auth_admin):
    b = Brand(name="Gucci", organization_id=org.id)
    db.add(b)
    db.commit()
    r = client.put(f"/api/brands/{b.id}", json={"name": "Gucci", "is_premium": True}, headers=_h(auth_admin, org))
    assert r.status_code == 200 and r.json()["is_premium"] is True
    r = client.get("/api/brands/", headers=_h(auth_admin, org))
    assert [x["is_premium"] for x in r.json() if x["id"] == b.id] == [True]
    # PUT sin el campo no lo apaga.
    r = client.put(f"/api/brands/{b.id}", json={"name": "Gucci"}, headers=_h(auth_admin, org))
    assert r.json()["is_premium"] is True


def test_editar_variante_toca_producto(client, db, org, branch_a, auth_admin):
    p, v = _make_product(db, org, "Tenis", "TEN-1", 100, [(branch_a.id, True)])
    db.commit()
    antes = db.query(Product).get(p.id).updated_at
    time.sleep(0.01)
    r = client.put(f"/api/products/variants/{v.id}", json={"price": "150"}, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    despues = db.query(Product).get(p.id).updated_at
    assert despues > antes


def test_modulo_en_catalogo_sin_presets(db):
    seed_global_modules(db)
    m = db.query(Module).filter(Module.key == "tienda_en_linea").first()
    assert m is not None and m.name == "Tienda en línea"
    for preset in db.query(IndustryPreset).all():
        assert "tienda_en_linea" not in (preset.modules or [])


def test_borrar_padre_deja_hijos_en_raiz(client, db, org, auth_admin):
    ropa = _crear(client, org, auth_admin, "Ropa").json()
    camisas = _crear(client, org, auth_admin, "Camisas", ropa["id"]).json()
    otra = Organization(name="Otra org 2")
    db.add(otra)
    db.flush()
    ajeno = Department(name="Ajeno hijo", organization_id=otra.id, parent_id=ropa["id"])
    db.add(ajeno)
    db.commit()
    antes = db.query(Department).get(camisas["id"]).updated_at
    time.sleep(0.01)
    r = client.delete(f"/api/departments/{ropa['id']}", headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    c = db.query(Department).get(camisas["id"])
    assert c is not None and c.parent_id is None and c.updated_at > antes
    assert db.query(Department).get(ajeno.id).parent_id == ropa["id"]
