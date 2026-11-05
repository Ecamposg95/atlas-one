"""Deuda anterior (2026-11-04): el dueño carga lo que una clienta ya debía
antes del sistema (la libreta de Eleven). Sube su saldo con la fecha real de
la deuda, no es venta ni toca caja ni inventario, los abonos la cubren
primero y se puede quitar mientras no tenga abonos."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal

from app.models.platform import PlatformAuditLog
from app.models.sales import DocumentStatus, SalesDocument
from app.modules.customers.models import CustomerLedgerEntry
from app.modules.customers.services import antiguedad_por_cargo, asientos_del_cliente
from app.pos_printer import PosPrinter
from app.services import metricas_ventas as mv
from tests.cobranza_helpers import _cliente, _escenario, _fiar


def _hoy_mx() -> date:
    # El servicio valida "no en el futuro" con el día de México; el runner del CI
    # vive en UTC y de 18:00 a 24:00 de México ya va en el día siguiente.
    return datetime.now(ZoneInfo("America/Mexico_City")).date()


def _ho(auth_admin, org):
    return {**auth_admin, "X-Organization-ID": str(org.id)}


def _cargar(client, h, cliente, monto, fecha, nota=None):
    body = {"amount": str(monto), "fecha": fecha.isoformat()}
    if nota is not None:
        body["nota"] = nota
    return client.post(f"/api/customers/{cliente.id}/deuda-anterior", json=body, headers=h)


def test_el_dueno_carga_la_deuda_con_su_fecha(client, db, org, auth_admin):
    cliente = _cliente(db, org, "Ana")
    fecha = _hoy_mx() - timedelta(days=100)
    r = _cargar(client, _ho(auth_admin, org), cliente, "1500", fecha, "libreta: vestido Zara")
    assert r.status_code == 200, r.text
    d = r.json()
    assert float(d["customer_balance"]) == 1500.0
    assert d["entry"]["description"] == "Deuda anterior: libreta: vestido Zara"
    assert d["entry"]["sales_document_id"] is None
    assert d["entry"]["created_at"][:10] == fecha.isoformat()
    db.refresh(cliente)
    assert cliente.current_balance == Decimal("1500.00")
    assert db.query(SalesDocument).filter(SalesDocument.customer_id == cliente.id).count() == 0
    assert db.query(PlatformAuditLog).filter(PlatformAuditLog.action == "CUSTOMER_DEUDA_ANTERIOR_CREATE").count() == 1

    estado = client.get(f"/api/customers/{cliente.id}/statement", headers=_ho(auth_admin, org)).json()
    assert [float(e["amount"]) for e in estado] == [1500.0]


def test_sin_nota_la_descripcion_es_solo_deuda_anterior(client, db, org, auth_admin):
    cliente = _cliente(db, org)
    d = _cargar(client, _ho(auth_admin, org), cliente, "80", _hoy_mx()).json()
    assert d["entry"]["description"] == "Deuda anterior"


def test_la_cajera_no_puede_cargar_deuda_anterior(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, _, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    assert _cargar(client, h, cliente, "100", _hoy_mx()).status_code == 403


def test_monto_y_fecha_invalidos_se_rechazan(client, db, org, auth_admin):
    cliente = _cliente(db, org)
    h = _ho(auth_admin, org)
    assert _cargar(client, h, cliente, "0", _hoy_mx()).status_code == 422
    assert _cargar(client, h, cliente, "-5", _hoy_mx()).status_code == 422
    r = _cargar(client, h, cliente, "100", _hoy_mx() + timedelta(days=2))
    assert r.status_code == 422
    assert "futuro" in r.json()["detail"]
    db.refresh(cliente)
    assert cliente.current_balance == Decimal("0.00")


def test_no_es_venta_ni_fiado_y_entra_a_cobranza_por_su_antiguedad(client, db, org, auth_admin):
    cliente = _cliente(db, org, "Beth")
    _cargar(client, _ho(auth_admin, org), cliente, "900", _hoy_mx() - timedelta(days=75))

    ambito = mv.Ambito(organization_id=org.id, branch_id=None, toda_la_org=True)
    periodo = mv.Periodo(_hoy_mx() - timedelta(days=120), _hoy_mx())
    res = mv.resumen(db, ambito, periodo)
    assert (res.bruta, res.neta, res.tickets) == (0.0, 0.0, 0)
    assert mv.fiado(db, ambito, periodo) == 0.0

    r = client.get("/api/customers/cobranza", headers=_ho(auth_admin, org))
    assert r.status_code == 200, r.text
    fila = next(i for i in r.json()["items"] if i["id"] == cliente.id)
    assert float(fila["balance"]) == 900.0
    assert float(fila["antiguedad"]["61_90"]) == 900.0
    assert fila["dias"] >= 74 and fila["tickets_abiertos"] == 0


def test_el_abono_libre_cubre_primero_la_deuda_anterior(
    client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin, products_setup
):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku)          # ticket de hoy por 100
    _cargar(client, _ho(auth_admin, org), cliente, "300", _hoy_mx() - timedelta(days=60))

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "350", "method": "CASH"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert float(d["deuda_anterior"]) == 300.0
    assert [(x["sales_document_id"], float(x["amount"]), x["paid_in_full"]) for x in d["applied"]] == [
        (venta["sale_id"], 50.0, False)]
    assert float(d["unapplied"]) == 0.0
    assert float(d["customer_balance_after"]) == 50.0
    assert db.query(SalesDocument).get(venta["sale_id"]).status == DocumentStatus.PENDING

    # Lo que queda es el ticket de hoy: la antigüedad ya no reporta nada vencido.
    antig = antiguedad_por_cargo(asientos_del_cliente(db, org_id=org.id, customer_id=cliente.id))
    assert antig["current"] == Decimal("50") and antig["31_60"] == 0 and antig["61_90"] == 0


def test_un_abono_menor_baja_solo_la_deuda_anterior(client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin, products_setup):
    h, _, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _cargar(client, _ho(auth_admin, org), cliente, "300", _hoy_mx() - timedelta(days=10))
    d = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "120", "method": "CASH"}, headers=h).json()
    assert (float(d["deuda_anterior"]), float(d["unapplied"]), d["applied"]) == (120.0, 0.0, [])
    assert float(d["customer_balance_after"]) == 180.0
    # El recibo reimpreso dice lo mismo.
    from app.models.sales import Payment
    from app.modules.customers.services import detalle_del_abono
    pago = db.query(Payment).filter(Payment.id == d["payment_id"]).one()
    det = detalle_del_abono(db, org_id=org.id, pago=pago)
    assert (det["deuda_anterior"], det["unapplied"]) == (Decimal("120"), Decimal("0"))


def test_quitar_la_deuda_sin_abonos_la_borra(client, db, org, auth_admin):
    cliente = _cliente(db, org)
    h = _ho(auth_admin, org)
    entry = _cargar(client, h, cliente, "500", _hoy_mx() - timedelta(days=5)).json()["entry"]
    r = client.delete(f"/api/customers/{cliente.id}/deuda-anterior/{entry['id']}", headers=h)
    assert r.status_code == 200, r.text
    assert float(r.json()["customer_balance"]) == 0.0
    assert db.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.id == entry["id"]).count() == 0
    assert db.query(PlatformAuditLog).filter(PlatformAuditLog.action == "CUSTOMER_DEUDA_ANTERIOR_DELETE").count() == 1


def test_no_se_quita_si_ya_recibio_abonos(client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin, products_setup):
    h, _, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    ho = _ho(auth_admin, org)
    entry = _cargar(client, ho, cliente, "500", _hoy_mx() - timedelta(days=5)).json()["entry"]
    client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "100", "method": "CASH"}, headers=h)
    r = client.delete(f"/api/customers/{cliente.id}/deuda-anterior/{entry['id']}", headers=ho)
    assert r.status_code == 409, r.text
    db.refresh(cliente)
    assert cliente.current_balance == Decimal("400.00")


def test_solo_se_quita_una_deuda_anterior(client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    cargo = db.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.customer_id == cliente.id).one()
    r = client.delete(f"/api/customers/{cliente.id}/deuda-anterior/{cargo.id}", headers=_ho(auth_admin, org))
    assert r.status_code == 404
    assert client.delete(f"/api/customers/{cliente.id}/deuda-anterior/{cargo.id}", headers=h).status_code == 403


def test_el_recibo_dice_cuanto_fue_a_la_deuda_anterior():
    p = PosPrinter("x", paper_width_mm=58)
    raw = p.build_abono_bytes(
        organization=None, branch=None, cashier="denisse", customer_name="Ana",
        amount=120.0, method="CASH", reference=None, applied=[], unapplied=0.0,
        balance_before=300.0, balance_after=180.0, deuda_anterior=120.0,
        received_at=datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc), folio="AB-00000001",
    )
    assert b"APLICADO A:" in raw and b"Deuda anterior" in raw
