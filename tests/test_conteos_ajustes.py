# tests/test_conteos_ajustes.py
"""Fase 2: el conteo ajusta la existencia por el mismo kardex que /inventory/adjust."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.inventory import InventoryMovement, StockOnHand
from app.models.products import Department, Product, ProductVariant
from app.modules.conteos import services
from app.modules.conteos.models import ABIERTO, InventoryCount


def _prenda(db, org, branch, *, name, sku, barcode, depto, stock):
    p = Product(name=name, organization_id=org.id, is_active=True, department_id=depto.id)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, barcode=barcode, organization_id=org.id,
                       price=Decimal("100"), cost=Decimal("50"), size="M")
    db.add(v)
    db.flush()
    if stock is not None:
        db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                           qty_on_hand=Decimal(stock), is_active=True))
    db.flush()
    return v


def _stock(db, v, branch):
    s = db.query(StockOnHand).filter_by(variant_id=v.id, branch_id=branch.id).first()
    return Decimal(s.qty_on_hand) if s else Decimal("0")


@pytest.fixture()
def tienda(db, org, branch_a):
    playeras = Department(name="Playeras", organization_id=org.id)
    tenis = Department(name="Tenis", organization_id=org.id)
    db.add_all([playeras, tenis])
    db.flush()
    a = _prenda(db, org, branch_a, name="Playera", sku="A", barcode="1", depto=playeras, stock="3")
    b = _prenda(db, org, branch_a, name="Camisa", sku="B", barcode="2", depto=playeras, stock="2")
    c = _prenda(db, org, branch_a, name="Vieja", sku="C", barcode="3", depto=playeras, stock="0")
    t = _prenda(db, org, branch_a, name="Tenis", sku="T", barcode="4", depto=tenis, stock="1")
    conteo = InventoryCount(organization_id=org.id, branch_id=branch_a.id,
                            department_id=playeras.id, status=ABIERTO)
    db.add(conteo)
    db.commit()
    return {"a": a, "b": b, "c": c, "t": t, "conteo": conteo, "playeras": playeras}


def test_ajustar_linea_en_piso(db, org, branch_a, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "1", None)            # a: contado 1, sistema 3
    linea = next(l for l in c.lineas if l.id == r.linea.id)
    res = services.ajustar_linea(db, c, linea, None)
    assert res.qty_sistema == Decimal("1") and res.linea.ajustada is True
    assert _stock(db, tienda["a"], branch_a) == Decimal("1")
    mov = db.query(InventoryMovement).filter_by(variant_id=tienda["a"].id).order_by(InventoryMovement.id.desc()).first()
    assert mov.qty_change == Decimal("-2") and mov.reference == "Conteo" and "Conteo #" in mov.notes
    assert next(f for f in services.lista(db, c).filas if f.producto.sku == "A").estado == "revisado"
    with pytest.raises(HTTPException) as e:        # ya cuadra
        services.ajustar_linea(db, c, linea, None)
    assert e.value.status_code == 409


def test_ajustar_linea_sube_sobrante(db, org, branch_a, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "3", None)            # c: contado 1, sistema 0
    linea = next(l for l in c.lineas if l.id == r.linea.id)
    services.ajustar_linea(db, c, linea, None)
    assert _stock(db, tienda["c"], branch_a) == Decimal("1")


def test_aplicar_tras_cerrar_usa_la_diferencia_congelada(db, org, branch_a, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "1", None)                 # a: 1 de 3 → −2
    services.escanear(db, c, "3", None)                 # c: 1 de 0 → +1
    services.escanear(db, c, "4", None)                 # t: fuera de departamento, 1 de 1
    services.cerrar(db, c, None)                        # b nunca escaneada: 0 de 2 → −2
    # Venta después del cierre: a baja a 0 en el sistema.
    s = db.query(StockOnHand).filter_by(variant_id=tienda["a"].id).first()
    s.qty_on_hand = Decimal("0")
    db.commit()
    rep = services.aplicar(db, c, [tienda["a"].id, tienda["c"].id], None)
    # a: delta congelado −2 sobre existencia 0 → se recorta a 0 (no negativo)
    assert _stock(db, tienda["a"], branch_a) == Decimal("0")
    assert _stock(db, tienda["c"], branch_a) == Decimal("1")
    assert _stock(db, tienda["b"], branch_a) == Decimal("2")      # no seleccionada: intacta
    assert {x.variant_id for x in rep.ajustes} == {tienda["a"].id, tienda["c"].id}
    recorte = next(x for x in rep.ajustes if x.variant_id == tienda["a"].id)
    assert recorte.delta == Decimal("0") and recorte.recortado is True
    assert rep.aplicado_en is not None and c.aplicado_at is not None
    assert next(f for f in rep.faltantes if f.sku == "A").ajustada is True
    assert next(f for f in rep.faltantes if f.sku == "B").ajustada is False
    assert rep.totales["ajustadas"] == 2
    # Idempotente: repetir con las mismas filas no mueve nada ni duplica.
    rep2 = services.aplicar(db, c, [tienda["a"].id, tienda["b"].id], None)
    assert _stock(db, tienda["b"], branch_a) == Decimal("0")
    assert len(rep2.ajustes) == 3
    assert db.query(InventoryMovement).filter(InventoryMovement.reference == "Conteo").count() == 2  # solo c (+1) y b (−2); a se recorta a 0 y no crea


def test_aplicar_rechaza_abierto_vacio_y_desconocidos(db, org, branch_a, tienda):
    c = tienda["conteo"]
    with pytest.raises(HTTPException) as e:
        services.aplicar(db, c, [tienda["a"].id], None)
    assert e.value.status_code == 409
    services.cerrar(db, c, None)
    with pytest.raises(HTTPException) as e:
        services.aplicar(db, c, [], None)
    assert e.value.status_code == 422
    rep = services.aplicar(db, c, ["no-existe"], None)
    assert rep.ajustes == []


def test_api_ajustar_y_apply(client, db, org, branch_a, auth_admin, auth_cajero_a, tienda):
    h = {**auth_admin, "X-Organization-ID": str(org.id)}
    cid = tienda["conteo"].id
    lid = client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "1"}).json()["linea"]["id"]
    r = client.post(f"/api/inventory/counts/{cid}/lines/{lid}/ajustar", headers=h)
    assert r.status_code == 200 and r.json()["qty_sistema"] == "1" and r.json()["linea"]["ajustada"] is True
    r = client.post(f"/api/inventory/counts/{cid}/apply", headers=h, json={"variant_ids": [tienda["b"].id]})
    assert r.status_code == 409                       # abierto
    client.post(f"/api/inventory/counts/{cid}/close", headers=h)
    r = client.post(f"/api/inventory/counts/{cid}/apply", headers=h, json={"variant_ids": [tienda["b"].id]})
    assert r.status_code == 200 and r.json()["totales"]["ajustadas"] == 1
    assert r.json()["aplicado_en"] is not None
    r = client.post(f"/api/inventory/counts/{cid}/apply", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)}, json={"variant_ids": [tienda["b"].id]})
    assert r.status_code == 403


def test_inventory_adjust_sigue_igual(client, db, org, branch_a, auth_admin, tienda):
    """El handler viejo usa la función extraída y no cambia de contrato."""
    h = {**auth_admin, "X-Organization-ID": str(org.id)}
    r = client.post("/api/inventory/adjust", headers=h, json={
        "variant_id": tienda["a"].id, "quantity": "-1", "reason": "Merma", "branch_id": branch_a.id})
    assert r.status_code == 200 and r.json()["qty_after"] == "2.00"
    r = client.post("/api/inventory/adjust", headers=h, json={
        "variant_id": tienda["a"].id, "quantity": "-5", "reason": "Merma", "branch_id": branch_a.id})
    assert r.status_code == 400


def test_aplicar_recorta_con_remanente_bajo_el_candado(db, org, branch_a, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "1", None)                 # a: 1 de 3 → −2 congelado
    services.cerrar(db, c, None)
    s = db.query(StockOnHand).filter_by(variant_id=tienda["a"].id).first()
    s.qty_on_hand = Decimal("1")                        # venta posterior al cierre
    db.commit()
    rep = services.aplicar(db, c, [tienda["a"].id], None)
    aj = rep.ajustes[0]
    assert aj.delta == Decimal("-1") and aj.recortado is True
    assert aj.qty_before == Decimal("1") and aj.qty_after == Decimal("0")
    mov = db.query(InventoryMovement).filter_by(variant_id=tienda["a"].id, reference="Conteo").one()
    assert mov.qty_change == Decimal("-1") and "recortado a 0" in mov.notes
    assert _stock(db, tienda["a"], branch_a) == Decimal("0")


def test_ajustar_linea_dos_toques_el_segundo_ya_cuadra(db, org, branch_a, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "3", None)             # sobrante: contado 1, sistema 0
    linea = next(l for l in c.lineas if l.id == r.linea.id)
    services.ajustar_linea(db, c, linea, None)
    with pytest.raises(HTTPException) as e:
        services.ajustar_linea(db, c, linea, None)
    assert e.value.status_code == 409
    assert _stock(db, tienda["c"], branch_a) == Decimal("1")   # no se duplicó


def test_aplicar_es_atomico_si_una_fila_falla(db, org, branch_a, tienda, monkeypatch):
    c = tienda["conteo"]
    services.escanear(db, c, "3", None)                 # c: +1
    services.cerrar(db, c, None)
    real = services.aplicar_ajuste
    llamadas = []

    def falla_en_la_segunda(*a, **k):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise HTTPException(400, "Stock insuficiente para realizar este ajuste.")
        return real(*a, **k)

    monkeypatch.setattr(services, "aplicar_ajuste", falla_en_la_segunda)
    # La sesión de pruebas vive dentro de una transacción externa, así que un
    # rollback real se llevaría también la siembra: se prueba que NINGÚN commit
    # ocurre antes del fallo (el rollback de la petición descarta lo pendiente).
    commits = []
    commit_real = db.commit
    monkeypatch.setattr(db, "commit", lambda: (commits.append(1), commit_real())[1])
    resumen_antes = c.resumen
    with pytest.raises(HTTPException):
        services.aplicar(db, c, [tienda["c"].id, tienda["b"].id], None)
    assert commits == []
    assert c.resumen == resumen_antes and c.aplicado_at is None


def test_ajustar_linea_de_nuevo_tras_contar_otra_pieza(db, org, branch_a, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "3", None)             # c: contado 1, sistema 0
    linea = next(l for l in c.lineas if l.id == r.linea.id)
    services.ajustar_linea(db, c, linea, None)
    assert _stock(db, tienda["c"], branch_a) == Decimal("1")
    services.escanear(db, c, "3", None)                 # aparece otra igual: contado 2
    linea = next(l for l in c.lineas if l.id == r.linea.id)
    res = services.ajustar_linea(db, c, linea, None)
    assert _stock(db, tienda["c"], branch_a) == Decimal("2")
    assert res.linea.ajustada is True and linea.ajustada_at is not None


def test_aplicar_fuera_de_alcance_con_diferencia_cero_no_mueve_kardex(db, org, branch_a, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "4", None)                 # t: fuera de depto, contado 1 de 1
    services.cerrar(db, c, None)
    rep = services.aplicar(db, c, [tienda["t"].id], None)
    aj = rep.ajustes[0]
    assert aj.variant_id == tienda["t"].id and aj.movimiento_id is None and aj.delta == Decimal("0")
    assert db.query(InventoryMovement).filter_by(variant_id=tienda["t"].id).count() == 0
    assert _stock(db, tienda["t"], branch_a) == Decimal("1")
