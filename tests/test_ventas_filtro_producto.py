"""Ventas filtradas por producto vendido (2026-11-25).

`GET /api/sales/?product_id=` (o `variant_id=`) deja solo los tickets que
llevan ese producto, combinado con fechas y sucursal. A la oficina le suma
cuánto se vendió de él; la caja recibe la lista sin importes."""
from datetime import timedelta
from decimal import Decimal

from app.models.returns import SaleReturn, SaleReturnItem
from app.models.sales import DocumentStatus, PaymentMethod, SalesLineItem
from app.services import metricas_ventas as mv
from tests.test_cajero_ventas_del_dia import _ids, _pos, _venta


def _renglon(db, org, doc, variante, cantidad, importe):
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description="Extra", quantity=cantidad, unit_price=Decimal(importe) / cantidad,
                         total_line=Decimal(importe), unit_cost=Decimal("10")))
    db.commit()


def test_filtra_por_producto_y_resume_lo_vendido(client, db, org, branch_a, branch_b, cajero_a, auth_admin, products_setup):
    _pos(db, org)
    pa, va = products_setup["product_a"]
    pb, vb = products_setup["product_b"]
    _, vc = products_setup["product_both"]
    con_a = _venta(db, org, branch_a, cajero_a, va, "100")
    mixto = _venta(db, org, branch_a, cajero_a, vc, "150")
    _renglon(db, org, mixto, va, 2, "180")          # el ticket mixto también lleva A
    solo_b = _venta(db, org, branch_b, cajero_a, vb, "200")
    cancelada = _venta(db, org, branch_a, cajero_a, va, "100")
    cancelada.status = DocumentStatus.CANCELLED
    db.commit()

    r = client.get(f"/api/sales/?product_id={pa.id}", headers=auth_admin)
    assert r.status_code == 200, r.text
    assert _ids(r) == {con_a.id, mixto.id, cancelada.id}
    resumen = r.json()["resumen_producto"]
    # Sin la cancelada, y solo los renglones de A (no el producto Ambos del ticket mixto).
    assert resumen == {"piezas": 3.0, "piezas_devueltas": 0.0, "importe": 280.0, "tickets": 2}

    assert _ids(client.get(f"/api/sales/?variant_id={vb.id}", headers=auth_admin)) == {solo_b.id}
    assert _ids(client.get(f"/api/sales/?product_id={pa.id}&branch_id={branch_b.id}", headers=auth_admin)) == set()
    # Sin filtro de producto no hay resumen.
    assert "resumen_producto" not in client.get("/api/sales/", headers=auth_admin).json()


def test_se_combina_con_fechas_y_cuenta_devueltas(client, db, org, branch_a, cajero_a, auth_admin, products_setup):
    _pos(db, org)
    pa, va = products_setup["product_a"]
    hoy = _venta(db, org, branch_a, cajero_a, va, "100")
    _venta(db, org, branch_a, cajero_a, va, "100", dia=mv.hoy_mx() - timedelta(days=10))
    dev = SaleReturn(organization_id=org.id, sale_id=hoy.id, branch_id=branch_a.id, user_id=cajero_a.id,
                     status="APPROVED", total_refunded=Decimal("100"), refund_method=PaymentMethod.CASH,
                     reason="Talla")
    db.add(dev); db.flush()
    db.add(SaleReturnItem(organization_id=org.id, return_id=dev.id, variant_id=va.id, quantity=1,
                          refund_amount=Decimal("100")))
    db.commit()

    d = mv.hoy_mx()
    r = client.get(f"/api/sales/?product_id={pa.id}&start_date={d}&end_date={d}", headers=auth_admin)
    assert _ids(r) == {hoy.id}
    assert r.json()["resumen_producto"]["piezas_devueltas"] == 1.0


def test_la_caja_filtra_sin_importes(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _pos(db, org)
    pa, va = products_setup["product_a"]
    _, vc = products_setup["product_both"]
    con_a = _venta(db, org, branch_a, cajero_a, va, "100")
    _venta(db, org, branch_a, cajero_a, vc, "150")
    r = client.get(f"/api/sales/?product_id={pa.id}", headers=auth_cajero_a)
    assert _ids(r) == {con_a.id}
    assert "resumen_producto" not in r.json()
