"""POST /customers/{id}/pay: respuesta con lo aplicado (spec 2026-10-29 §4.2)
y el efectivo sin sucursal se rechaza (§6.1)."""
from decimal import Decimal

from app.crud import returns as crud_returns
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument
from app.schemas.returns import SaleReturnCreate
from tests.cobranza_helpers import _cliente, _escenario, _fiar


def test_el_abono_libre_dice_que_tickets_cubrio(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    a = _fiar(client, h, cliente, variant.sku)
    b = _fiar(client, h, cliente, variant.sku)

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "150", "method": "CASH"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(x["sales_document_id"], float(x["amount"]), x["paid_in_full"]) for x in d["applied"]] == [
        (a["sale_id"], 100.0, True), (b["sale_id"], 50.0, False)]
    assert all(x["folio"].startswith("A-") for x in d["applied"])
    assert float(d["unapplied"]) == 0.0
    assert (float(d["customer_balance_before"]), float(d["customer_balance_after"])) == (200.0, 50.0)
    assert d["method"] == "CASH" and d["received_at"]
    assert len(d["entries"]) == 2 and float(d["entries"][0]["amount"]) == -100.0
    assert db.query(Payment).filter(Payment.id == d["payment_id"]).one().customer_id == cliente.id


def test_lo_que_sobra_queda_a_favor(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    d = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "120", "method": "CARD", "reference": "1234"}, headers=h).json()
    assert float(d["unapplied"]) == 20.0
    assert float(d["customer_balance_after"]) == -20.0
    assert d["reference"] == "1234"


def test_efectivo_sin_sucursal_se_rechaza_y_tarjeta_pasa(
    client, db, org, branch_a, cajero_a, auth_cajero_a, admin_sin_sucursal, auth_admin_sin_sucursal, products_setup
):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    ho = {**auth_admin_sin_sucursal, "X-Organization-ID": str(org.id)}

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "10", "method": "CASH"}, headers=ho)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "Para recibir efectivo elige una sucursal con caja abierta; tarjeta y transferencia sí se pueden registrar"

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "10", "method": "TRANSFER", "reference": "SPEI 1"}, headers=ho)
    assert r.status_code == 200, r.text
    assert db.query(Payment).filter(Payment.id == r.json()["payment_id"]).one().cash_session_id is None


def test_paid_in_full_sale_de_la_deuda_restante_y_no_del_estatus(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """Una fiada con devolución parcial aprobada sigue debiendo lo que falta;
    si no está PENDING (aquí REFUNDED_PARTIAL) el servicio no la marca PAID,
    pero al abonar justo lo que debe el ticket queda saldado y así se dice."""
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    r = client.post("/api/sales/", json={          # 200 sin pagar (el helper fía una pieza)
        "doc_type": "ORDER", "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 2}], "payments": [],
    }, headers=h)
    assert r.status_code in (200, 201), r.text
    venta = r.json()

    d = crud_returns.create_return(
        db=db,
        return_in=SaleReturnCreate(
            sale_id=venta["sale_id"], reason="prueba", total_refunded=Decimal("100.00"),
            refund_method=PaymentMethod.CASH,
            items=[{"variant_id": variant.id, "quantity": 1, "refund_amount": Decimal("100.00")}],
        ),
        user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
    )
    crud_returns.approve_return(db, d.id, supervisor_id=cajero_a.id, organization_id=org.id)
    doc = db.query(SalesDocument).filter(SalesDocument.id == venta["sale_id"]).one()
    doc.status = DocumentStatus.REFUNDED_PARTIAL  # estado con el que el CRM aún lo cobra
    db.commit()
    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("100.00")

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "100", "method": "CASH"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(x["sales_document_id"], float(x["amount"]), x["paid_in_full"]) for x in d["applied"]] == [
        (venta["sale_id"], 100.0, True)]
    assert float(d["unapplied"]) == 0.0
    assert float(d["customer_balance_after"]) == 0.0
