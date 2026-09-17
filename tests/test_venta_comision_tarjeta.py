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

    def test_el_mensaje_de_pago_insuficiente_no_cambia_sin_comision(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        # Sin comision el 422 tiene que ser byte a byte el de siempre: hay POS
        # y bitacoras alla afuera que leen este texto.
        _preparar(db, org, branch_a, cajero_a)
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "900.00"}])
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Pagos insuficientes: recibido 900.00 vs total 1000.00"

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
        # El mensaje nombra la comision: si solo dijera "total 1035.00" el
        # cajero creeria que el sistema le esta inventando $35 al carrito.
        assert r.json()["detail"] == (
            "Pagos insuficientes: recibido 1000.00 vs total 1035.00 "
            "(incluye comisión tarjeta 35.00)"
        )

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


    def test_el_sobrepago_anomalo_sigue_siendo_422_con_comision(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        # El guard de x10 se mide contra el total CON comision, pero un dedo
        # gordo de $20,000 sobre una venta de $1,000 tiene que seguir rebotando.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "20000.00"}])
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Sobrepago anómalo, revisa el monto"


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


class TestVentaPendienteQueSeCompleta:
    """La OTRA ruta que cobra: un documento PENDING que se termina de pagar.

    `create_sale` reutiliza el documento cuando le llega el mismo `id`: borra
    los pagos viejos y vuelve a calcularlo todo. Ahi la comision se cobra por
    PRIMERA vez sobre una venta que ya tiene folio, y es exactamente el caso de
    un credito que el cliente viene a liquidar con tarjeta.
    """

    VENTA_ID = "11111111-2222-3333-4444-555555555555"

    def _postear(self, client, org, auth, pagos):
        return client.post("/api/sales/", json={
            "id": self.VENTA_ID,
            "doc_type": "ORDER",
            "items": [{"sku": "COM-01", "quantity": 1}],
            "payments": pagos,
        }, headers={**auth, "X-Organization-ID": str(org.id)})

    def test_el_pendiente_que_se_liquida_con_tarjeta_cobra_la_comision(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        _preparar(db, org, branch_a, cajero_a, pct="3.5")

        # 1) Se abre sin pagos: queda PENDING y sin comision, porque todavia no
        #    hay ninguna tarjeta de por medio.
        abierta = self._postear(client, org, auth_cajero_a, [])
        assert abierta.status_code in (200, 201), abierta.text
        assert abierta.json()["card_surcharge_amount"] == 0.0
        assert abierta.json()["card_surcharge_pct"] is None
        db.expire_all()
        assert _doc(db, self.VENTA_ID).card_surcharge_amount == Decimal("0.00")

        # 2) El cliente vuelve y paga con tarjeta: ahi si se cobra.
        liquidada = self._postear(
            client, org, auth_cajero_a, [{"method": "CARD", "amount": "1035.00"}]
        )
        assert liquidada.status_code in (200, 201), liquidada.text
        cuerpo = liquidada.json()
        assert cuerpo["sale_id"] == self.VENTA_ID
        assert cuerpo["card_surcharge_amount"] == 35.0
        assert cuerpo["card_surcharge_pct"] == 3.5
        assert cuerpo["total"] == 1000.0
        assert cuerpo["credit_debt"] == 0.0

        db.expire_all()
        venta = _doc(db, self.VENTA_ID)
        # La comision NO infla el total: sigue siendo la mercancia de siempre.
        assert venta.total_amount == Decimal("1000.00")
        assert venta.card_surcharge_amount == Decimal("35.00")
        assert venta.card_surcharge_pct == Decimal("3.50")
        # Un solo pago: el de la primera pasada se borro, no se acumulo.
        pagos = db.query(Payment).filter(
            Payment.sales_document_id == self.VENTA_ID
        ).all()
        assert len(pagos) == 1
        assert pagos[0].method == PaymentMethod.CARD
        assert pagos[0].amount == Decimal("1035.00")

    def test_el_pendiente_que_se_liquida_en_efectivo_no_cobra_comision(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        # Neutralidad en la misma ruta: sin tarjeta, el documento reutilizado
        # queda igual que antes de la funcion.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        assert self._postear(client, org, auth_cajero_a, []).status_code in (200, 201)
        r = self._postear(client, org, auth_cajero_a, [{"method": "CASH", "amount": "1000.00"}])
        assert r.status_code in (200, 201), r.text
        assert r.json()["card_surcharge_amount"] == 0.0
        assert r.json()["change"] == 0.0
        db.expire_all()
        venta = _doc(db, self.VENTA_ID)
        assert venta.card_surcharge_amount == Decimal("0.00")
        assert venta.card_surcharge_pct is None
