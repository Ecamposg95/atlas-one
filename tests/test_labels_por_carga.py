"""`/api/labels/candidates?carga_id=`: solo las variantes que recibieron piezas
de una carga (kardex con `reference = "carga:<id>"`), con lo que entró."""
from decimal import Decimal

from app.models.inventory import InventoryMovement, MovementType
from app.models.organization import Organization

from tests.test_labels_api import _h, _por_sku, tienda  # noqa: F401  (fixture)


def _entrada(db, org_id, branch, variant, qty, reference):
    db.add(InventoryMovement(
        organization_id=org_id, branch_id=branch.id, variant_id=variant.id,
        movement_type=MovementType.ADJUSTMENT_IN, qty_change=Decimal(qty),
        qty_before=Decimal(0), qty_after=Decimal(qty), reference=reference,
    ))
    db.flush()


def test_filtra_solo_variantes_de_la_carga(client, db, org, branch_a, tienda, auth_admin):
    _, v_cham = tienda["chamarra"]
    _, v_play = tienda["sin_codigo"]
    _entrada(db, org.id, branch_a, v_cham, "3", "carga:abc")
    _entrada(db, org.id, branch_a, v_play, "2", "carga:otra")
    db.commit()
    r = client.get("/api/labels/candidates?carga_id=abc", headers=_h(auth_admin, org))
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["LV-CHAM-SLI-NEG-M"]


def test_piezas_carga_es_lo_que_entro(client, db, org, branch_a, tienda, auth_admin):
    _, v = tienda["chamarra"]  # existencia 5... entraron 3 de 2 renglones
    _entrada(db, org.id, branch_a, v, "2", "carga:abc")
    _entrada(db, org.id, branch_a, v, "1", "carga:abc")
    db.commit()
    fila = client.get("/api/labels/candidates?carga_id=abc",
                      headers=_h(auth_admin, org)).json()["items"][0]
    assert fila["stock"] == 3.0
    assert fila["piezas_carga"] == 3
    # Sin filtro de carga el campo no se llena.
    sin = _por_sku(client.get("/api/labels/candidates", headers=_h(auth_admin, org)).json()["items"])
    assert sin["LV-CHAM-SLI-NEG-M"]["piezas_carga"] is None


def test_carga_de_otra_org_da_lista_vacia(client, db, org, branch_a, tienda, auth_admin):
    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    _, v = tienda["chamarra"]
    _entrada(db, otra.id, branch_a, v, "3", "carga:abc")
    db.commit()
    r = client.get("/api/labels/candidates?carga_id=abc", headers=_h(auth_admin, org))
    assert r.status_code == 200
    assert r.json()["items"] == []
