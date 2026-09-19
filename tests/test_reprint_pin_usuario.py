"""PIN de reimpresion PROPIO del usuario, separado de su contrasena.

`tests/test_reprint_pin.py` cubre el gate y el camino historico: el "PIN" que
teclea el cajero es la CONTRASENA de un supervisor. Eso funciona pero obliga al
dueno a compartir su contrasena real con el mostrador.

Aqui se cubre la columna `users.reprint_pin_hash`: un PIN numerico de 4-8
digitos que el panel de Usuarios fija por usuario. Reglas que estos tests
fijan:

  - El hash NUNCA sale en una respuesta; solo el derivado `has_reprint_pin`.
  - El PIN solo autoriza si su dueno es un rol gerencial activo de la org
    (misma condicion que ya aplicaba a la contrasena).
  - La contrasena del supervisor SIGUE sirviendo: el PIN es un primer intento,
    no un reemplazo.
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
    """Venta de hace dos horas: fuera de la ventana de "venta propia reciente"."""
    _, variante = products_setup["product_a"]
    return _crear_venta(db, org, branch_a, cajero_a, variante)


def _reimprimir(client, auth, org, venta_id, pin=None):
    return client.post(
        f"/api/printer/reprint-ticket/{venta_id}",
        json={"pin": pin} if pin is not None else None,
        headers={**auth, "X-Organization-ID": str(org.id)},
    )


def _poner_pin(client, auth, org, user_id, pin):
    return client.put(
        f"/api/users/{user_id}",
        json={"reprint_pin": pin},
        headers={**auth, "X-Organization-ID": str(org.id)},
    )


class TestElPinNoSeFiltra:
    def test_configurarlo_devuelve_el_derivado_y_no_el_hash(self, client, org, admin_user, auth_admin):
        resp = _poner_pin(client, auth_admin, org, admin_user.id, "1234")
        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        assert cuerpo["has_reprint_pin"] is True
        assert "reprint_pin_hash" not in cuerpo
        assert "reprint_pin" not in cuerpo

    def test_el_listado_tampoco_lo_expone(self, client, org, admin_user, auth_admin):
        assert _poner_pin(client, auth_admin, org, admin_user.id, "1234").status_code == 200

        resp = client.get("/api/users/", headers={**auth_admin, "X-Organization-ID": str(org.id)})
        assert resp.status_code == 200, resp.text
        fila = next(u for u in resp.json() if u["id"] == admin_user.id)
        assert fila["has_reprint_pin"] is True
        assert "reprint_pin_hash" not in fila
        assert "reprint_pin" not in fila

    def test_sin_pin_configurado_el_derivado_es_falso(self, client, org, admin_user, auth_admin):
        resp = client.get(f"/api/users/{admin_user.id}",
                          headers={**auth_admin, "X-Organization-ID": str(org.id)})
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_reprint_pin"] is False


class TestElPinAutoriza:
    def test_el_cajero_reimprime_una_venta_ajena_con_el_pin(
        self, client, org, venta, admin_user, auth_admin, auth_cajero_a
    ):
        assert _poner_pin(client, auth_admin, org, admin_user.id, "1234").status_code == 200

        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="1234")
        assert resp.status_code == 200, resp.text
        assert resp.json()["content_base64"]

    def test_un_pin_que_no_es_el_configurado_se_rechaza(
        self, client, org, venta, admin_user, auth_admin, auth_cajero_a
    ):
        assert _poner_pin(client, auth_admin, org, admin_user.id, "1234").status_code == 200

        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="9999")
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "PIN_INCORRECTO"

    def test_la_contrasena_del_gerente_sigue_sirviendo(
        self, client, org, venta, admin_user, auth_admin, auth_cajero_a, gerente_a
    ):
        """El PIN es un primer intento, no un reemplazo: quien no se puso PIN
        autoriza con su contrasena igual que antes."""
        assert _poner_pin(client, auth_admin, org, admin_user.id, "1234").status_code == 200

        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="test1234")
        assert resp.status_code == 200, resp.text

    def test_borrar_el_pin_lo_invalida(
        self, client, org, venta, admin_user, auth_admin, auth_cajero_a
    ):
        assert _poner_pin(client, auth_admin, org, admin_user.id, "1234").status_code == 200

        resp = _poner_pin(client, auth_admin, org, admin_user.id, "")
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_reprint_pin"] is False

        rechazo = _reimprimir(client, auth_cajero_a, org, venta.id, pin="1234")
        assert rechazo.status_code == 403, rechazo.text

    def test_el_pin_de_un_cajero_no_autoriza(
        self, client, org, venta, auth_admin, auth_cajero_a, cajero_a
    ):
        """Un PIN solo tiene sentido en roles gerenciales: al guardarlo en un
        cajero el router lo descarta (no queda huerfano) y, aunque quedara,
        la verificacion solo compara contra roles gerenciales activos."""
        alta = _poner_pin(client, auth_admin, org, cajero_a.id, "5678")
        assert alta.status_code == 200, alta.text
        assert alta.json()["has_reprint_pin"] is False

        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="5678")
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "PIN_INCORRECTO"

    def test_el_pin_de_otra_organizacion_no_autoriza(
        self, client, db, org, venta, auth_cajero_a
    ):
        from app.core.security import get_password_hash
        from app.models.organization import Branch, BranchType
        from app.modules.tenants.models import Organization
        from app.modules.users.models import Role
        from tests.conftest import _make_user

        otra = Organization(name="Otra Org PIN", status="ACTIVE")
        db.add(otra); db.flush()
        sucursal = Branch(name="Otra Suc PIN", branch_type=BranchType.STORE, can_sell=True,
                          is_active=True, organization_id=otra.id)
        db.add(sucursal); db.flush()
        ajeno = _make_user(db, otra, sucursal, "gerente_ajeno_pin", Role.GERENTE)
        ajeno.reprint_pin_hash = get_password_hash("4321")
        db.flush()

        resp = _reimprimir(client, auth_cajero_a, org, venta.id, pin="4321")
        assert resp.status_code == 403, resp.text


class TestValidacionDelPin:
    @pytest.mark.parametrize("pin", ["12", "abcd", "123456789", "12 34"])
    def test_un_pin_que_no_es_4_a_8_digitos_se_rechaza(
        self, client, org, admin_user, auth_admin, pin
    ):
        resp = _poner_pin(client, auth_admin, org, admin_user.id, pin)
        assert resp.status_code == 422, resp.text

    def test_el_alta_acepta_el_pin(self, client, org, branch_a, auth_admin):
        resp = client.post(
            "/api/users/",
            json={
                "username": "gerente_con_pin", "password": "test1234",
                "role": "GERENTE", "branch_id": branch_a.id, "reprint_pin": "8765",
            },
            headers={**auth_admin, "X-Organization-ID": str(org.id)},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_reprint_pin"] is True
        assert "reprint_pin_hash" not in resp.json()

    def test_el_alta_rechaza_un_pin_invalido(self, client, org, branch_a, auth_admin):
        resp = client.post(
            "/api/users/",
            json={
                "username": "gerente_pin_malo", "password": "test1234",
                "role": "GERENTE", "branch_id": branch_a.id, "reprint_pin": "abc",
            },
            headers={**auth_admin, "X-Organization-ID": str(org.id)},
        )
        assert resp.status_code == 422, resp.text


class TestQuienPuedeFijarlo:
    def test_un_cajero_no_puede_tocar_usuarios(self, client, org, admin_user, auth_cajero_a):
        """Sin este guard la cajera le fijaba el PIN al dueno y autorizaba sus
        propias reimpresiones con la bitacora senalando al dueno."""
        resp = _poner_pin(client, auth_cajero_a, org, admin_user.id, "1111")
        assert resp.status_code == 403, resp.text

    def test_degradar_al_gerente_borra_su_pin(self, client, org, gerente_a, auth_admin):
        alta = _poner_pin(client, auth_admin, org, gerente_a.id, "2468")
        assert alta.status_code == 200 and alta.json()["has_reprint_pin"] is True
        baja = client.put(
            f"/api/users/{gerente_a.id}",
            json={"role": "CAJERO"},
            headers={**auth_admin, "X-Organization-ID": str(org.id)},
        )
        assert baja.status_code == 200, baja.text
        assert baja.json()["has_reprint_pin"] is False

    def test_un_salto_de_linea_no_pasa_el_validador(self, client, org, admin_user, auth_admin):
        resp = _poner_pin(client, auth_admin, org, admin_user.id, "1234\n")
        assert resp.status_code == 422, resp.text
