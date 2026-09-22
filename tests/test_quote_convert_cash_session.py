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
