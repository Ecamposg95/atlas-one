"""La cajera solo ve las ventas de hoy (México) de su sucursal; el resto de roles no cambia."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.modules import OrganizationModule
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem
from app.services import metricas_ventas as mv

_MX = ZoneInfo("America/Mexico_City")
_folios = count(5000)


def _instante(dia, hora=12):
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variante, total="100", *, dia=None, hora=12):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(organization_id=org.id, branch_id=branch.id if branch else None, seller_id=user.id,
                        folio=next(_folios), series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
                        total_amount=Decimal(total), status=DocumentStatus.PAID, doc_type="INVOICE")
    doc.created_at = _instante(dia, hora)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description="Producto", quantity=1, unit_price=Decimal(total),
                         total_line=Decimal(total), unit_cost=Decimal("10")))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=PaymentMethod.CASH, amount=Decimal(total))
    pago.created_at = doc.created_at
    db.add(pago)
    db.commit()
    return doc


def _v(ps):
    return ps["product_a"][1]


def _pos(db, org):
    db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    db.commit()


def _ayer():
    return mv.hoy_mx() - timedelta(days=1)


def _ids(resp):
    return {i["id"] for i in resp.json()["items"]}


def test_cajero_solo_ve_ventas_de_hoy(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    hoy = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    r = client.get("/api/sales/", headers=auth_cajero_a)
    assert r.status_code == 200
    assert _ids(r) == {hoy.id}


def test_cajero_ignora_fechas_y_sucursal(client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    hoy = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    _venta(db, org, branch_b, cajero_a, _v(products_setup))
    _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    a = _ayer()
    r = client.get(f"/api/sales/?start_date={a}&end_date={a}&branch_id={branch_b.id}", headers=auth_cajero_a)
    assert _ids(r) == {hoy.id}
    assert r.json()["total"] == 1


def test_venta_de_ayer_noche_no_aparece(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer(), hora=23)
    r = client.get("/api/sales/", headers=auth_cajero_a)
    assert r.json()["items"] == []


def test_folio_search_de_ayer_vacio(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    r = client.get(f"/api/sales/?folio_search={v.folio}", headers=auth_cajero_a)
    assert r.json()["items"] == []


def test_detalle_de_ayer_404(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    ayer = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    hoy = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    assert client.get(f"/api/sales/{ayer.id}", headers=auth_cajero_a).status_code == 404
    assert client.get(f"/api/sales/{hoy.id}", headers=auth_cajero_a).status_code == 200


def test_print_view_de_ayer_404(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    ayer = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    hoy = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    assert client.get(f"/api/sales/{ayer.id}/print-view", headers=auth_cajero_a).status_code == 404
    assert client.get(f"/api/sales/{hoy.id}/print-view", headers=auth_cajero_a).status_code == 200


def test_venta_sin_sucursal_invisible_para_cajero(cajero_a):
    # branch_id es NOT NULL en la tabla; el caso solo existe en datos legados, se prueba la regla directa.
    from app.models.sales import SalesDocument
    from app.services.ventas_cajero import venta_visible_para_cajero
    legada = SalesDocument(branch_id=None)
    legada.created_at = datetime.now(timezone.utc)
    assert venta_visible_para_cajero(legada, cajero_a) is False


def test_gerente_sigue_viendo_ayer(client, db, org, branch_a, cajero_a, auth_gerente_a, products_setup):
    _pos(db, org)
    ayer = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    a = _ayer()
    r = client.get(f"/api/sales/?start_date={a}&end_date={a}", headers=auth_gerente_a)
    assert ayer.id in _ids(r)


def test_gerente_stats_sigue_200(client, db, org, branch_a, branch_b, cajero_a, auth_gerente_a, products_setup):
    _pos(db, org)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    r = client.get("/api/sales/stats", headers=auth_gerente_a)
    assert r.status_code == 200
    assert r.json()["total_sales"] == 100.0


# --- Devoluciones ---------------------------------------------------------

def _devolver(client, headers, venta, variante):
    return client.post("/api/returns/", json={
        "sale_id": venta.id,
        "reason": "Prueba",
        "total_refunded": "1.00",
        "refund_method": "CASH",
        "items": [{"variant_id": variante.id, "quantity": "1",
                   "refund_amount": "1.00", "is_inventory_reentry": True}],
    }, headers=headers)


def test_cajero_devuelve_venta_de_hoy(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    r = _devolver(client, auth_cajero_a, v, _v(products_setup))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING"


def test_cajero_no_devuelve_venta_de_ayer(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    r = _devolver(client, auth_cajero_a, v, _v(products_setup))
    assert r.status_code == 403
    assert r.json()["detail"] == "Solo puedes devolver ventas de hoy. Para días anteriores pide al gerente."


def test_cajero_no_devuelve_otra_sucursal(client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_b, cajero_a, _v(products_setup))
    assert _devolver(client, auth_cajero_a, v, _v(products_setup)).status_code == 404


def test_gerente_devuelve_venta_de_ayer(client, db, org, branch_a, cajero_a, auth_gerente_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    r = _devolver(client, auth_gerente_a, v, _v(products_setup))
    assert r.status_code == 200, r.text


def test_gerente_no_devuelve_otra_sucursal(client, db, org, branch_a, branch_b, cajero_a, auth_gerente_a, products_setup):
    _pos(db, org)
    v = _venta(db, org, branch_b, cajero_a, _v(products_setup))
    assert _devolver(client, auth_gerente_a, v, _v(products_setup)).status_code == 404
