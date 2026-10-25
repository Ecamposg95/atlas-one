# tests/test_reports_dashboard.py
"""`/reports/dashboard`, `/reports/sales-by-hour` y `/reports/command-center/stats`
sobre `metricas_ventas`: neto, día de México, 24 horas y ámbito explícito."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.returns import SaleReturn
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem
from app.services import metricas_ventas as mv

_MX = ZoneInfo("America/Mexico_City")
_folios = count(1)


def _instante(dia, hora=12):
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variante, total, *, dia=None, hora=12, status=DocumentStatus.PAID):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
                        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
                        total_amount=Decimal(total), status=status, doc_type="ORDER")
    doc.created_at = _instante(dia, hora)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description=f"Producto {doc.folio}", quantity=1, unit_price=Decimal(total),
                         total_line=Decimal(total), unit_cost=Decimal("10")))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=PaymentMethod.CASH, amount=Decimal(total))
    pago.created_at = doc.created_at
    db.add(pago)
    db.commit()
    return doc


def _devolucion(db, org, branch, user, venta, importe):
    dev = SaleReturn(organization_id=org.id, sale_id=venta.id, user_id=user.id, branch_id=branch.id,
                     total_refunded=Decimal(importe), refund_method=PaymentMethod.CASH, reason="Prueba",
                     status="APPROVED")
    db.add(dev)
    db.commit()
    return dev


def _v(products_setup):
    return products_setup["product_a"][1]


def test_dashboard_tendencia_agrupa_por_dia_de_mexico(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy, hora=19)   # 01:00 UTC de mañana
    d = client.get(f"/api/reports/dashboard?start_date={hoy - timedelta(days=1)}&end_date={hoy}&branch_id=0",
                   headers=auth_admin_a).json()
    assert d["charts"]["trend"]["data"] == [0.0, 100.0]
    assert d["kpis"]["sales"] == 100.0


def test_dashboard_kpis_netos_y_comparativo(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy)
    _devolucion(db, org, branch_a, cajero_a, v, "25")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "60", dia=hoy - timedelta(days=1))
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()
    k = d["kpis"]
    assert (k["sales"], k["orders"], k["returns"], k["returns_count"]) == (75.0, 1, 25.0, 1)
    assert k["avg_ticket"] == 75.0
    assert (k["prev_sales"], k["prev_orders"], k["prev_returns"]) == (60.0, 1, 0.0)
    assert d["charts"]["trend_previous"]["data"] == [60.0]
    assert d["charts"]["payments"]["CASH"] == {"total": 75.0, "count": 1}


def test_dashboard_admin_sin_sucursal_en_query_ve_toda_la_org(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    hoy = mv.hoy_mx()
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}", headers=auth_admin_a).json()
    assert d["kpis"]["sales"] == 300.0


def test_dashboard_y_sales_by_hour_traen_24_horas(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", hora=7)
    hoy = mv.hoy_mx()
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()
    assert len(d["charts"]["hourly"]["labels"]) == 24 and d["charts"]["hourly"]["data"][7] == 100.0
    h = client.get("/api/reports/sales-by-hour?branch_id=0", headers=auth_admin_a).json()
    assert [x["hour"] for x in h["hourly"]] == list(range(24))
    assert h["hourly"][7] == {"hour": 7, "amount": 100.0, "tickets": 1}


def test_command_center_global_y_sucursales_netos(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a, products_setup):
    va = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    _devolucion(db, org, branch_a, cajero_a, va, "30")
    d = client.get("/api/reports/command-center/stats", headers=auth_admin_a).json()
    assert d["global"]["total_sales"] == 270.0 and d["global"]["returns_total"] == 30.0
    por_sucursal = {b["id"]: b["total_sales"] for b in d["branches"]}
    assert por_sucursal[branch_a.id] == 70.0 and por_sucursal[branch_b.id] == 200.0
    assert len(d["hourly_distribution"]) == 24
