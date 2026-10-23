"""Lista del departamento con palomas y marca de ficha corregida."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.products import Brand, Department, Product, ProductVariant
from app.modules.conteos import services
from app.modules.conteos.models import ABIERTO, InventoryCount


def _prenda(db, org, branch, *, name, sku, barcode, depto, stock, size="M", brand=None,
            model=None, description=None):
    p = Product(name=name, organization_id=org.id, is_active=True, department_id=depto.id,
                brand_id=brand.id if brand else None, model=model, description=description)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, barcode=barcode, organization_id=org.id,
                       price=Decimal("1800"), cost=Decimal("900"), size=size, color="Negro")
    db.add(v)
    db.flush()
    if stock is not None:
        db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                           qty_on_hand=Decimal(stock), is_active=True))
    db.flush()
    return v


@pytest.fixture()
def tienda(db, org, branch_a):
    marca = Brand(name="Zegna", organization_id=org.id)
    playeras = Department(name="Playeras", organization_id=org.id)
    db.add_all([marca, playeras])
    db.flush()
    a = _prenda(db, org, branch_a, name="Playera", sku="A", barcode="1", depto=playeras,
                stock="2", brand=marca, model="Slim", description="Algodón pima")
    b = _prenda(db, org, branch_a, name="Camisa", sku="B", barcode="2", depto=playeras, stock="1")
    c = _prenda(db, org, branch_a, name="Vieja", sku="C", barcode="3", depto=playeras, stock="0")
    d = _prenda(db, org, branch_a, name="Sin fila", sku="D", barcode="4", depto=playeras, stock=None)
    conteo = InventoryCount(organization_id=org.id, branch_id=branch_a.id,
                            department_id=playeras.id, status=ABIERTO)
    db.add(conteo)
    db.commit()
    return {"a": a, "b": b, "c": c, "d": d, "conteo": conteo}


def test_lista_trae_todo_el_departamento_con_estado(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "1", None)            # a: 1 de 2 → diferencia
    services.escanear(db, c, "2", None)            # b: 1 de 1 → revisado
    lista = services.lista(db, c)
    por_sku = {f.producto.sku: f for f in lista.filas}
    assert set(por_sku) == {"A", "B", "C", "D"}    # también existencia 0 y sin fila de stock
    assert por_sku["A"].estado == "diferencia" and por_sku["A"].contado == Decimal("1")
    assert por_sku["B"].estado == "revisado" and por_sku["B"].line_id is not None
    assert por_sku["C"].estado == "pendiente" and por_sku["C"].sistema == Decimal("0")
    assert por_sku["D"].estado == "pendiente" and por_sku["D"].line_id is None
    assert por_sku["A"].producto.product_id == tienda["a"].product_id
    assert por_sku["A"].producto.modelo == "Slim"
    assert por_sku["A"].producto.descripcion == "Algodón pima"
    assert por_sku["A"].producto.precio == Decimal("1800")
    assert por_sku["A"].producto.marca_id is not None
    assert lista.totales == {"total": 4, "revisados": 1, "pendientes": 2, "con_diferencia": 1, "corregidas": 0}
    # Orden: por nombre de producto y luego talla.
    assert [f.producto.sku for f in lista.filas] == ["B", "A", "D", "C"]


def test_marcar_corregida_y_reporte(db, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "1", None)
    linea = next(l for l in c.lineas if l.id == r.linea.id)
    linea = services.marcar_corregida(db, c, linea, True)
    assert linea.corregida is True
    assert services.a_linea_read(linea).corregida is True
    lista = services.lista(db, c)
    assert next(f for f in lista.filas if f.producto.sku == "A").corregida is True
    assert lista.totales["corregidas"] == 1
    rep = services.reporte(db, c)
    assert next(f for f in rep.faltantes if f.sku == "A").corregida is True
    assert rep.totales["corregidas"] == 1
    assert services.marcar_corregida(db, c, linea, False).corregida is False


def test_lista_api_y_patch_corregida(client, db, org, branch_a, auth_admin, tienda):
    h = {**auth_admin, "X-Organization-ID": str(org.id)}
    cid = tienda["conteo"].id
    r = client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "2"})
    lid = r.json()["linea"]["id"]
    assert r.json()["linea"]["corregida"] is False
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={"corregida": True})
    assert r.status_code == 200 and r.json()["corregida"] is True and r.json()["qty_contada"] == "1"
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={})
    assert r.status_code == 422
    r = client.get(f"/api/inventory/counts/{cid}/lista", headers=h)
    assert r.status_code == 200
    assert r.json()["totales"]["total"] == 4 and r.json()["totales"]["corregidas"] == 1
    fila_b = next(f for f in r.json()["filas"] if f["producto"]["sku"] == "B")
    assert fila_b["estado"] == "revisado" and fila_b["corregida"] is True
