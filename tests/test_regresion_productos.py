"""Regresiones de la auditoría funcional del backend (2026-09-22) — productos.

* A-5 `PUT /api/products/{id}` con `description`/`unit`/`image_url: null` no
  borraba el campo (200 silencioso, valor viejo intacto).
* A-6 `core.router` se registraba PRIMERO, así que `GET /{product_id}` tapaba
  toda ruta GET de un solo segmento de los demás sub-routers
  (`/boxes-inventory`, `/search`, `/departments`).
"""
import pytest

from conftest import _make_product


@pytest.fixture()
def producto_con_ficha(db, org, branch_a):
    prod, _ = _make_product(
        db, org, "Playera Con Ficha", "SKU-FICHA", 100.0,
        branches_active=[(branch_a.id, True)],
    )
    prod.description = "Descripcion original que la dueña quiere borrar"
    prod.unit = "pza"
    prod.image_url = "https://cdn.example.com/playera.png"
    db.commit()
    return prod


def _put(client, headers, pid, **fields):
    body = {"sku": "SKU-FICHA", "name": "Playera Con Ficha", "cost": 60.0, "price": 100.0}
    body.update(fields)
    return client.put(f"/api/products/{pid}", json=body, headers=headers)


# ---------------------------------------------------------------- A-5
def test_a5_null_explicito_borra_descripcion_unidad_e_imagen(
    client, auth_admin, producto_con_ficha, db
):
    r = _put(client, auth_admin, producto_con_ficha.id,
             description=None, unit=None, image_url=None)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("description") is None
    db.refresh(producto_con_ficha)
    assert producto_con_ficha.description is None
    assert producto_con_ficha.unit is None
    assert producto_con_ficha.image_url is None


def test_a5_no_mandar_el_campo_lo_deja_igual(client, auth_admin, producto_con_ficha, db):
    r = _put(client, auth_admin, producto_con_ficha.id)
    assert r.status_code == 200, r.text
    db.refresh(producto_con_ficha)
    assert producto_con_ficha.description == "Descripcion original que la dueña quiere borrar"
    assert producto_con_ficha.image_url == "https://cdn.example.com/playera.png"


def test_a5_un_valor_nuevo_sigue_guardandose(client, auth_admin, producto_con_ficha, db):
    r = _put(client, auth_admin, producto_con_ficha.id, description="Nueva ficha", unit="kg")
    assert r.status_code == 200, r.text
    db.refresh(producto_con_ficha)
    assert producto_con_ficha.description == "Nueva ficha"
    assert producto_con_ficha.unit == "kg"


# ---------------------------------------------------------------- A-6
@pytest.mark.parametrize("ruta,params", [
    ("/api/products/boxes-inventory", None),
    ("/api/products/search", {"q": "Playera"}),
    ("/api/products/departments", None),
    ("/api/products/hq-inventory", None),
])
def test_a6_rutas_de_un_segmento_no_las_tapa_product_id(client, auth_admin, ruta, params):
    r = client.get(ruta, params=params, headers=auth_admin)
    assert r.status_code == 200, f"{ruta} -> {r.status_code} {r.text[:200]}"
    assert "Producto no encontrado" not in r.text


def test_a6_el_get_por_id_sigue_resolviendo(client, auth_admin, producto_con_ficha):
    r = client.get(f"/api/products/{producto_con_ficha.id}", headers=auth_admin)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Playera Con Ficha"


def test_a6_un_id_inexistente_sigue_dando_404(client, auth_admin):
    r = client.get("/api/products/00000000-0000-0000-0000-000000000000", headers=auth_admin)
    assert r.status_code == 404
