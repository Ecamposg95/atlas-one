"""Un abono a cuenta de un cliente no pertenece a ninguna venta.

Regresión: la migración "Track 1" de `scripts/railway_init.py` ponía
`payments.sales_document_id` en NOT NULL para que ningún pago quedara suelto.
Iba demasiado lejos: el modelo documenta que un abono a cuenta va sin venta, así
que `POST /api/customers/{id}/pay` sin `sales_document_id` reventaba con 500
(NotNullViolation) en Postgres y un saldo a favor no se podía registrar.

La garantía original —ningún pago sin dueño— se conserva con un CHECK: venta o
cliente, al menos uno. Aquí se prueba el camino del endpoint; el CHECK vive en
la migración y solo aplica en Postgres.
"""
import pytest

from app.models.sales import Payment


def _crear_cliente(client, auth_admin, nombre="Rafa"):
    r = client.post("/api/customers/", json={"name": nombre, "has_credit": True}, headers=auth_admin)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_abono_sin_venta_deja_saldo_a_favor(client, auth_admin, db):
    cid = _crear_cliente(client, auth_admin)

    r = client.post(
        f"/api/customers/{cid}/pay",
        json={"amount": 200, "method": "OTHER", "reference": "Resto de la chamarra a cuenta"},
        headers=auth_admin,
    )
    assert r.status_code == 200, r.text

    pago = db.query(Payment).filter(Payment.customer_id == cid).first()
    assert pago is not None, "el abono debe quedar registrado"
    assert pago.sales_document_id is None, "un abono a cuenta no pertenece a una venta"
    assert float(pago.amount) == 200.0

    ficha = client.get(f"/api/customers/{cid}", headers=auth_admin).json()
    assert float(ficha["current_balance"]) < 0, "el abono sin deuda deja saldo A FAVOR del cliente"


def test_el_modelo_permite_pago_sin_venta():
    """El candado vive en la base (CHECK), no en una columna NOT NULL."""
    columna = Payment.__table__.c.sales_document_id
    assert columna.nullable is True, (
        "payments.sales_document_id debe aceptar NULL: es lo que distingue "
        "un abono a cuenta de un pago de venta"
    )
