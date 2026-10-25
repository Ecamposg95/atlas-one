"""`app/services/metricas_ventas.py` — la única regla de "venta" de los reportes.

Venta neta = documentos cobrados (SALES_REPORT_STATUSES) a su importe original
menos devoluciones APROBADAS en el periodo, todo en día de México.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import update

from app.models.returns import SaleReturn, SaleReturnItem
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem
from app.services import metricas_ventas as mv

_MX = ZoneInfo("America/Mexico_City")
_folios = count(1)


def _instante(dia: date, hora: int = 12) -> datetime:
    """`hora` de México del día `dia`, como instante UTC (así se guarda)."""
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variante, total, *, dia=None, hora=12, status=DocumentStatus.PAID,
           metodo=PaymentMethod.CASH, entregado=None, costo="40"):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"), total_amount=Decimal(total),
        status=status, doc_type="ORDER",
        change_given=(Decimal(entregado) - Decimal(total)) if entregado else None,
    )
    doc.created_at = _instante(dia, hora)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description=f"Producto {doc.folio}", quantity=1, unit_price=Decimal(total),
                         total_line=Decimal(total), unit_cost=Decimal(costo)))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=metodo,
                   amount=Decimal(entregado or total))
    pago.created_at = doc.created_at
    db.add(pago)
    db.commit()
    return doc


def _devolucion(db, org, branch, user, venta, importe, *, dia=None, hora=13, status="APPROVED",
                metodo=PaymentMethod.CASH):
    dia = dia or mv.hoy_mx()
    dev = SaleReturn(organization_id=org.id, sale_id=venta.id, user_id=user.id, branch_id=branch.id,
                     total_refunded=Decimal(importe), refund_method=metodo, reason="Prueba", status=status)
    dev.created_at = _instante(dia, hora)
    db.add(dev)
    db.commit()
    return dev


def _v(products_setup):
    return products_setup["product_a"][1]


# --- Periodo -----------------------------------------------------------------

def test_periodo_anterior_mismo_largo():
    p = mv.Periodo(date(2026, 10, 17), date(2026, 10, 23))
    assert p.dias == 7
    assert p.anterior() == mv.Periodo(date(2026, 10, 10), date(2026, 10, 16))


def test_periodo_preset_7d_y_mes():
    hoy = date(2026, 10, 23)
    assert mv.periodo_preset("hoy", hoy) == mv.Periodo(hoy, hoy)
    assert mv.periodo_preset("ayer", hoy) == mv.Periodo(date(2026, 10, 22), date(2026, 10, 22))
    assert mv.periodo_preset("7d", hoy) == mv.Periodo(date(2026, 10, 17), hoy)
    assert mv.periodo_preset("30d", hoy) == mv.Periodo(date(2026, 9, 24), hoy)
    assert mv.periodo_preset("mes", hoy) == mv.Periodo(date(2026, 10, 1), hoy)
    with pytest.raises(ValueError):
        mv.periodo_preset("trimestre", hoy)


def test_periodo_invertido_revienta():
    with pytest.raises(ValueError):
        mv.Periodo(date(2026, 10, 23), date(2026, 10, 22))


def test_periodo_de_query_una_fecha_es_ese_dia_ninguna_es_hoy_invertido_es_422():
    hoy = date(2026, 10, 23)
    assert mv.periodo_de_query(date(2026, 10, 20), None, hoy) == mv.Periodo(date(2026, 10, 20), date(2026, 10, 20))
    assert mv.periodo_de_query(None, date(2026, 10, 21), hoy) == mv.Periodo(date(2026, 10, 21), date(2026, 10, 21))
    assert mv.periodo_de_query(date(2026, 10, 20), date(2026, 10, 22), hoy) == mv.Periodo(date(2026, 10, 20), date(2026, 10, 22))
    assert mv.periodo_de_query(None, None, hoy) == mv.Periodo(hoy, hoy)
    with pytest.raises(HTTPException) as e:
        mv.periodo_de_query(date(2026, 10, 20), date(2026, 10, 19), hoy)
    assert e.value.status_code == 422


# --- Ámbito ------------------------------------------------------------------

def test_resolver_ambito_admin_sin_parametro_es_toda_la_org(admin_a, org):
    a = mv.resolver_ambito(admin_a, org.id, None)
    assert a.toda_la_org is True and a.branch_id is None
    assert mv.resolver_ambito(admin_a, org.id, 0).toda_la_org is True


def test_resolver_ambito_admin_con_sucursal(admin_a, org, branch_b):
    a = mv.resolver_ambito(admin_a, org.id, branch_b.id)
    assert a == mv.Ambito(org.id, branch_b.id, False)


def test_resolver_ambito_cajera_siempre_la_suya(cajero_a, org, branch_a, branch_b):
    a = mv.resolver_ambito(cajero_a, org.id, branch_b.id)
    assert a == mv.Ambito(org.id, branch_a.id, False)


def test_resolver_ambito_gerente_puede_pedir_otra_sucursal(gerente_a, org, branch_b):
    # GERENTE está en HQ_ROLES de los reportes desde antes; se conserva.
    assert mv.resolver_ambito(gerente_a, org.id, branch_b.id).branch_id == branch_b.id


def test_resolver_ambito_sin_sucursal_no_ve_la_org(vendedor_sin_sucursal, org):
    a = mv.resolver_ambito(vendedor_sin_sucursal, org.id, 0)
    assert a.toda_la_org is False and a.branch_id is None


# --- Resumen -----------------------------------------------------------------

def test_resumen_neta_resta_devoluciones_aprobadas(db, org, branch_a, cajero_a, products_setup):
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "50")
    _devolucion(db, org, branch_a, cajero_a, v, "30")
    _devolucion(db, org, branch_a, cajero_a, v, "20", status="PENDING")
    r = mv.resumen(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert (r.bruta, r.devuelto, r.neta, r.tickets, r.devoluciones) == (150.0, 30.0, 120.0, 2, 1)
    assert r.ticket_promedio == 60.0


def test_resumen_excluye_pendientes_borradores_y_canceladas(db, org, branch_a, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    for st in (DocumentStatus.PENDING, DocumentStatus.DRAFT, DocumentStatus.CANCELLED):
        _venta(db, org, branch_a, cajero_a, _v(products_setup), "999", status=st)
    r = mv.resumen(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert (r.bruta, r.tickets) == (100.0, 1)


def test_resumen_venta_de_las_7pm_cae_en_su_dia_de_mexico(db, org, branch_a, cajero_a, products_setup):
    hoy = mv.hoy_mx()
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy, hora=19)   # 01:00 UTC de mañana
    assert mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(hoy, hoy)).neta == 100.0
    manana = mv.Periodo(hoy + timedelta(days=1), hoy + timedelta(days=1))
    assert mv.resumen(db, mv.Ambito(org.id, None, True), manana).neta == 0.0


def test_devolucion_resta_en_su_propio_dia(db, org, branch_a, cajero_a, products_setup):
    hoy = mv.hoy_mx()
    ayer = hoy - timedelta(days=1)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=ayer)
    _devolucion(db, org, branch_a, cajero_a, v, "100", dia=hoy)
    assert mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(ayer, ayer)).neta == 100.0
    assert mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(hoy, hoy)).neta == -100.0


def test_resumen_respeta_el_ambito(db, org, branch_a, branch_b, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    hoy = mv.periodo_preset("hoy")
    assert mv.resumen(db, mv.Ambito(org.id, branch_a.id, False), hoy).neta == 100.0
    assert mv.resumen(db, mv.Ambito(org.id, None, True), hoy).neta == 300.0
    assert mv.resumen(db, mv.Ambito(org.id, None, False), hoy).tickets == 0


def test_por_dia_rellena_ceros_y_agrupa_en_dia_de_mexico(db, org, branch_a, cajero_a, products_setup):
    hoy = mv.hoy_mx()
    p = mv.Periodo(hoy - timedelta(days=2), hoy)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy - timedelta(days=2), hora=19)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "50", dia=hoy)
    _devolucion(db, org, branch_a, cajero_a, v, "10", dia=hoy)
    dias = mv.por_dia(db, mv.Ambito(org.id, None, True), p)
    assert [d.fecha for d in dias] == p.fechas()
    assert [(d.bruta, d.devuelto, d.neta, d.tickets) for d in dias] == [
        (100.0, 0.0, 100.0, 1), (0.0, 0.0, 0.0, 0), (50.0, 10.0, 40.0, 1),
    ]


def test_por_hora_trae_24_horas_y_no_recorta(db, org, branch_a, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", hora=7)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "200", hora=22)
    horas = mv.por_hora(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert [h.hora for h in horas] == list(range(24))
    assert horas[7].neta == 100.0 and horas[7].tickets == 1
    assert horas[22].neta == 200.0
    assert sum(h.tickets for h in horas) == 2


def test_por_metodo_resta_el_cambio_del_efectivo(db, org, branch_a, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "80", entregado="100")
    m = mv.por_metodo(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert m["CASH"].total == 80.0 and m["CASH"].tickets == 1


def test_por_metodo_resta_la_devolucion_a_su_metodo(db, org, branch_a, cajero_a, products_setup):
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", metodo=PaymentMethod.CASH)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "300", metodo=PaymentMethod.CARD)
    _devolucion(db, org, branch_a, cajero_a, v, "40", metodo=PaymentMethod.CARD)
    m = mv.por_metodo(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert m["CASH"].total == 100.0
    assert m["CARD"].total == 260.0
    assert "TRANSFER" not in m


def test_por_sucursal_devuelve_resumen_neto_por_sucursal(db, org, branch_a, branch_b, cajero_a, products_setup):
    va = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    _devolucion(db, org, branch_a, cajero_a, va, "25")
    s = mv.por_sucursal(db, org.id, mv.periodo_preset("hoy"))
    assert s[branch_a.id].neta == 75.0 and s[branch_a.id].tickets == 1
    assert s[branch_b.id].neta == 200.0


def test_top_productos_por_piezas(db, org, branch_a, cajero_a, products_setup):
    for _ in range(3):
        _venta(db, org, branch_a, cajero_a, _v(products_setup), "10")
    docs = db.query(SalesDocument).all()
    for d in docs:
        for li in db.query(SalesLineItem).filter(SalesLineItem.document_id == d.id):
            li.description = "Gorra"
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "500")
    db.commit()
    top = mv.top_productos(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"), limite=5)
    assert top[0].nombre == "Gorra" and top[0].cantidad == 3.0 and top[0].total == 30.0
    assert len(top) == 2


def test_utilidad_bruta_solo_con_costo_y_resta_reingresos(db, org, branch_a, cajero_a, products_setup):
    variante = _v(products_setup)          # cost = 60 (conftest: precio 100 × 0.6)
    v = _venta(db, org, branch_a, cajero_a, variante, "100", costo="60")
    _venta(db, org, branch_a, cajero_a, variante, "70", costo="0")      # sin costo: fuera de la utilidad
    dev = _devolucion(db, org, branch_a, cajero_a, v, "100")
    db.add(SaleReturnItem(organization_id=org.id, return_id=dev.id, variant_id=variante.id,
                          quantity=Decimal("1"), refund_amount=Decimal("100"), is_inventory_reentry=True))
    db.commit()
    utilidad, sin_costo = mv.utilidad_bruta(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    # (100 − 60) de la venta − (100 − 60) de la devolución que volvió al stock = 0
    assert utilidad == 0.0
    assert sin_costo == 70.0


def _sin_costo(variante, valor):
    """Fija el costo ACTUAL de la variante (la devolución se clasifica por él)."""
    variante.cost = valor


def test_utilidad_bruta_devolucion_sin_reingreso_resta_todo_el_reembolso(db, org, branch_a, cajero_a, products_setup):
    variante = _v(products_setup)
    _sin_costo(variante, Decimal("40"))
    v = _venta(db, org, branch_a, cajero_a, variante, "100", costo="40")
    ambito, hoy = mv.Ambito(org.id, None, True), mv.periodo_preset("hoy")
    assert mv.utilidad_bruta(db, ambito, hoy) == (60.0, 0.0)          # antes de la devolución
    dev = _devolucion(db, org, branch_a, cajero_a, v, "100")
    db.add(SaleReturnItem(organization_id=org.id, return_id=dev.id, variant_id=variante.id,
                          quantity=Decimal("1"), refund_amount=Decimal("100"), is_inventory_reentry=False))
    db.commit()
    utilidad, sin_costo = mv.utilidad_bruta(db, ambito, hoy)
    # (100 − 40) de la venta − 100 de la pieza perdida (ingreso fuera, costo hundido)
    assert utilidad == -40.0
    assert sin_costo == 0.0


def test_utilidad_bruta_reingreso_nulo_cuenta_como_sin_reingreso(db, org, branch_a, cajero_a, products_setup):
    variante = _v(products_setup)
    _sin_costo(variante, Decimal("40"))
    v = _venta(db, org, branch_a, cajero_a, variante, "100", costo="40")
    dev = _devolucion(db, org, branch_a, cajero_a, v, "100")
    db.add(SaleReturnItem(organization_id=org.id, return_id=dev.id, variant_id=variante.id,
                          quantity=Decimal("1"), refund_amount=Decimal("100")))
    db.commit()
    # El ORM salta el None y aplica el default (True): el NULL de filas viejas se fuerza por SQL.
    db.execute(update(SaleReturnItem).values(is_inventory_reentry=None))
    db.commit()
    assert db.query(SaleReturnItem).filter(SaleReturnItem.is_inventory_reentry.is_(None)).count() == 1
    utilidad, _ = mv.utilidad_bruta(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert utilidad == -40.0


def test_utilidad_bruta_devolucion_de_pieza_sin_costo_baja_venta_sin_costo(db, org, branch_a, cajero_a, products_setup):
    variante = _v(products_setup)
    _sin_costo(variante, None)
    v = _venta(db, org, branch_a, cajero_a, variante, "70", costo="0")
    ambito, hoy = mv.Ambito(org.id, None, True), mv.periodo_preset("hoy")
    assert mv.utilidad_bruta(db, ambito, hoy) == (0.0, 70.0)          # antes de la devolución
    dev = _devolucion(db, org, branch_a, cajero_a, v, "70")
    db.add(SaleReturnItem(organization_id=org.id, return_id=dev.id, variant_id=variante.id,
                          quantity=Decimal("1"), refund_amount=Decimal("70"), is_inventory_reentry=True))
    db.commit()
    utilidad, sin_costo = mv.utilidad_bruta(db, ambito, hoy)
    assert sin_costo == 0.0          # la venta vivía aquí y se devolvió
    assert utilidad == 0.0           # y nunca tocó la utilidad


def test_utilidad_bruta_devolucion_sin_reingreso_de_pieza_sin_costo_tambien_baja_venta_sin_costo(db, org, branch_a, cajero_a, products_setup):
    variante = _v(products_setup)
    _sin_costo(variante, Decimal("0"))
    v = _venta(db, org, branch_a, cajero_a, variante, "70", costo="0")
    dev = _devolucion(db, org, branch_a, cajero_a, v, "30")
    db.add(SaleReturnItem(organization_id=org.id, return_id=dev.id, variant_id=variante.id,
                          quantity=Decimal("1"), refund_amount=Decimal("30"), is_inventory_reentry=False))
    db.commit()
    utilidad, sin_costo = mv.utilidad_bruta(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert (utilidad, sin_costo) == (0.0, 40.0)
