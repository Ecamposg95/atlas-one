"""Reimpresion de tickets: PIN de supervisor y ventas canceladas.

Hallazgo §6 de docs/audits/2026-09-01-comparacion-atlas-rmazh.md: cualquiera
podia reimprimir un ticket sin autorizacion. Es un control anti-fraude clasico
—sin el, un cajero reimprime un ticket y lo entrega como comprobante de una
venta que no ocurrio—. Y el hallazgo C-18: una venta CANCELLED seguia
devolviendo su ticket limpio, que es justo el insumo de ese fraude.

Aqui no hay columna de PIN: el "PIN" es la contrasena de un usuario con rol
gerencial de la misma organizacion, validada con la misma funcion que el login
(app/core/security/passwords.py::verify_pin). No se guarda nada nuevo.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.sales import DocumentStatus, DocumentType, Payment, PaymentMethod, SalesDocument, SalesLineItem


@pytest.fixture(autouse=True)
def _sin_intentos_previos():
    """El contador anti fuerza-bruta vive en memoria del proceso."""
    from app.services import reprint_auth
    reprint_auth._INTENTOS_FALLIDOS.clear()
    yield
    reprint_auth._INTENTOS_FALLIDOS.clear()


def _crear_venta(db, org, branch, vendedor, variante, *, hace_minutos=120, folio=1):
    doc = SalesDocument(
        seller_id=vendedor.id, branch_id=branch.id, organization_id=org.id,
        doc_type=DocumentType.INVOICE, status=DocumentStatus.PAID,
        subtotal=Decimal("100.00"), tax_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"), series="A", folio=folio,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=hace_minutos),
    )
    db.add(doc); db.flush()
    db.add(SalesLineItem(
        document_id=doc.id, variant_id=variante.id, description="Producto A",
        quantity=1, unit_price=Decimal("100.00"), total_line=Decimal("100.00"),
        organization_id=org.id,
    ))
    db.add(Payment(
        sales_document_id=doc.id, method=PaymentMethod.CASH,
        amount=Decimal("100.00"), organization_id=org.id,
    ))
    db.flush()
    return doc


@pytest.fixture()
def venta(db, org, branch_a, cajero_a, products_setup):
    """Venta de hace dos horas: fuera de la ventana de "venta propia reciente",
    asi que el gate de autorizacion aplica de lleno."""
    _, variante = products_setup["product_a"]
    return _crear_venta(db, org, branch_a, cajero_a, variante)



def _reimprimir(client, auth, org, venta_id, pin=None, ruta="reprint-ticket"):
    return client.post(
        f"/api/printer/{ruta}/{venta_id}",
        json={"pin": pin} if pin is not None else None,
        headers={**auth, "X-Organization-ID": str(org.id)},
    )


class TestGateDePin:
    def test_un_cajero_sin_pin_no_reimprime(self, client, org, venta, auth_cajero_a):
        resp = _reimprimir(client, auth_cajero_a, org, venta.id)
        # 428 y no 401: el cajero SI esta autenticado; lo que falta es una
        # autorizacion puntual. Un 401 dispararia el cierre de sesion global.
        assert resp.status_code == 428, resp.text

    def test_un_cajero_con_el_pin_de_su_gerente_reimprime(self, client, org, venta, auth_cajero_a, gerente_a):
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234")
        assert resp.status_code == 200, resp.text
        assert resp.json()["content_base64"]

    def test_un_pin_incorrecto_se_rechaza(self, client, org, venta, auth_cajero_a, gerente_a):
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="no-es")
        assert resp.status_code == 403, resp.text
        # El `detail` va estructurado: el otro 403 del endpoint ("Sin acceso a
        # esta venta") es texto plano, y el front tiene que distinguirlos para
        # decidir si deja reintentar en el modal.
        assert resp.json()["detail"]["code"] == "PIN_INCORRECTO"

    def test_un_rechazo_de_acceso_no_lleva_el_codigo_del_pin(
        self, client, db, org, branch_b, venta, auth_cajero_a, gerente_a
    ):
        """El endpoint tiene otros rechazos (sucursal ajena, venta de otra org)
        que NO son "PIN incorrecto": ninguno debe traer el codigo, o el modal
        del front se quedaria abierto pidiendo un PIN que no arregla nada."""
        venta.branch_id = branch_b.id
        db.flush()
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234")
        assert resp.status_code == 404, resp.text  # no filtra que la venta existe
        assert resp.json()["detail"] != {"code": "PIN_INCORRECTO", "message": "PIN incorrecto"}

    def test_prefiere_a_un_supervisor_de_la_misma_sucursal(
        self, client, db, org, branch_a, venta, auth_cajero_a, gerente_a
    ):
        """Con gerente en la sucursal, no se prueba el PIN contra los de las
        demas: cada candidato cuesta un bcrypt."""
        from app.services.reprint_auth import _supervisores_activos
        candidatos = _supervisores_activos(db, org.id, branch_a.id)
        assert [u.id for u in candidatos] == [gerente_a.id]

    def test_sin_supervisor_en_la_sucursal_cae_a_la_organizacion(
        self, client, db, org, branch_a, hq_branch, admin_user, products_setup, auth_cajero_a, cajero_a
    ):
        """El dueno/administrador suele estar en HQ, no en la sucursal que
        vende: si se filtrara solo por sucursal, nadie podria autorizar."""
        _, variante = products_setup["product_a"]
        propia = _crear_venta(db, org, branch_a, cajero_a, variante, folio=5)
        resp = _reimprimir(client, auth_cajero_a, org, propia.id, pin="test1234")
        assert resp.status_code == 200, resp.text

    def test_un_rol_gerencial_no_necesita_pin(self, client, org, venta, auth_gerente_a):
        resp = _reimprimir(client, auth_gerente_a, org, venta.id)
        assert resp.status_code == 200, resp.text

    def test_la_contrasena_de_otro_cajero_no_sirve_de_pin(self, client, db, org, branch_a, venta, auth_cajero_a):
        """Solo autoriza un rol gerencial: la contrasena de un par no basta."""
        from app.modules.users.models import Role
        from tests.conftest import _make_user
        _make_user(db, org, branch_a, "otro_cajero", Role.CAJERO)
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234")
        assert resp.status_code == 403, resp.text

    def test_el_gerente_de_otra_organizacion_no_autoriza(self, client, db, org, branch_a, venta, auth_cajero_a):
        from app.modules.tenants.models import Organization
        from app.modules.users.models import Role
        from app.models.organization import Branch, BranchType
        from tests.conftest import _make_user

        otra = Organization(name="Otra Org", status="ACTIVE")
        db.add(otra); db.flush()
        sucursal = Branch(name="Otra Suc", branch_type=BranchType.STORE, can_sell=True,
                          is_active=True, organization_id=otra.id)
        db.add(sucursal); db.flush()
        _make_user(db, otra, sucursal, "gerente_ajeno", Role.GERENTE)

        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234")
        assert resp.status_code == 403, resp.text


class TestVentaPropiaReciente:
    """El fraude es entregar un ticket viejo o ajeno como comprobante de una
    venta que no ocurrio. Volver a sacar el de la venta que uno acaba de cobrar
    es el papel atascado: el POS lo hace con un boton y no puede pedir PIN."""

    def test_el_cajero_reimprime_su_venta_del_momento_sin_pin(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        _, variante = products_setup["product_a"]
        reciente = _crear_venta(db, org, branch_a, cajero_a, variante, hace_minutos=2, folio=9)
        assert _reimprimir(client, auth_cajero_a, org, reciente.id).status_code == 200

    def test_pasada_la_ventana_ya_pide_pin(self, client, org, venta, auth_cajero_a):
        # `venta` es de hace dos horas.
        assert _reimprimir(client, auth_cajero_a, org, venta.id).status_code == 428

    def test_la_venta_reciente_de_otro_cajero_pide_pin(
        self, client, db, org, branch_a, auth_cajero_a, gerente_a, products_setup
    ):
        _, variante = products_setup["product_a"]
        ajena = _crear_venta(db, org, branch_a, gerente_a, variante, hace_minutos=2, folio=8)
        assert _reimprimir(client, auth_cajero_a, org, ajena.id).status_code == 428


class TestImpresionOriginal:
    """`print-ticket` acepta un order_id cualquiera: sin el mismo gate, el
    ticket que la reimpresion protege quedaria a un POST de distancia."""

    def _imprimir(self, client, auth, org, venta_id, pin=None):
        cuerpo = {"order_id": venta_id}
        if pin is not None:
            cuerpo["pin"] = pin
        return client.post(
            "/api/printer/print-ticket",
            json=cuerpo,
            headers={**auth, "X-Organization-ID": str(org.id)},
        )

    def test_el_ticket_de_una_venta_vieja_pide_pin(self, client, org, venta, auth_cajero_a):
        assert self._imprimir(client, auth_cajero_a, org, venta.id).status_code == 428

    def test_con_pin_de_supervisor_se_emite(self, client, org, venta, auth_cajero_a, gerente_a):
        assert self._imprimir(client, auth_cajero_a, org, venta.id, pin="test1234").status_code == 200

    def test_el_ticket_de_la_venta_recien_cobrada_se_emite_solo(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        """El flujo normal del POS tras cobrar: no puede pedir nada."""
        _, variante = products_setup["product_a"]
        reciente = _crear_venta(db, org, branch_a, cajero_a, variante, hace_minutos=0, folio=7)
        assert self._imprimir(client, auth_cajero_a, org, reciente.id).status_code == 200

    def test_una_venta_cancelada_no_emite_ticket(self, client, db, org, venta, auth_gerente_a):
        venta.status = DocumentStatus.CANCELLED
        db.flush()
        assert self._imprimir(client, auth_gerente_a, org, venta.id).status_code == 409


class TestFuerzaBruta:
    def test_tres_fallos_bloquean_la_reimpresion(self, client, org, venta, auth_cajero_a, gerente_a):
        for _ in range(3):
            assert _reimprimir(client, auth_cajero_a, org, venta.id, pin="mal").status_code == 403
        bloqueado = _reimprimir(client, auth_cajero_a, org, venta.id, pin="mal")
        assert bloqueado.status_code == 423, bloqueado.text

    def test_el_bloqueo_ignora_incluso_el_pin_correcto(self, client, org, venta, auth_cajero_a, gerente_a):
        for _ in range(3):
            _reimprimir(client, auth_cajero_a, org, venta.id, pin="mal")
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234")
        assert resp.status_code == 423, resp.text

    def test_un_acierto_limpia_el_contador(self, client, org, venta, auth_cajero_a, gerente_a):
        _reimprimir(client, auth_cajero_a, org, venta.id, pin="mal")
        _reimprimir(client, auth_cajero_a, org, venta.id, pin="mal")
        assert _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234").status_code == 200
        # Con el contador limpio vuelve a haber margen para tres fallos.
        for _ in range(3):
            assert _reimprimir(client, auth_cajero_a, org, venta.id, pin="mal").status_code == 403


class TestVentaCancelada:
    """C-18: cancelar la venta borraba el cobro pero no el comprobante."""

    def test_no_se_reimprime_una_venta_cancelada(self, client, db, org, venta, auth_gerente_a):
        venta.status = DocumentStatus.CANCELLED
        db.flush()
        resp = _reimprimir(client, auth_gerente_a, org, venta.id)
        assert resp.status_code == 409, resp.text
        assert "cancelada" in resp.json()["detail"].lower()

    def test_tampoco_con_pin_de_supervisor(self, client, db, org, venta, auth_cajero_a, gerente_a):
        venta.status = DocumentStatus.CANCELLED
        db.flush()
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234")
        assert resp.status_code == 409, resp.text

    def test_tampoco_por_el_ticket_actualizado_tras_devolucion(self, client, db, org, venta, auth_gerente_a):
        venta.status = DocumentStatus.CANCELLED
        db.flush()
        resp = _reimprimir(client, auth_gerente_a, org, venta.id, ruta="reprint-refunded")
        assert resp.status_code == 409, resp.text

    def test_una_venta_pagada_si_se_reimprime(self, client, org, venta, auth_gerente_a):
        assert _reimprimir(client, auth_gerente_a, org, venta.id).status_code == 200


class TestTicketTrasDevolucion:
    def test_tambien_exige_pin(self, client, org, venta, auth_cajero_a):
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, ruta="reprint-refunded")
        assert resp.status_code == 428, resp.text

    def test_lo_emite_con_pin_valido(self, client, org, venta, auth_cajero_a, gerente_a):
        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234", ruta="reprint-refunded")
        assert resp.status_code == 200, resp.text


class TestRastroDeAuditoria:
    """El PrintJob guarda los bytes y la impresora, no quien pidio el ticket ni
    quien lo autorizo. Sin esta fila el control del PIN no se puede investigar."""

    def _filas(self, db, org, evento):
        from app.models.cash_audit import CashAuditLog
        return (
            db.query(CashAuditLog)
            .filter(CashAuditLog.organization_id == org.id,
                    CashAuditLog.event_type == evento)
            .all()
        )

    def test_la_reimpresion_con_pin_deja_quien_autorizo(
        self, client, db, org, branch_a, venta, auth_cajero_a, cajero_a, gerente_a
    ):
        from app.models.cash_audit import CashAuditEvent
        assert _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234").status_code == 200

        filas = self._filas(db, org, CashAuditEvent.TICKET_REPRINTED)
        assert len(filas) == 1
        fila = filas[0]
        assert fila.user_id == cajero_a.id
        assert fila.branch_id == branch_a.id
        assert fila.related_id == str(venta.id)
        assert fila.payload_json["via"] == "pin"
        assert fila.payload_json["authorized_by_user_id"] == gerente_a.id

    def test_el_intento_fallido_queda_registrado(
        self, client, db, org, venta, auth_cajero_a, cajero_a, gerente_a
    ):
        from app.models.cash_audit import CashAuditEvent
        assert _reimprimir(client, auth_cajero_a, org, venta.id, pin="mal").status_code == 403

        filas = self._filas(db, org, CashAuditEvent.REPRINT_PIN_FAILED)
        assert len(filas) == 1
        assert filas[0].user_id == cajero_a.id
        assert filas[0].related_id == str(venta.id)
        assert filas[0].payload_json["authorized_by_user_id"] is None

    def test_el_rol_gerencial_tambien_deja_rastro(self, client, db, org, venta, auth_gerente_a, gerente_a):
        from app.models.cash_audit import CashAuditEvent
        assert _reimprimir(client, auth_gerente_a, org, venta.id).status_code == 200

        filas = self._filas(db, org, CashAuditEvent.TICKET_REPRINTED)
        assert len(filas) == 1
        assert filas[0].user_id == gerente_a.id
        assert filas[0].payload_json["via"] == "rol_gerencial"

    def test_la_impresion_normal_del_pos_no_ensucia_la_bitacora(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
    ):
        """Una fila por cada venta cobrada seria ruido, no auditoria."""
        from app.models.cash_audit import CashAuditEvent
        _, variante = products_setup["product_a"]
        reciente = _crear_venta(db, org, branch_a, cajero_a, variante, hace_minutos=1, folio=6)
        assert _reimprimir(client, auth_cajero_a, org, reciente.id).status_code == 200
        assert self._filas(db, org, CashAuditEvent.TICKET_REPRINTED) == []
