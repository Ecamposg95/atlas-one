"""Vale de tienda, cambio de producto y CRM (2026-11-24)."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.cash import CashMovement
from app.models.vales import StoreVoucher
from tests.cobranza_helpers import _habilitar
from tests.test_cajero_ventas_del_dia import _abrir_caja, _v, _venta


def _listo(db, org, branch, user, libre="1000"):
    _habilitar(db, org, "pos", "crm")
    org.devolucion_libre_hasta = Decimal(libre)
    db.commit()
    return _abrir_caja(db, org, branch, user)


def _devolver(client, headers, venta, variante, destino, metodo="CASH"):
    return client.post("/api/returns/", headers=headers, json={
        "sale_id": venta.id, "reason": "", "reason_code": "TALLA", "total_refunded": "0",
        "refund_method": metodo, "destino": destino,
        "items": [{"variant_id": variante.id, "quantity": "1", "refund_amount": "0",
                   "is_inventory_reentry": True}],
    })


def _cobrar(client, headers, sku, pagos):
    return client.post("/api/sales/", headers=headers, json={
        "doc_type": "ORDER", "items": [{"sku": sku, "quantity": 1}], "payments": pagos,
    })


# --- Vale de tienda --------------------------------------------------------

def test_devolucion_a_vale_no_saca_efectivo_y_emite_vale(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    turno = _listo(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    r = _devolver(client, auth_cajero_a, v, _v(products_setup), "VALE")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "APPROVED" and d["destino"] == "VALE" and d["refund_method"] == "OTHER"
    assert Decimal(str(d["vale"]["balance"])) == Decimal("100") and len(d["vale"]["code"]) == 8
    assert db.query(CashMovement).filter(CashMovement.session_id == turno.id).count() == 0
    c = client.get(f"/api/vales/{d['vale']['code'].lower()}", headers=auth_cajero_a)
    assert c.status_code == 200 and c.json()["status"] == "ACTIVO"
    assert [m["kind"] for m in c.json()["movimientos"]] == ["EMISION"]


def test_vale_pendiente_no_existe_hasta_autorizar(client, db, org, branch_a, cajero_a, gerente_a, auth_cajero_a, products_setup):
    _listo(db, org, branch_a, cajero_a, libre="0")
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    r = _devolver(client, auth_cajero_a, v, _v(products_setup), "CAMBIO")
    assert r.json()["status"] == "PENDING" and r.json()["vale"] is None
    assert db.query(StoreVoucher).count() == 0
    ok = client.post(f"/api/returns/{r.json()['id']}/autorizar", json={"pin": "test1234"}, headers=auth_cajero_a)
    assert ok.status_code == 200, ok.text
    assert Decimal(str(ok.json()["vale"]["balance"])) == Decimal("100")
    assert db.query(StoreVoucher).count() == 1


def test_el_vale_se_cobra_y_se_agota(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _listo(db, org, branch_a, cajero_a)
    variante = _v(products_setup)
    v = _venta(db, org, branch_a, cajero_a, variante, "60")
    codigo = _devolver(client, auth_cajero_a, v, variante, "VALE").json()["vale"]["code"]

    # Más de lo que tiene: no se cobra y el saldo queda intacto
    mal = _cobrar(client, auth_cajero_a, variante.sku, [{"method": "OTHER", "amount": "61", "reference": f"VALE:{codigo}"},
                                                         {"method": "CASH", "amount": "39"}])
    assert mal.status_code == 400 and "no alcanza" in mal.json()["detail"]
    assert Decimal(str(client.get(f"/api/vales/{codigo}", headers=auth_cajero_a).json()["balance"])) == Decimal("60")

    ok = _cobrar(client, auth_cajero_a, variante.sku, [{"method": "OTHER", "amount": "60", "reference": f"VALE:{codigo}"},
                                                        {"method": "CASH", "amount": "40"}])
    assert ok.status_code in (200, 201), ok.text
    vale = client.get(f"/api/vales/{codigo}", headers=auth_cajero_a).json()
    assert Decimal(str(vale["balance"])) == 0 and vale["status"] == "AGOTADO"
    assert [m["kind"] for m in vale["movimientos"]] == ["EMISION", "USO"]

    otra = _cobrar(client, auth_cajero_a, variante.sku, [{"method": "OTHER", "amount": "1", "reference": f"VALE:{codigo}"},
                                                          {"method": "CASH", "amount": "99"}])
    assert otra.status_code == 400


def test_vale_inexistente_o_de_otra_tienda_400(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _listo(db, org, branch_a, cajero_a)
    from app.services.vales import emitir_vale
    from app.models.organization import Organization
    org_b = Organization(name="Otra tienda")
    db.add(org_b); db.flush()
    ajeno = emitir_vale(db, org_id=org_b.id, amount=Decimal("500"))
    db.commit()
    assert client.get(f"/api/vales/{ajeno.code}", headers=auth_cajero_a).status_code == 404
    r = _cobrar(client, auth_cajero_a, _v(products_setup).sku,
                [{"method": "OTHER", "amount": "10", "reference": f"VALE:{ajeno.code}"}, {"method": "CASH", "amount": "90"}])
    assert r.status_code == 400 and "no existe" in r.json()["detail"]
    db.refresh(ajeno)
    assert Decimal(str(ajeno.balance)) == Decimal("500")


def test_cancelar_la_venta_regresa_el_saldo_al_vale(client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin, products_setup):
    _listo(db, org, branch_a, cajero_a)
    variante = _v(products_setup)
    v = _venta(db, org, branch_a, cajero_a, variante, "40")
    codigo = _devolver(client, auth_cajero_a, v, variante, "VALE").json()["vale"]["code"]
    venta = _cobrar(client, auth_cajero_a, variante.sku, [{"method": "OTHER", "amount": "40", "reference": f"VALE:{codigo}"},
                                                           {"method": "CASH", "amount": "60"}])
    assert venta.status_code in (200, 201), venta.text
    sale_id = venta.json().get("id") or venta.json().get("sale_id")
    c = client.delete(f"/api/sales/{sale_id}", headers=auth_admin, params={"reason": "prueba"})
    assert c.status_code == 200, c.text
    vale = client.get(f"/api/vales/{codigo}", headers=auth_cajero_a).json()
    assert Decimal(str(vale["balance"])) == Decimal("40") and vale["status"] == "ACTIVO"


def test_ticket_pagado_con_vale_no_regresa_en_efectivo(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _listo(db, org, branch_a, cajero_a)
    from app.models.sales import Payment
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    pago = db.query(Payment).filter(Payment.sales_document_id == v.id).one()
    pago.method, pago.reference = "OTHER", "VALE:ABCDEFGH"
    db.commit()
    r = _devolver(client, auth_cajero_a, v, _v(products_setup), "DINERO", metodo="CASH")
    assert r.status_code == 400 and "vale" in r.json()["detail"].lower()
    assert _devolver(client, auth_cajero_a, v, _v(products_setup), "VALE").status_code == 200


def test_lista_y_cancelacion_de_vales_por_rol(client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin, products_setup):
    _listo(db, org, branch_a, cajero_a)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    vale = _devolver(client, auth_cajero_a, v, _v(products_setup), "VALE").json()["vale"]
    assert client.get("/api/vales/", headers=auth_cajero_a).status_code == 403
    assert client.get("/api/vales/", headers=auth_admin).json()["total"] == 1
    assert client.post(f"/api/vales/{vale['id']}/cancelar", headers=auth_cajero_a).status_code == 403
    c = client.post(f"/api/vales/{vale['id']}/cancelar", headers=auth_admin)
    assert c.status_code == 200 and c.json()["status"] == "CANCELADO" and Decimal(str(c.json()["balance"])) == 0


# --- CRM -------------------------------------------------------------------

def test_alta_rapida_de_caja_ignora_credito(client, db, org, cajero_a, auth_cajero_a):
    _habilitar(db, org, "crm")
    r = client.post("/api/customers/", headers=auth_cajero_a, json={
        "name": "Ana", "phone": "5511112222", "has_credit": True, "credit_limit": "9999", "tipo": "MAYOREO"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["has_credit"] is False and Decimal(str(d["credit_limit"])) == 0 and d["tipo"] == "MENUDEO"
    assert client.put(f"/api/customers/{d['id']}", headers=auth_cajero_a, json={"phone": "5500000000"}).status_code == 200
    assert client.put(f"/api/customers/{d['id']}", headers=auth_cajero_a, json={"has_credit": True}).status_code == 403


def test_campos_propios_tope_y_valores(client, db, org, auth_admin, auth_cajero_a):
    _habilitar(db, org, "crm")
    assert client.post("/api/customers/campos", headers=auth_cajero_a, json={"label": "X"}).status_code == 403
    talla = client.post("/api/customers/campos", headers=auth_admin,
                        json={"label": "Talla", "tipo": "LISTA", "opciones": ["CH", "M", "G"]}).json()
    assert talla["key"] == "talla"
    for i in range(9):
        assert client.post("/api/customers/campos", headers=auth_admin, json={"label": f"Campo {i}"}).status_code == 200
    tope = client.post("/api/customers/campos", headers=auth_admin, json={"label": "Once"})
    assert tope.status_code == 400 and "tope" in tope.json()["detail"]

    c = client.post("/api/customers/", headers=auth_admin, json={
        "name": "Mayorista", "tipo": "MAYOREO", "company": "Boutique Sol", "birthday": "1990-05-17",
        "campos": {"talla": "M", "inventado": "x"}})
    assert c.status_code == 200, c.text
    assert c.json()["campos"] == {"talla": "M"} and c.json()["tipo"] == "MAYOREO" and c.json()["birthday"] == "1990-05-17"
    mal = client.put(f"/api/customers/{c.json()['id']}", headers=auth_admin, json={"campos": {"talla": "XXL"}})
    assert mal.status_code == 400

    assert client.delete(f"/api/customers/campos/{talla['id']}", headers=auth_admin).status_code == 200
    assert len(client.get("/api/customers/campos", headers=auth_admin).json()) == 9


def test_ficha_360_gerencia_ve_acumulados_y_la_caja_no(client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin, products_setup):
    _habilitar(db, org, "pos", "crm")
    cid = client.post("/api/customers/", headers=auth_admin, json={"name": "Lupita"}).json()["id"]
    for total in ("100", "300"):
        v = _venta(db, org, branch_a, cajero_a, _v(products_setup), total)
        v.customer_id = cid
    db.commit()
    f = client.get(f"/api/customers/{cid}/ficha", headers=auth_admin).json()
    assert f["limitado"] is False and f["resumen"]["tickets"] == 2 and f["resumen"]["total_comprado"] == 400.0
    assert f["resumen"]["ticket_promedio"] == 200.0 and len(f["compras"]) == 2 and f["productos"][0]["piezas"] == 2.0
    caja = client.get(f"/api/customers/{cid}/ficha", headers=auth_cajero_a).json()
    assert caja["limitado"] is True and caja["resumen"] is None and caja["productos"] == [] and len(caja["compras"]) == 2
    assert client.get("/api/customers/999999/ficha", headers=auth_admin).status_code == 404


def test_seguimiento_crear_listar_y_cerrar(client, db, org, cajero_a, auth_cajero_a, auth_admin):
    _habilitar(db, org, "crm")
    cid = client.post("/api/customers/", headers=auth_admin, json={"name": "Rosa", "phone": "5512345678"}).json()["id"]
    manana = (date.today() + timedelta(days=1)).isoformat()
    t = client.post("/api/customers/seguimiento", headers=auth_cajero_a,
                    json={"customer_id": cid, "tipo": "WHATSAPP", "nota": "Avisar que llegó su talla", "due_date": manana})
    assert t.status_code == 200, t.text
    assert t.json()["assigned_user_id"] == cajero_a.id and t.json()["customer_name"] == "Rosa"
    assert client.post("/api/customers/seguimiento", headers=auth_admin,
                       json={"customer_id": cid, "tipo": "NADA", "due_date": manana}).status_code == 400
    lista = client.get("/api/customers/seguimiento", headers=auth_admin).json()["items"]
    assert [x["id"] for x in lista] == [t.json()["id"]]
    assert client.get("/api/customers/seguimiento", headers=auth_admin, params={"hasta": date.today().isoformat()}).json()["items"] == []
    h = client.post(f"/api/customers/seguimiento/{t.json()['id']}/hecho", headers=auth_cajero_a, json={"resultado": "Pasa el sábado"})
    assert h.json()["status"] == "HECHO" and h.json()["resultado"] == "Pasa el sábado"
    assert client.get("/api/customers/seguimiento", headers=auth_admin).json()["items"] == []
    assert len(client.get(f"/api/customers/{cid}/ficha", headers=auth_admin).json()["seguimiento"]) == 1
