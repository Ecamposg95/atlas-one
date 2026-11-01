"""Corte de caja con ventas fiadas (spec 2026-10-29 §2.3).

La venta fiada cuenta en "Ventas totales" del turno; lo que quedó a cuenta se
reporta como `credit_sales` y los abonos cobrados en el turno como
`customer_payments`. El efectivo esperado no cambia de criterio, pero el abono
LIBRE (pago sin documento) por fin entra: el `join` interno a `SalesDocument`
lo dejaba fuera del cajón aunque los billetes estuvieran ahí.
"""
from app.modules.customers.models import CustomerLedgerEntry
from app.modules.customers.services import es_abono, es_reversion
from app.routers.cash import get_session_audit_data
from tests.cobranza_helpers import _abonar, _cliente, _escenario, _fiar


def test_la_venta_fiada_cuenta_en_el_corte_y_el_fiado_se_reporta(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "40.00"}])

    audit = get_session_audit_data(db, sesion.id)
    assert audit["kpis"]["total_sales"] == 100.0
    assert audit["kpis"]["total_tickets"] == 1
    assert audit["kpis"]["credit_sales"] == 60.0
    assert audit["kpis"]["customer_payments"] == 0.0
    assert audit["payments"]["cash"]["total"] == 40.0
    assert audit["expected"]["cash_physical"] == 40.0, "el esperado solo suma lo que entró"


def test_el_abono_libre_en_efectivo_entra_al_esperado_y_al_desglose(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """Review Focus 1: el abono sin ticket nace como Payment sin documento y el
    join interno lo dejaba fuera del cajón."""
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    _abonar(client, h, cliente, "30")

    audit = get_session_audit_data(db, sesion.id)
    assert audit["payments"]["cash"] == {"total": 30.0, "count": 1}
    assert audit["expected"]["cash_physical"] == 30.0
    assert audit["kpis"]["customer_payments"] == 30.0
    assert audit["kpis"]["total_sales"] == 100.0
    assert audit["kpis"]["credit_sales"] == 100.0, "el abono es cobranza: no baja el fiado del turno"


def test_la_venta_fiada_cancelada_no_deja_fiado(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku)
    r = client.delete(f"/api/sales/{venta['sale_id']}", params={"reason": "Se arrepintió"}, headers=h)
    assert r.status_code == 200, r.text

    audit = get_session_audit_data(db, sesion.id)
    assert audit["kpis"]["total_sales"] == 0.0
    assert audit["kpis"]["total_tickets"] == 0
    assert audit["kpis"]["credit_sales"] == 0.0


def test_el_resumen_de_sucursal_suma_fiado_y_abonos(
    client, db, org, branch_a, cajero_a, auth_cajero_a, gerente_a, auth_gerente_a, products_setup
):
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "40.00"}])
    _abonar(client, h, cliente, "30")

    r = client.get(f"/api/cash/branch-summary?branch_id={branch_a.id}",
                   headers={**auth_gerente_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totals"]["sales"] == 100.0
    assert data["totals"]["tickets"] == 1
    assert data["totals"]["credit_sales"] == 60.0
    assert data["totals"]["customer_payments"] == 30.0
    assert data["totals"]["cash"] == 70.0
    fila = next(c for c in data["cashiers"] if c["session_id"] == sesion.id)
    assert (fila["credit_sales"], fila["customer_payments"], fila["cash"]) == (60.0, 30.0, 70.0)


def test_las_reversiones_se_distinguen_de_los_abonos(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """La clasificación por prefijo es la única forma de separar un abono de
    una cancelación en el ledger; si alguien cambia el texto, esto truena."""
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    a = _fiar(client, h, cliente, variant.sku)
    _abonar(client, h, cliente, "20", documento=a["sale_id"])
    b = _fiar(client, h, cliente, variant.sku)
    assert client.delete(f"/api/sales/{b['sale_id']}", params={"reason": "x"}, headers=h).status_code == 200

    asientos = db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.customer_id == cliente.id).order_by(CustomerLedgerEntry.id).all()
    assert [float(x.amount) for x in asientos] == [100.0, -20.0, 100.0, -100.0]
    assert [es_abono(x) for x in asientos] == [False, True, False, False]
    assert [es_reversion(x) for x in asientos] == [False, False, False, True]


def test_la_cotizacion_y_el_pedido_con_cliente_no_cuentan_en_el_corte(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """Una cotización/pedido PENDING con cliente cae en el turno por el respaldo
    legacy (vendedor + sucursal + horario) pero no es un ticket: la fiada solo
    es INVOICE."""
    from tests.cobranza_helpers import _habilitar
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    _habilitar(db, org, "quotes")
    cliente = _cliente(db, org)
    for tipo in ("QUOTE", "ORDER"):
        r = client.post("/api/quotes/", json={
            "doc_type": tipo, "customer_id": cliente.id,
            "items": [{"sku": variant.sku, "quantity": 1}], "payments": [],
        }, headers=h)
        assert r.status_code == 200, r.text

    audit = get_session_audit_data(db, sesion.id)
    assert audit["kpis"]["total_sales"] == 0.0
    assert audit["kpis"]["total_tickets"] == 0
    assert audit["kpis"]["credit_sales"] == 0.0
    assert audit["expected"]["total_system"] == float(sesion.opening_balance)
