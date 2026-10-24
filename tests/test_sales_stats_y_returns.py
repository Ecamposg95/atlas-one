"""`/sales/stats` y `/returns/` con el criterio único de `metricas_ventas`."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.modules import OrganizationModule
from app.models.returns import SaleReturn
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem
from app.services import metricas_ventas as mv

_MX = ZoneInfo("America/Mexico_City")
_folios = count(1)


def _instante(dia, hora=12):
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variante, total, *, dia=None, hora=12, status=DocumentStatus.PAID, doc_type="INVOICE"):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
                        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
                        total_amount=Decimal(total), status=status, doc_type=doc_type)
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


def _devolucion(db, org, branch, user, venta, importe, *, dia=None, status="APPROVED"):
    dev = SaleReturn(organization_id=org.id, sale_id=venta.id, user_id=user.id, branch_id=branch.id,
                     total_refunded=Decimal(importe), refund_method=PaymentMethod.CASH, reason="Prueba",
                     status=status)
    dev.created_at = _instante(dia or mv.hoy_mx())
    db.add(dev)
    db.commit()
    return dev


def _v(products_setup):
    return products_setup["product_a"][1]


def test_sales_stats_neto_sin_pendientes_y_con_hora_pico(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", hora=17)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "50", hora=17)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "999", status=DocumentStatus.PENDING)
    _devolucion(db, org, branch_a, cajero_a, v, "30")
    s = client.get(f"/api/sales/stats?start_date={hoy}&end_date={hoy}", headers=auth_admin_a).json()
    assert (s["total_sales"], s["gross_sales"], s["total_transactions"]) == (120.0, 150.0, 2)
    assert s["average_ticket"] == 60.0
    assert (s["refund_count"], s["refund_total"]) == (1, 30.0)
    assert s["payment_methods"]["CASH"] == 120.0
    assert s["peak_hour"] == "17:00"


def test_sales_stats_cajera_solo_su_sucursal(client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup):
    db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))  # la cajera pasa por el candado del módulo
    db.commit()
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    s = client.get("/api/sales/stats", headers=auth_cajero_a).json()
    assert s["total_sales"] == 100.0


def test_returns_lista_por_dia_de_mexico_y_30_dias_por_defecto(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy - timedelta(days=40))
    vieja = _devolucion(db, org, branch_a, cajero_a, v, "10", dia=hoy - timedelta(days=40))
    reciente = _devolucion(db, org, branch_a, cajero_a, v, "20", dia=hoy)
    pendiente_vieja = _devolucion(db, org, branch_a, cajero_a, v, "5", dia=hoy - timedelta(days=40), status="PENDING")

    ids = {r["id"] for r in client.get("/api/returns/", headers=auth_admin_a).json()}
    assert reciente.id in ids and vieja.id not in ids

    ids = {r["id"] for r in client.get("/api/returns/?status=PENDING", headers=auth_admin_a).json()}
    assert ids == {pendiente_vieja.id}

    desde = hoy - timedelta(days=45)
    ids = {r["id"] for r in client.get(f"/api/returns/?start_date={desde}&end_date={hoy}", headers=auth_admin_a).json()}
    assert {vieja.id, reciente.id, pendiente_vieja.id} <= ids

    ids = {r["id"] for r in client.get(f"/api/returns/?start_date={hoy}&end_date={hoy}", headers=auth_admin_a).json()}
    assert ids == {reciente.id}
