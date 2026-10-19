"""`GET /api/reports/valor-inventario` -- cuanto vale la existencia hoy.

Dos cifras que siempre van juntas: valor a precio de venta (completo: toda
variante tiene precio) y valor a costo (solo variantes con costo > 0), mas el
conteo de piezas y SKUs sin costo. Caso guia: Eleven (zapatos cargados con
costo 0) e Imaltzin (el importador de rmazh deja `cost` NULL). Sin este
conteo, "valor a costo = $0" se lee como "mi tienda no vale nada".
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.organization import Branch, BranchType, Organization
from app.models.products import Brand, Department, Product, ProductVariant
from app.models.users import Role
from conftest import _auth_header, _make_user

URL = "/api/reports/valor-inventario"


def _producto(db, org, nombre, sku, precio, costo, existencias,
              department_id=None, brand_id=None):
    """Producto de una sola variante con existencias `{branch_id: qty}`.

    `costo=None` deja la columna en NULL (como el importador de rmazh);
    `costo=0` es el caso de los zapatos de Eleven.
    """
    p = Product(name=nombre, organization_id=org.id, is_active=True,
                department_id=department_id, brand_id=brand_id)
    db.add(p)
    db.flush()
    v = ProductVariant(
        product_id=p.id, sku=sku, organization_id=org.id,
        price=Decimal(str(precio)),
        cost=None if costo is None else Decimal(str(costo)),
    )
    db.add(v)
    db.flush()
    for branch_id, qty in existencias.items():
        db.add(StockOnHand(
            variant_id=v.id, branch_id=branch_id, organization_id=org.id,
            qty_on_hand=Decimal(str(qty)), is_active=True,
        ))
    db.flush()
    return p, v


@pytest.fixture()
def tienda(db, org, branch_a, branch_b):
    """Tres SKUs en dos sucursales que venden.

    Bolsa   $1000 costo $400 : 3 en A, 2 en B  -> venta 5000, costo 2000
    Zapato  $800  costo 0    : 4 en A          -> venta 3200, sin costo (4 pz)
    Playera $200  costo NULL : 10 en B         -> venta 2000, sin costo (10 pz)
    Totales: 19 piezas, 3 SKUs, venta 10200, costo 2000, 14 pz / 2 SKUs sin costo.
    Sucursal A: 7 pz, 2 SKUs, venta 6200, costo 1200, 4 pz sin costo.
    Sucursal B: 12 pz, 2 SKUs, venta 4000, costo 800, 10 pz sin costo.
    """
    bolsas = Department(name="Bolsas", organization_id=org.id)
    zapatos = Department(name="Zapatos", organization_id=org.id)
    gucci = Brand(name="Gucci", organization_id=org.id)
    db.add_all([bolsas, zapatos, gucci])
    db.flush()
    bolsa = _producto(db, org, "Bolsa", "BOL-1", 1000, 400,
                      {branch_a.id: 3, branch_b.id: 2},
                      department_id=bolsas.id, brand_id=gucci.id)
    zapato = _producto(db, org, "Zapato", "ZAP-1", 800, 0, {branch_a.id: 4},
                       department_id=zapatos.id)
    playera = _producto(db, org, "Playera", "PLA-1", 200, None, {branch_b.id: 10})
    return {
        "bolsa": bolsa, "zapato": zapato, "playera": playera,
        "dept_bolsas": bolsas, "dept_zapatos": zapatos, "marca_gucci": gucci,
    }


# ---------------------------------------------------------------- totales

def test_admin_ve_totales_de_la_organizacion(client, auth_admin, tienda):
    r = client.get(URL, headers=auth_admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ve_costo"] is True
    assert body["branch_id"] is None
    assert body["totales"] == {
        "piezas": 19.0, "skus": 3,
        "valor_venta": 10200.0, "valor_costo": 2000.0,
        "piezas_sin_costo": 14.0, "skus_sin_costo": 2,
    }


def test_costo_cero_cuenta_en_venta_pero_no_en_costo(client, auth_admin, db, org, branch_a):
    _producto(db, org, "Zapato", "ZAP-1", 800, 0, {branch_a.id: 4})
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["valor_venta"] == 3200.0
    assert t["valor_costo"] == 0.0
    assert t["piezas_sin_costo"] == 4.0
    assert t["skus_sin_costo"] == 1


def test_costo_null_cuenta_en_venta_pero_no_en_costo(client, auth_admin, db, org, branch_a):
    _producto(db, org, "Playera", "PLA-1", 200, None, {branch_a.id: 10})
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["valor_venta"] == 2000.0
    assert t["valor_costo"] == 0.0
    assert t["piezas_sin_costo"] == 10.0
    assert t["skus_sin_costo"] == 1


def test_sucursal_que_no_vende_queda_fuera_salvo_que_se_pida(client, auth_admin, db, org, tienda):
    bodega = Branch(name="Bodega", branch_type=BranchType.WAREHOUSE,
                    can_sell=False, is_active=True, organization_id=org.id)
    db.add(bodega)
    db.flush()
    _, v = tienda["bolsa"]
    db.add(StockOnHand(variant_id=v.id, branch_id=bodega.id, organization_id=org.id,
                       qty_on_hand=Decimal("100"), is_active=True))
    db.flush()

    sin_filtro = client.get(URL, headers=auth_admin).json()["totales"]
    assert sin_filtro["valor_venta"] == 10200.0
    assert sin_filtro["piezas"] == 19.0

    solo_bodega = client.get(URL, params={"branch_id": bodega.id}, headers=auth_admin).json()
    assert solo_bodega["branch_id"] == bodega.id
    assert solo_bodega["totales"]["piezas"] == 100.0
    assert solo_bodega["totales"]["valor_venta"] == 100000.0
    assert solo_bodega["totales"]["valor_costo"] == 40000.0


def test_sucursal_desactivada_queda_fuera_salvo_que_se_pida(client, auth_admin, db, org, tienda):
    cerrada = Branch(name="Cerrada", branch_type=BranchType.STORE,
                     can_sell=True, is_active=False, organization_id=org.id)
    db.add(cerrada)
    db.flush()
    _, v = tienda["bolsa"]
    db.add(StockOnHand(variant_id=v.id, branch_id=cerrada.id, organization_id=org.id,
                       qty_on_hand=Decimal("100"), is_active=True))
    db.flush()

    body = client.get(URL, headers=auth_admin).json()
    assert body["totales"]["valor_venta"] == 10200.0
    assert body["totales"]["piezas"] == 19.0
    assert str(cerrada.id) not in [g["clave"] for g in body["grupos"]]

    solo = client.get(URL, params={"branch_id": cerrada.id}, headers=auth_admin).json()
    assert solo["totales"]["piezas"] == 100.0
    assert solo["totales"]["valor_venta"] == 100000.0


def test_producto_con_variante_con_costo_y_otra_sin_costo(client, auth_admin, db, org, branch_a):
    p, _ = _producto(db, org, "Tenis", "TEN-1", 500, 200, {branch_a.id: 2})
    v2 = ProductVariant(product_id=p.id, sku="TEN-2", organization_id=org.id,
                        price=Decimal("300"), cost=None)
    db.add(v2)
    db.flush()
    db.add(StockOnHand(variant_id=v2.id, branch_id=branch_a.id, organization_id=org.id,
                       qty_on_hand=Decimal("3"), is_active=True))
    db.flush()
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["valor_venta"] == 1900.0   # 2*500 + 3*300
    assert t["valor_costo"] == 400.0    # solo la variante con costo
    assert t["piezas_sin_costo"] == 3.0
    assert t["skus_sin_costo"] == 1
    assert t["skus"] == 2


def test_filtro_por_sucursal(client, auth_admin, branch_a, tienda):
    t = client.get(URL, params={"branch_id": branch_a.id}, headers=auth_admin).json()["totales"]
    assert t == {
        "piezas": 7.0, "skus": 2,
        "valor_venta": 6200.0, "valor_costo": 1200.0,
        "piezas_sin_costo": 4.0, "skus_sin_costo": 1,
    }


def test_producto_borrado_queda_fuera(client, auth_admin, db, tienda):
    p, v = tienda["zapato"]
    p.deleted_at = datetime.now(timezone.utc)
    p.is_active = False
    v.deleted_at = datetime.now(timezone.utc)
    db.flush()
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 15.0
    assert t["valor_venta"] == 7000.0
    assert t["skus"] == 2


def test_variante_borrada_queda_fuera_aunque_el_producto_siga(client, auth_admin, db, tienda):
    _, v = tienda["playera"]
    v.deleted_at = datetime.now(timezone.utc)
    db.flush()
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 9.0
    assert t["valor_venta"] == 8200.0
    assert t["piezas_sin_costo"] == 4.0


def test_existencia_negativa_no_resta(client, auth_admin, db, org, branch_a, tienda):
    """Una venta sin stock deja la existencia en negativo; eso es un error de
    inventario, no valor negativo de la tienda."""
    _producto(db, org, "Fantasma", "FAN-1", 5000, 2500, {branch_a.id: -3})
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 19.0
    assert t["valor_venta"] == 10200.0
    assert t["valor_costo"] == 2000.0


def test_org_sin_existencias_devuelve_ceros(client, auth_admin, org):
    r = client.get(URL, headers=auth_admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totales"] == {
        "piezas": 0.0, "skus": 0, "valor_venta": 0.0, "valor_costo": 0.0,
        "piezas_sin_costo": 0.0, "skus_sin_costo": 0,
    }
    assert body["grupos"] == []


def test_otra_organizacion_no_se_mezcla(client, auth_admin, db, tienda):
    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    suc = Branch(name="Suc Otra", branch_type=BranchType.STORE,
                 can_sell=True, is_active=True, organization_id=otra.id)
    db.add(suc)
    db.flush()
    _producto(db, otra, "Ajeno", "AJ-1", 9999, 5000, {suc.id: 50})

    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 19.0
    assert t["valor_venta"] == 10200.0

    r = client.get(URL, params={"branch_id": suc.id}, headers=auth_admin)
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------- agrupacion

def _grupo(body, nombre):
    return next(g for g in body["grupos"] if g["nombre"] == nombre)


def test_agrupar_por_sucursal_es_el_default_y_ordena_por_valor_venta(client, auth_admin, branch_a, branch_b, tienda):
    body = client.get(URL, headers=auth_admin).json()
    assert body["agrupar"] == "sucursal"
    assert [g["nombre"] for g in body["grupos"]] == ["Sucursal A", "Sucursal B"]
    a = _grupo(body, "Sucursal A")
    assert a["clave"] == str(branch_a.id)
    assert a == {
        "clave": str(branch_a.id), "nombre": "Sucursal A",
        "piezas": 7.0, "skus": 2, "valor_venta": 6200.0, "valor_costo": 1200.0,
        "piezas_sin_costo": 4.0,
    }
    b = _grupo(body, "Sucursal B")
    assert b["clave"] == str(branch_b.id)
    assert (b["piezas"], b["valor_venta"], b["valor_costo"], b["piezas_sin_costo"]) == (12.0, 4000.0, 800.0, 10.0)


def test_agrupar_departamento_incluye_sin_departamento(client, auth_admin, tienda):
    body = client.get(URL, params={"agrupar": "departamento"}, headers=auth_admin).json()
    assert body["agrupar"] == "departamento"
    assert [g["nombre"] for g in body["grupos"]] == ["Bolsas", "Zapatos", "Sin departamento"]
    assert _grupo(body, "Bolsas")["clave"] == tienda["dept_bolsas"].id
    assert _grupo(body, "Bolsas")["valor_venta"] == 5000.0
    assert _grupo(body, "Bolsas")["valor_costo"] == 2000.0
    assert _grupo(body, "Zapatos")["piezas_sin_costo"] == 4.0
    sin = _grupo(body, "Sin departamento")
    assert sin["clave"] == ""
    assert sin["piezas"] == 10.0
    assert sin["valor_venta"] == 2000.0
    # La suma de los grupos cuadra con los totales: nada se pierde por faltar el dato.
    assert sum(g["valor_venta"] for g in body["grupos"]) == body["totales"]["valor_venta"]


def test_agrupar_marca_incluye_sin_marca(client, auth_admin, tienda):
    body = client.get(URL, params={"agrupar": "marca"}, headers=auth_admin).json()
    assert [g["nombre"] for g in body["grupos"]] == ["Sin marca", "Gucci"]
    gucci = _grupo(body, "Gucci")
    assert gucci["clave"] == tienda["marca_gucci"].id
    assert (gucci["piezas"], gucci["valor_venta"]) == (5.0, 5000.0)
    sin = _grupo(body, "Sin marca")
    assert sin["clave"] == ""
    assert (sin["piezas"], sin["valor_venta"], sin["piezas_sin_costo"]) == (14.0, 5200.0, 14.0)


def test_agrupar_con_filtro_de_sucursal(client, auth_admin, branch_a, tienda):
    body = client.get(URL, params={"agrupar": "departamento", "branch_id": branch_a.id}, headers=auth_admin).json()
    assert [g["nombre"] for g in body["grupos"]] == ["Zapatos", "Bolsas"]
    assert _grupo(body, "Bolsas")["piezas"] == 3.0


def test_agrupar_invalido_es_422(client, auth_admin, tienda):
    r = client.get(URL, params={"agrupar": "color"}, headers=auth_admin)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- roles

def test_gerente_ve_su_sucursal_sin_costos(client, auth_gerente_a, branch_a, tienda):
    body = client.get(URL, params={"agrupar": "departamento"}, headers=auth_gerente_a).json()
    assert body["ve_costo"] is False
    assert body["branch_id"] == branch_a.id
    t = body["totales"]
    assert (t["piezas"], t["skus"], t["valor_venta"]) == (7.0, 2, 6200.0)
    assert t["valor_costo"] is None
    # El hueco de costos si lo ve: es "que falta capturar", no dinero.
    assert t["piezas_sin_costo"] == 4.0
    assert all(g["valor_costo"] is None for g in body["grupos"])
    assert [g["nombre"] for g in body["grupos"]] == ["Zapatos", "Bolsas"]


def test_gerente_no_puede_mirar_otra_sucursal(client, auth_gerente_a, branch_a, branch_b, tienda):
    body = client.get(URL, params={"branch_id": branch_b.id}, headers=auth_gerente_a).json()
    assert body["branch_id"] == branch_a.id
    assert body["totales"]["valor_venta"] == 6200.0


def test_gerente_sin_sucursal_403(client, db, org, tienda):
    gerente = _make_user(db, org, None, "gerente_sin_sucursal", Role.GERENTE)
    r = client.get(URL, headers=_auth_header(gerente))
    assert r.status_code == 403, r.text
    assert "sucursal" in r.json()["detail"].lower()


def test_cajero_403(client, auth_cajero_a, tienda):
    r = client.get(URL, headers=auth_cajero_a)
    assert r.status_code == 403, r.text


def test_vendedor_sin_sucursal_403(client, auth_vendedor_sin_sucursal, tienda):
    r = client.get(URL, headers=auth_vendedor_sin_sucursal)
    assert r.status_code == 403, r.text


def test_dueno_ve_costos(client, db, org, hq_branch, tienda):
    dueno = _make_user(db, org, hq_branch, "dueno_test", Role.DUEÑO)
    body = client.get(URL, headers=_auth_header(dueno)).json()
    assert body["ve_costo"] is True
    assert body["totales"]["valor_costo"] == 2000.0


def test_superadmin_ve_costos_con_header_de_org(client, auth_superadmin, org, tienda):
    r = client.get(URL, headers={**auth_superadmin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert r.json()["totales"]["valor_costo"] == 2000.0
