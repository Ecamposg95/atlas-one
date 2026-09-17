"""La venta cobra la comision de tarjeta, la congela y NO la mete en total_amount.

`create_sale` es el motor ATS-critico: la mitad de este archivo son pruebas de
NEUTRALIDAD -- con el porcentaje en 0, o sin pago con tarjeta, todo tiene que
quedar exactamente como estaba."""
from decimal import Decimal

from app.models.sales import Payment, PaymentMethod, SalesDocument
from conftest import _make_product
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _preparar(db, org, branch, cajero, precio="1000.00", pct=None):
    _habilitar_pos(db, org)
    _make_product(db, org, "Mercancia", "COM-01", Decimal(precio), [(branch.id, True)])
    _abrir_caja(db, org, branch, cajero)
    if pct is not None:
        org.card_surcharge_pct = Decimal(pct)
    db.commit()


def _vender(client, org, auth, pagos):
    return client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "COM-01", "quantity": 1}],
        "payments": pagos,
    }, headers={**auth, "X-Organization-ID": str(org.id)})


def _doc(db, sale_id):
    return db.query(SalesDocument).filter(SalesDocument.id == sale_id).one()


class TestNeutralidad:
    def test_sin_porcentaje_nada_cambia(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a)
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "1000.00"}])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["total"] == 1000.0
        assert cuerpo["paid"] == 1000.0
        assert cuerpo["change"] == 0.0
        assert cuerpo["card_surcharge_amount"] == 0.0
        assert cuerpo["card_surcharge_pct"] is None

        venta = _doc(db, cuerpo["sale_id"])
        assert venta.total_amount == Decimal("1000.00")
        assert venta.card_surcharge_amount == Decimal("0.00")
        assert venta.card_surcharge_pct is None

    def test_sin_pago_con_tarjeta_no_hay_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CASH", "amount": "1000.00"}])
        assert r.status_code in (200, 201), r.text
        assert r.json()["card_surcharge_amount"] == 0.0
        assert _doc(db, r.json()["sale_id"]).card_surcharge_amount == Decimal("0.00")

    def test_el_efectivo_sigue_dando_cambio_igual(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Con comision configurada pero sin tarjeta, el billete grande de
        # siempre tiene que devolver exactamente el mismo cambio de siempre.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CASH", "amount": "1200.00"}])
        assert r.status_code in (200, 201), r.text
        assert r.json()["change"] == 200.0
        assert _doc(db, r.json()["sale_id"]).change_given == Decimal("200.00")


class TestCobro:
    def test_cien_por_ciento_tarjeta(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Ejemplo A del diseño.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "1035.00"}])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["card_surcharge_amount"] == 35.0
        assert cuerpo["card_surcharge_pct"] == 3.5
        # `total` es SOLO mercancia: la comision va aparte y no infla el
        # reporte de ingresos.
        assert cuerpo["total"] == 1000.0
        assert cuerpo["paid"] == 1035.0
        assert cuerpo["change"] == 0.0

        venta = _doc(db, cuerpo["sale_id"])
        assert venta.total_amount == Decimal("1000.00")
        assert venta.card_surcharge_amount == Decimal("35.00")
        assert venta.card_surcharge_pct == Decimal("3.50")

        # El Payment de tarjeta lleva la comision DENTRO: es lo que paso por la
        # terminal y es lo que el corte por metodo tiene que reflejar.
        pago = db.query(Payment).filter(Payment.sales_document_id == venta.id).one()
        assert pago.method == PaymentMethod.CARD
        assert pago.amount == Decimal("1035.00")

    def test_pagar_solo_la_mercancia_es_422(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # El cajero NO puede quitar la comision: si cobra 1000 en vez de 1035,
        # el checkout lo rechaza con el importe correcto en el mensaje.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "1000.00"}])
        assert r.status_code == 422, r.text
        assert "1035.00" in r.json()["detail"]

    def test_mixto_solo_cobra_la_parte_de_tarjeta(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Ejemplo B del diseño: $400 en efectivo, el resto con tarjeta.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "400.00"},
            {"method": "CARD", "amount": "621.00"},
        ])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["card_surcharge_amount"] == 21.0
        assert cuerpo["total"] == 1000.0
        assert cuerpo["paid"] == 1021.0
        # El cambio es CERO: si `cash_needed` no incluyera la comision, aqui
        # saldrian 21.00 de cambio -- justo lo que se le acaba de cobrar.
        assert cuerpo["change"] == 0.0
        assert _doc(db, cuerpo["sale_id"]).change_given == Decimal("0.00")

    def test_mixto_con_cambio_en_efectivo(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Ejemplo C del diseño: el cliente da un billete de 600 y la tarjeta
        # quedo en 517.50. Comision sobre base 400 = 14.00.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "600.00"},
            {"method": "CARD", "amount": "517.50"},
        ])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["card_surcharge_amount"] == 14.0
        assert cuerpo["paid"] == 1117.5
        assert cuerpo["change"] == 103.5
        # 1117.50 - 103.50 = 1014.00 = 1000.00 de mercancia + 14.00 de comision
        assert cuerpo["paid"] - cuerpo["change"] == cuerpo["total"] + cuerpo["card_surcharge_amount"]

    def test_el_efectivo_que_cubre_todo_no_genera_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "1200.00"},
            {"method": "CARD", "amount": "50.00"},
        ])
        assert r.status_code in (200, 201), r.text
        assert r.json()["card_surcharge_amount"] == 0.0

    def test_la_transferencia_no_causa_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "TRANSFER", "amount": "1000.00"}])
        assert r.status_code in (200, 201), r.text
        assert r.json()["card_surcharge_amount"] == 0.0


class TestIdempotencia:
    def test_el_reenvio_devuelve_la_comision_congelada_sin_duplicar(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        # La comision se LEE del documento, nunca se recalcula: si el POS
        # reintenta el cobro, el cliente no puede acabar pagandola dos veces.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        cuerpo_venta = {
            "doc_type": "ORDER",
            "client_uuid": "reintento-comision-1",
            "items": [{"sku": "COM-01", "quantity": 1}],
            "payments": [{"method": "CARD", "amount": "1035.00"}],
        }
        cab = {**auth_cajero_a, "X-Organization-ID": str(org.id)}

        primera = client.post("/api/sales/", json=cuerpo_venta, headers=cab)
        assert primera.status_code in (200, 201), primera.text

        segunda = client.post("/api/sales/", json=cuerpo_venta, headers=cab)
        assert segunda.status_code in (200, 201), segunda.text
        assert segunda.json()["duplicate_ignored"] is True
        assert segunda.json()["sale_id"] == primera.json()["sale_id"]
        assert segunda.json()["card_surcharge_amount"] == 35.0
        assert segunda.json()["card_surcharge_pct"] == 3.5

        venta_id = primera.json()["sale_id"]
        assert db.query(Payment).filter(Payment.sales_document_id == venta_id).count() == 1
        assert _doc(db, venta_id).card_surcharge_amount == Decimal("35.00")
