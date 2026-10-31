"""Recibo de abono (spec 2026-10-29 §4.3): bytes ESC/POS con cliente, monto,
tickets aplicados y saldo antes/después; reimprimir es volver a llamar."""
import base64
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.pos_printer import PosPrinter
from tests.cobranza_helpers import _abonar, _cliente, _escenario, _fiar


def _texto(raw: bytes, p: PosPrinter) -> str:
    out = raw
    for k, c in sorted(p.CMD.items(), key=lambda kv: len(kv[1]), reverse=True):
        if k != "LF" and c:
            out = out.replace(c, b"")
    return out.decode("latin-1", "replace")


class _Org:
    name = "ELEVEN FASHION"; legal_name = None; logo_url = None; phone = None


class _Branch:
    name = "Roma"; logo_url = None; phone = None; city = None


def test_los_bytes_del_recibo_traen_todo_lo_que_la_clienta_necesita():
    p = PosPrinter("x", paper_width_mm=58)
    raw = p.build_abono_bytes(
        organization=_Org(), branch=_Branch(), cashier="mirna", customer_name="Ana Pérez",
        amount=150.0, method="CASH", reference=None,
        applied=[{"folio": "A-12", "amount": Decimal("100.00"), "paid_in_full": True},
                 {"folio": "A-15", "amount": Decimal("50.00"), "paid_in_full": False}],
        unapplied=0.0, balance_before=200.0, balance_after=50.0,
        received_at=datetime(2026, 10, 31, 18, 5, tzinfo=timezone.utc), folio="AB-1A2B3C4D",
    )
    t = _texto(raw, p)
    for esperado in ("ELEVEN FASHION", "RECIBO DE ABONO", "AB-1A2B3C4D", "Ana P", "Efectivo",
                     "Ticket A-12 (liquidado)", "Ticket A-15", "Saldo anterior", "Saldo actual"):
        assert esperado in t, f"falta {esperado!r} en:\n{t}"
    lineas = t.split("\n")
    assert next(l for l in lineas if "Saldo actual" in l).rstrip().endswith("$50.00")
    assert "12:05" in t, "la hora se imprime en hora de México"
    assert p.CMD["DRAWER"] not in raw, "un abono no abre el cajón"


def test_el_endpoint_devuelve_el_recibo_en_base64(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org, nombre="Lupita")
    venta = _fiar(client, h, cliente, variant.sku)
    abono = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "40", "method": "CASH"}, headers=h).json()

    r = client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready_to_print"
    t = base64.b64decode(r.json()["content_base64"]).decode("latin-1", "replace")
    assert "RECIBO DE ABONO" in t and "LUPITA" in t.upper()
    assert abono["applied"][0]["folio"] in t
    assert f"AB-{abono['payment_id'][:8].upper()}" in t
    assert "$40.00" in t and "$100.00" in t and "$60.00" in t   # abono, saldo anterior, saldo actual

    # Reimprimir es volver a llamar; no pide PIN.
    assert client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=h).status_code == 200


def test_un_pago_que_no_es_abono_o_no_existe_da_404(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "30.00"}])
    assert client.post(f"/api/printer/print-abono/{uuid.uuid4()}", headers=h).status_code == 404
    from app.models.sales import Payment
    pago_venta = db.query(Payment).filter(Payment.sales_document_id == venta["sale_id"]).one()
    assert client.post(f"/api/printer/print-abono/{pago_venta.id}", headers=h).status_code == 404


def test_el_gerente_puede_imprimir_el_recibo_de_otra_cajera(
    client, db, org, branch_a, cajero_a, auth_cajero_a, gerente_a, auth_gerente_a, products_setup
):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    abono = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "10", "method": "CARD", "reference": "77"}, headers=h).json()
    hg = {**auth_gerente_a, "X-Organization-ID": str(org.id)}
    assert client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=hg).status_code == 200


def _recibo(client, h, payment_id) -> str:
    r = client.post(f"/api/printer/print-abono/{payment_id}", headers=h)
    assert r.status_code == 200, r.text
    return base64.b64decode(r.json()["content_base64"]).decode("latin-1", "replace")


def test_dos_abonos_seguidos_no_se_mezclan_en_el_recibo(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Dos abonos del mismo cliente en el mismo segundo: cada recibo enlaza solo
    sus asientos (por el folio AB-… del asiento), no por ventana de tiempo."""
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    v1 = _fiar(client, h, cliente, variant.sku)                       # 100
    r2 = client.post("/api/sales/", json={
        "doc_type": "ORDER", "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}], "payments": [{"method": "CASH", "amount": "50.00"}],
    }, headers=h)
    assert r2.status_code in (200, 201), r2.text                        # deja 50 más de saldo
    def _linea(t, clave):
        return next(l for l in t.split("\n") if clave in l).rstrip()

    # El recibo se imprime al cobrar: ahí "Saldo anterior" es exacto.
    a1 = _abonar(client, h, cliente, 100)
    t1 = _recibo(client, h, a1["payment_id"])
    a2 = _abonar(client, h, cliente, 50)        # mismo segundo que el anterior
    t2 = _recibo(client, h, a2["payment_id"])
    folio1, folio2 = a1["applied"][0]["folio"], a2["applied"][0]["folio"]
    assert folio1 != folio2 and len(a1["applied"]) == 1 and len(a2["applied"]) == 1

    assert f"Ticket {folio1}" in t1 and f"Ticket {folio2}" not in t1, t1
    assert f"Ticket {folio2}" in t2 and f"Ticket {folio1}" not in t2, t2
    assert _linea(t1, "Saldo anterior").endswith("$150.00"), t1
    assert _linea(t1, "Saldo actual").endswith("$50.00"), t1
    assert _linea(t2, "Saldo anterior").endswith("$50.00"), t2
    assert _linea(t2, "Saldo actual").endswith("$0.00"), t2

    # Reimprimir después, con el otro abono ya hecho, sigue sin mezclarlos.
    r1 = _recibo(client, h, a1["payment_id"])
    assert f"Ticket {folio1}" in r1 and f"Ticket {folio2}" not in r1, r1
    assert _linea(r1, "Abono").endswith("$100.00"), r1


def test_la_cajera_ajena_sin_rol_de_oficina_recibe_403(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    from conftest import _auth_header, _make_user
    from app.models.users import Role
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    abono = _abonar(client, h, cliente, 10)
    otra = _make_user(db, org, branch_a, "cajera_ajena", Role.CAJERO); db.commit()
    ho = {**_auth_header(otra), "X-Organization-ID": str(org.id)}
    assert client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=ho).status_code == 403
    assert client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=h).status_code == 200
