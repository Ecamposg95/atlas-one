"""Ventas pasadas y devoluciones de la caja (2026-11-24).

La cajera consulta las ventas de su sucursal dentro del plazo de la tienda
(30 días por omisión), sin totales. Devuelve sola hasta el monto que fije la
tienda; arriba de eso, el gerente autoriza con su PIN en la misma caja."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.cash import CashMovement
from app.models.inventory import StockOnHand
from app.models.sales import PaymentMethod
from app.services import metricas_ventas as mv
from app.services import reprint_auth
from tests.test_cajero_ventas_del_dia import _abrir_caja, _ids, _pos, _v, _venta


def _hace(dias):
    return mv.hoy_mx() - timedelta(days=dias)


@pytest.fixture(autouse=True)
def _sin_bloqueos():
    reprint_auth._INTENTOS_FALLIDOS.clear()
    yield
    reprint_auth._INTENTOS_FALLIDOS.clear()


def _cuerpo(venta, variante, *, metodo="CASH", motivo="TALLA", a_stock=True, nota=""):
    return {
        "sale_id": venta.id, "reason": nota, "reason_code": motivo, "total_refunded": "0",
        "refund_method": metodo,
        "items": [{"variant_id": variante.id, "quantity": "1", "refund_amount": "0",
                   "is_inventory_reentry": a_stock}],
    }


# --- Ventas pasadas --------------------------------------------------------

def test_cajera_ve_30_dias_por_omision(client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    hoy = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    d29 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(29))
    d30 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(30), hora=1)
    d31 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(31), hora=23)
    _venta(db, org, branch_b, cajero_a, _v(products_setup), dia=_hace(2))       # otra sucursal
    r = client.get("/api/sales/", headers=auth_cajero_a)
    assert _ids(r) == {hoy.id, d29.id, d30.id}
    assert client.get(f"/api/sales/{d29.id}", headers=auth_cajero_a).status_code == 200
    assert client.get(f"/api/sales/{d31.id}", headers=auth_cajero_a).status_code == 404
    assert client.get(f"/api/sales/by-folio/A/{d29.folio}", headers=auth_cajero_a).status_code == 200
    assert client.get(f"/api/sales/by-folio/A/{d31.folio}", headers=auth_cajero_a).status_code == 404


def test_fechas_de_la_cajera_filtran_dentro_del_plazo(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    _venta(db, org, branch_a, cajero_a, _v(products_setup))
    d5 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(5))
    d60 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(60))
    r = client.get(f"/api/sales/?start_date={_hace(5)}&end_date={_hace(5)}", headers=auth_cajero_a)
    assert _ids(r) == {d5.id}
    # Pedir fuera del plazo no lo amplía
    r = client.get(f"/api/sales/?start_date={_hace(90)}&end_date={_hace(40)}", headers=auth_cajero_a)
    assert d60.id not in _ids(r) and r.json()["items"] == []


def test_plazo_configurable_por_tienda(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    d40 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(40))
    assert d40.id not in _ids(client.get("/api/sales/", headers=auth_cajero_a))
    org.dias_ventas_caja = 90
    db.commit()
    assert d40.id in _ids(client.get("/api/sales/", headers=auth_cajero_a))


def test_la_cajera_sigue_sin_totales(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(3))
    assert client.get("/api/sales/stats", headers=auth_cajero_a).status_code == 403
    assert client.get("/api/sales/export/csv", headers=auth_cajero_a).status_code == 403


def test_busqueda_por_cliente_y_producto(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    a = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(2))
    b = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(3))
    a.customer_name = "Mariana Torres"
    b.lines[0].description = "Vestido lino azul"
    db.commit()
    assert _ids(client.get("/api/sales/?search=mariana", headers=auth_cajero_a)) == {a.id}
    assert _ids(client.get("/api/sales/?search=lino", headers=auth_cajero_a)) == {b.id}
    sku = _v(products_setup).sku
    assert _ids(client.get(f"/api/sales/?search={sku}", headers=auth_cajero_a)) == {a.id, b.id}
    assert client.get("/api/sales/?search=zzzz", headers=auth_cajero_a).json()["items"] == []


def test_contexto_trae_los_ajustes_de_caja(client, db, org, cajero_a, auth_cajero_a):
    org.dias_ventas_caja = 45
    org.devolucion_libre_hasta = Decimal("300")
    db.commit()
    ctx = client.get("/api/users/me/context", headers=auth_cajero_a).json()
    assert ctx["dias_ventas_caja"] == 45
    assert ctx["devolucion_libre_hasta"] == 300.0


# --- Devoluciones ----------------------------------------------------------

def test_devuelve_venta_de_hace_una_semana_y_no_la_de_fuera_de_plazo(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    _abrir_caja(db, org, branch_a, cajero_a)
    d7 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(7))
    d45 = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(45))
    r = client.post("/api/returns/", json=_cuerpo(d7, _v(products_setup)), headers=auth_cajero_a)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING" and r.json()["reason_code"] == "TALLA"
    assert r.json()["reason"] == "Talla o medida"
    r = client.post("/api/returns/", json=_cuerpo(d45, _v(products_setup)), headers=auth_cajero_a)
    assert r.status_code == 403
    assert "más de 30 días" in r.json()["detail"]


def test_dentro_del_monto_libre_la_caja_devuelve_sola(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    org.devolucion_libre_hasta = Decimal("500")
    db.commit()
    turno = _abrir_caja(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=_hace(2))
    r = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup)), headers=auth_cajero_a)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "APPROVED" and d["autorizacion"] == "POLITICA"
    assert Decimal(str(d["total_refunded"])) == Decimal("100")
    salida = db.query(CashMovement).filter(CashMovement.session_id == turno.id, CashMovement.type == "OUT").all()
    assert [Decimal(str(m.amount)) for m in salida] == [Decimal("100")]


def test_arriba_del_monto_libre_queda_pendiente_y_el_pin_la_autoriza(client, db, org, branch_a, cajero_a, gerente_a, auth_cajero_a, products_setup):
    _pos(db, org)
    org.devolucion_libre_hasta = Decimal("50")
    db.commit()
    turno = _abrir_caja(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    r = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup)), headers=auth_cajero_a)
    assert r.json()["status"] == "PENDING"
    rid = r.json()["id"]

    mal = client.post(f"/api/returns/{rid}/autorizar", json={"pin": "0000"}, headers=auth_cajero_a)
    assert mal.status_code == 403 and mal.json()["detail"]["code"] == "PIN_INCORRECTO"

    ok = client.post(f"/api/returns/{rid}/autorizar", json={"pin": "test1234"}, headers=auth_cajero_a)
    assert ok.status_code == 200, ok.text
    d = ok.json()
    assert d["status"] == "APPROVED" and d["autorizacion"] == "PIN"
    assert d["supervisor"]["username"] == "gerente_a"
    # El efectivo sale del turno de la cajera, no de uno del gerente
    assert db.query(CashMovement).filter(CashMovement.session_id == turno.id, CashMovement.type == "OUT").count() == 1
    # Ya aprobada no se vuelve a autorizar
    assert client.post(f"/api/returns/{rid}/autorizar", json={"pin": "test1234"}, headers=auth_cajero_a).status_code == 400


def test_tres_pines_malos_bloquean(client, db, org, branch_a, cajero_a, gerente_a, auth_cajero_a, products_setup):
    _pos(db, org)
    _abrir_caja(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    rid = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup)), headers=auth_cajero_a).json()["id"]
    for _ in range(3):
        assert client.post(f"/api/returns/{rid}/autorizar", json={"pin": "x"}, headers=auth_cajero_a).status_code == 403
    assert client.post(f"/api/returns/{rid}/autorizar", json={"pin": "test1234"}, headers=auth_cajero_a).status_code == 423


def test_el_reembolso_va_por_el_metodo_de_pago(client, db, org, branch_a, cajero_a, auth_cajero_a, auth_gerente_a, products_setup):
    _pos(db, org)
    _abrir_caja(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    v.payments[0].method = PaymentMethod.CARD
    db.commit()
    r = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup), metodo="CASH"), headers=auth_cajero_a)
    assert r.status_code == 400 and "mismo método" in r.json()["detail"]
    # El gerente conserva el criterio
    r = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup), metodo="CASH"), headers=auth_gerente_a)
    assert r.status_code == 200, r.text


def test_efectivo_sin_caja_abierta_409(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    r = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup)), headers=auth_cajero_a)
    assert r.status_code == 409


def test_motivo_desconocido_400(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    _abrir_caja(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    r = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup), motivo="CAPRICHO"), headers=auth_cajero_a)
    assert r.status_code == 400


def test_piezas_muestra_lo_devuelto_y_lo_que_queda(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    org.devolucion_libre_hasta = Decimal("500")
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    v.lines[0].quantity = 2
    db.commit()
    antes = client.get(f"/api/returns/sale/{v.id}/piezas", headers=auth_cajero_a)
    assert antes.status_code == 200, antes.text
    pz = antes.json()["piezas"][0]
    assert (Decimal(str(pz["vendido"])), Decimal(str(pz["disponible"]))) == (Decimal("2"), Decimal("2"))
    assert Decimal(str(pz["precio_pagado"])) == Decimal("50")
    assert antes.json()["metodos"] == ["CASH"]
    assert Decimal(str(antes.json()["monto_libre"])) == Decimal("500")
    assert {m["code"] for m in antes.json()["motivos"]} >= {"DEFECTO", "TALLA", "NO_GUSTO", "ERROR_COBRO"}

    assert client.post("/api/returns/", json=_cuerpo(v, _v(products_setup)), headers=auth_cajero_a).json()["status"] == "APPROVED"
    pz = client.get(f"/api/returns/sale/{v.id}/piezas", headers=auth_cajero_a).json()["piezas"][0]
    assert (Decimal(str(pz["devuelto"])), Decimal(str(pz["disponible"]))) == (Decimal("1"), Decimal("1"))


def test_piezas_fuera_de_plazo_403(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_hace(45))
    assert client.get(f"/api/returns/sale/{v.id}/piezas", headers=auth_cajero_a).status_code == 403
    assert client.get(f"/api/returns/sale/{v.id}", headers=auth_cajero_a).status_code == 403


def test_merma_no_regresa_a_stock(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    org.devolucion_libre_hasta = Decimal("500")
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)
    variante = _v(products_setup)
    v = _venta(db, org, branch_a, cajero_a, variante)

    def existencia():
        db.expire_all()
        fila = db.query(StockOnHand).filter(StockOnHand.branch_id == branch_a.id, StockOnHand.variant_id == variante.id).first()
        return Decimal(str(fila.qty_on_hand)) if fila else Decimal("0")

    antes = existencia()
    r = client.post("/api/returns/", json=_cuerpo(v, variante, motivo="DEFECTO", a_stock=False, nota="cierre roto"), headers=auth_cajero_a)
    assert r.json()["status"] == "APPROVED" and r.json()["reason"] == "Defecto: cierre roto"
    assert existencia() == antes


def test_comprobante_de_devolucion(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    org.devolucion_libre_hasta = Decimal("500")
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    rid = client.post("/api/returns/", json=_cuerpo(v, _v(products_setup)), headers=auth_cajero_a).json()["id"]
    r = client.post(f"/api/printer/print-return/{rid}", headers=auth_cajero_a)
    assert r.status_code == 200, r.text
    import base64
    texto = base64.b64decode(r.json()["content_base64"]).decode("latin-1")
    assert "DEVOLUCION" in texto and f"A-{v.folio}" in texto and "Total devuelto" in texto


def test_vendedor_no_cambia_ajustes_de_caja(client, db, org, auth_cajero_a):
    r = client.put("/api/organization/", json={"devolucion_libre_hasta": "9999"}, headers=auth_cajero_a)
    assert r.status_code in (401, 403)
    db.refresh(org)
    assert Decimal(str(org.devolucion_libre_hasta or 0)) == Decimal("0")
