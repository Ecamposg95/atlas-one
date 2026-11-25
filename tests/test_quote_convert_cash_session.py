"""Convertir una cotizacion en venta no puede saltarse el control de caja.

`convert_quote_to_sale` no comprobaba sesion, su payment_method por omision era
"CASH" y nunca asignaba cash_session_id: un bypass completo del guard, abierto
a cualquier rol.
"""
from decimal import Decimal

import pytest

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, SalesDocument


def _habilitar_modulo(db, org, key):
    """El router de cotizaciones exige el modulo `quotes` habilitado (gate a
    nivel de router, ver app/routers/quotes.py:24). CAJERO no tiene el bypass
    de ADMINISTRADOR/DUEÑO, asi que sin esto el POST devuelve 403 antes de
    llegar al guard de caja que estas pruebas verifican."""
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key)); db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == key).first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _crear_cotizacion(client, headers, sku):
    resp = client.post("/api/quotes/", json={
        "doc_type": "QUOTE",
        "items": [{"sku": sku, "quantity": 1}],
        # SaleCreate (compartido con /api/sales/) exige "payments"; la
        # cotizacion no cobra nada, pero el schema no distingue el caso.
        "payments": [],
    }, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    # create_quote responde {"status": "success", "quote_id": ..., "folio": ...}
    # (no trae la clave "id" — ver app/routers/quotes.py:117).
    return resp.json()["quote_id"]


class TestConversionDeCotizacion:
    def test_efectivo_sin_caja_se_rechaza(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        qid = _crear_cotizacion(client, h, variant.sku)

        resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h)
        assert resp.status_code == 409, (
            f"sin caja abierta no se puede convertir cobrando efectivo: {resp.status_code}"
        )

    def test_con_caja_queda_asociada(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        sesion = _abrir_caja(db, org, branch_a, cajero_a)
        qid = _crear_cotizacion(client, h, variant.sku)

        resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h)
        assert resp.status_code in (200, 201), resp.text
        venta = db.query(SalesDocument).filter(SalesDocument.id == qid).one()
        assert venta.cash_session_id == sesion.id
        # El pago tambien: la atribucion por pago manda sobre la del documento
        # (app/services/cash_reconciliation.py::session_payments_filter), asi
        # que un pago en NULL aqui dependeria del respaldo por documento y se
        # movria de corte si el pedido se reprocesa en otro turno.
        assert [p.cash_session_id for p in venta.payments] == [sesion.id]

    def test_tarjeta_sin_caja_tambien_se_rechaza(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        """Hallazgo ALTA (revisión final): el guard solo exigía caja para
        CASH -- perdió la mitad "todo usuario con sucursal necesita turno"
        que sí tiene create_sale (H-5). Con eso, `payment_method=CARD` sin
        caja abierta producía la venta huérfana (cash_session_id=None) que
        esta rama existe para impedir. Ahora replica el criterio completo:
        se exige caja si el usuario tiene sucursal Y (cobra efectivo O no es
        rol HQ) -- un CAJERO cae en el segundo brazo aunque cobre con
        tarjeta."""
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        qid = _crear_cotizacion(client, h, variant.sku)

        resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CARD", headers=h)
        assert resp.status_code == 409, (
            f"un CAJERO sin caja abierta no debe poder convertir ni cobrando "
            f"con tarjeta: {resp.status_code}"
        )
        venta = db.query(SalesDocument).filter(SalesDocument.id == qid).one()
        assert venta.status == DocumentStatus.PENDING, (
            "el rechazo debe evitar la conversion; la cotizacion no debe quedar PAID"
        )
        assert venta.cash_session_id is None

    def test_el_metodo_de_pago_es_obligatorio(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        """Un default de CASH convierte en efectivo por accidente."""
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        qid = _crear_cotizacion(client, h, variant.sku)

        resp = client.post(f"/api/quotes/{qid}/convert-to-sale", headers=h)
        assert resp.status_code == 422, "sin payment_method explicito debe ser error de validacion"


class TestConversionEmiteElEvento:
    """Convertir un pedido en venta encola `SalesDocumentCreated` en la misma
    transaccion, igual que `create_sale`. Sin el evento no se descontaban los
    insumos de receta ni se revisaba el reabasto."""

    @staticmethod
    def _eventos(db, qid):
        from app.models.event_outbox import EventOutbox
        return [
            e for e in db.query(EventOutbox).filter(
                EventOutbox.event_type == "SalesDocumentCreated").all()
            if e.payload.get("sales_document_id") == qid
        ]

    def test_la_conversion_encola_el_evento_con_sus_partidas(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        from app.models.event_outbox import OutboxStatus
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        _abrir_caja(db, org, branch_a, cajero_a)
        qid = _crear_cotizacion(client, h, variant.sku)
        assert self._eventos(db, qid) == [], "cotizar no es vender: no emite"

        resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h)
        assert resp.status_code in (200, 201), resp.text

        eventos = self._eventos(db, qid)
        assert len(eventos) == 1
        assert eventos[0].status == OutboxStatus.PENDING
        assert eventos[0].payload["items"] == [
            {"variant_id": variant.id, "quantity": 1.0, "sku": variant.sku}]

    def test_una_conversion_rechazada_no_deja_evento(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        qid = _crear_cotizacion(client, h, variant.sku)

        # Sin caja abierta: 409 y nada encolado.
        resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h)
        assert resp.status_code == 409
        assert self._eventos(db, qid) == []

    def test_convertir_dos_veces_no_emite_dos_eventos(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        _abrir_caja(db, org, branch_a, cajero_a)
        qid = _crear_cotizacion(client, h, variant.sku)
        url = f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH"

        assert client.post(url, headers=h).status_code in (200, 201)
        assert client.post(url, headers=h).status_code == 400  # "Ya fue procesado"
        assert len(self._eventos(db, qid)) == 1

    def test_si_el_outbox_falla_la_conversion_no_se_bloquea(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup, monkeypatch
    ):
        from app.core.events import EventBus
        _habilitar_modulo(db, org, "quotes")
        _, variant = products_setup["product_a"]
        h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
        _abrir_caja(db, org, branch_a, cajero_a)
        qid = _crear_cotizacion(client, h, variant.sku)

        def _revienta(cls, *a, **k):
            raise RuntimeError("outbox caido")
        monkeypatch.setattr(EventBus, "enqueue", classmethod(_revienta))

        resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h)
        assert resp.status_code in (200, 201), resp.text
        db.expire_all()
        venta = db.query(SalesDocument).filter(SalesDocument.id == qid).one()
        assert venta.status == DocumentStatus.PAID
        assert len(venta.payments) == 1
