"""Vaciar marca, departamento o código de barras tiene que vaciarlos de verdad.

`update_product` guardaba cada uno con `if prod_in.X is not None`, así que un
`null` explícito se descartaba en silencio: la pantalla mandaba el cambio,
recibía 200, decía "guardado" y el dato seguía ahí. No era un bug del scanner —
`ProductForm`, `ProductsBranchView` y `Products.tsx` los tres mandan
`campo || null` con intención de borrar, así que en ninguna pantalla se podía
quitar una marca.

Se distingue "ausente" (no lo toques) de "null explícito" (bórralo) con
`model_fields_set`, que es lo que Pydantic expone justo para esto.
"""
import pytest

from conftest import _make_product


@pytest.fixture()
def producto_con_ficha(db, org, branch_a):
    from app.models.products import Brand, Department

    marca = Brand(name="Marca Vieja", organization_id=org.id)
    depto = Department(name="Depto Viejo", organization_id=org.id)
    db.add_all([marca, depto]); db.flush()

    prod, v = _make_product(
        db, org, "Pluma Con Ficha", "SKU-FICHA", 12.0,
        branches_active=[(branch_a.id, True)],
    )
    prod.brand_id = marca.id
    prod.department_id = depto.id
    v.barcode = "750000000001"
    db.flush()
    return prod


def _put(client, headers, pid, **fields):
    body = {"sku": "SKU-FICHA", "name": "Pluma Con Ficha", "cost": 6.0, "price": 12.0}
    body.update(fields)
    return client.put(f"/api/products/{pid}", json=body, headers=headers)


class TestVaciarCampos:
    def test_null_explicito_borra_la_marca(self, client, auth_admin, producto_con_ficha):
        r = _put(client, auth_admin, producto_con_ficha.id, brand_id=None)
        assert r.status_code == 200
        assert r.json()["brand_id"] is None, "mandar brand_id=null debe quitar la marca"

    def test_null_explicito_borra_el_departamento(self, client, auth_admin, producto_con_ficha):
        r = _put(client, auth_admin, producto_con_ficha.id, department_id=None)
        assert r.status_code == 200
        assert r.json()["department"] is None

    def test_cadena_vacia_borra_el_codigo_de_barras(self, client, auth_admin, producto_con_ficha):
        r = _put(client, auth_admin, producto_con_ficha.id, barcode="")
        assert r.status_code == 200
        assert not r.json().get("barcode")

    def test_campo_AUSENTE_no_toca_nada(self, client, auth_admin, producto_con_ficha):
        # La diferencia clave: no mandar el campo significa "no lo toques".
        # Guardar solo el precio no debe borrarle la marca al producto.
        r = _put(client, auth_admin, producto_con_ficha.id, price=15.0)
        assert r.status_code == 200
        assert r.json()["brand_id"] is not None, "un campo ausente NO debe borrarse"
        assert r.json()["department"] is not None
        assert r.json().get("barcode")

    def test_se_puede_reasignar_no_solo_borrar(self, client, auth_admin, producto_con_ficha, db, org):
        from app.models.products import Brand
        nueva = Brand(name="Marca Nueva", organization_id=org.id)
        db.add(nueva); db.flush()
        r = _put(client, auth_admin, producto_con_ficha.id, brand_id=nueva.id)
        assert r.status_code == 200
        assert r.json()["brand_id"] == nueva.id
