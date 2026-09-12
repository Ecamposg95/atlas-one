"""Un escalón de precio no puede guardarse en cero.

`update_product` validaba el precio BASE (`prod_in.price <= 0`) pero nunca el
`unit_price` de los escalones, y el esquema los acepta (`Money = Field(ge=0)`).
El scanner de tienda destapó el hueco: vaciar el campo de un escalón para
reescribirlo produce `Number('') === 0`, y ese cero llegaba hasta la base. El
producto quedaba vendiéndose a $0.00 en mayoreo o en caja — `pickCheapestTier`
del POS elige el escalón más barato aplicable.

El guard vive en el backend a propósito: es la última línea antes de la base y
protege a cualquier cliente, no solo a la pantalla que lo destapó.
"""
from decimal import Decimal

import pytest

from conftest import _make_product


@pytest.fixture()
def producto_con_escalones(db, org, branch_a):
    from app.models.products import ProductPrice

    prod, v = _make_product(
        db, org, "Pluma Con Escalones", "SKU-TIER", 12.0,
        branches_active=[(branch_a.id, True)],
    )
    db.add(ProductPrice(
        variant_id=v.id, organization_id=org.id,
        price_name="Mayoreo", min_quantity=Decimal("3"), unit_price=Decimal("10"),
    ))
    db.flush()
    return prod


def _payload(**over):
    base = {"sku": "SKU-TIER", "name": "Pluma Con Escalones", "cost": 6.0, "price": 12.0}
    base.update(over)
    return base


class TestGuardEscalonEnCero:
    def test_rechaza_un_escalon_en_cero(self, client, auth_admin, producto_con_escalones):
        resp = client.put(
            f"/api/products/{producto_con_escalones.id}",
            json=_payload(prices=[
                {"price_name": "Mayoreo", "min_quantity": 3, "unit_price": 0},
            ]),
            headers=auth_admin,
        )
        assert resp.status_code == 422, "un escalón en $0 vende el producto regalado"
        assert "cero" in resp.json()["detail"].lower()

    def test_rechaza_un_escalon_negativo(self, client, auth_admin, producto_con_escalones):
        resp = client.put(
            f"/api/products/{producto_con_escalones.id}",
            json=_payload(prices=[
                {"price_name": "Mayoreo", "min_quantity": 3, "unit_price": -5},
            ]),
            headers=auth_admin,
        )
        assert resp.status_code == 422

    def test_nombra_el_escalon_culpable(self, client, auth_admin, producto_con_escalones):
        # El mensaje tiene que decir CUÁL, o con cinco escalones no se sabe dónde
        # está el error.
        resp = client.put(
            f"/api/products/{producto_con_escalones.id}",
            json=_payload(prices=[
                {"price_name": "Mayoreo", "min_quantity": 3, "unit_price": 10},
                {"price_name": "Caja", "min_quantity": 72, "unit_price": 0},
            ]),
            headers=auth_admin,
        )
        assert resp.status_code == 422
        assert "Caja" in resp.json()["detail"]

    def test_un_escalon_valido_sigue_pasando(self, client, auth_admin, producto_con_escalones):
        resp = client.put(
            f"/api/products/{producto_con_escalones.id}",
            json=_payload(prices=[
                {"price_name": "Mayoreo", "min_quantity": 3, "unit_price": 9.5},
            ]),
            headers=auth_admin,
        )
        assert resp.status_code == 200
        assert [float(p["unit_price"]) for p in resp.json()["prices"]] == [9.5]

    def test_sin_prices_no_se_valida_nada(self, client, auth_admin, producto_con_escalones):
        # Un cambio de ficha (nombre, marca) no manda `prices` y no debe romperse.
        resp = client.put(
            f"/api/products/{producto_con_escalones.id}",
            json=_payload(name="Pluma Renombrada"),
            headers=auth_admin,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Pluma Renombrada"
