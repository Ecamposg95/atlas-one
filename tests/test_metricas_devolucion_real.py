"""La venta neta de los reportes con una devolución aprobada por el flujo real.

`approve_return` rebaja `total_amount` del ticket, y `metricas_ventas` además
restaba `total_refunded`: una venta de 200 con devolución de 100 reportaba
neta 0, y una devolución total dejaba la venta en negativo.
"""
from decimal import Decimal

from app.crud import returns as crud_returns
from app.services import metricas_ventas as mv

from tests.test_crm_credito_auditoria import _devolucion, _escenario, _fiar, _cliente


def _vender_200(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    venta = _fiar(client, h, _cliente(db, org), variant.sku, qty=2,
                  pagos=[{"method": "CASH", "amount": "200.00"}])
    return variant, venta["sale_id"]


def _devolver(db, org, branch_a, cajero_a, sale_id, variant, monto):
    d = _devolucion(db, org, branch_a, cajero_a, sale_id, variant, Decimal(monto))
    crud_returns.approve_return(db, d.id, supervisor_id=cajero_a.id, organization_id=org.id)
    db.commit()


def _hoy(db, org):
    return mv.resumen(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))


def test_devolucion_parcial_se_resta_una_sola_vez(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    variant, sale_id = _vender_200(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    _devolver(db, org, branch_a, cajero_a, sale_id, variant, "100.00")

    r = _hoy(db, org)
    assert (r.bruta, r.devuelto, r.neta) == (200.0, 100.0, 100.0)
    periodo = mv.periodo_preset("hoy")
    assert mv.por_sucursal(db, org.id, periodo)[branch_a.id].neta == 100.0
    assert sum(d.neta for d in mv.por_dia(db, mv.Ambito(org.id, None, True), periodo)) == 100.0
    assert sum(h.neta for h in mv.por_hora(db, mv.Ambito(org.id, None, True), periodo)) == 100.0


def test_devolucion_total_deja_la_venta_en_cero_no_en_negativo(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    variant, sale_id = _vender_200(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    _devolver(db, org, branch_a, cajero_a, sale_id, variant, "100.00")
    _devolver(db, org, branch_a, cajero_a, sale_id, variant, "100.00")

    r = _hoy(db, org)
    assert (r.bruta, r.devuelto, r.neta) == (200.0, 200.0, 0.0)
