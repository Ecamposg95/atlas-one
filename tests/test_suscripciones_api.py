"""Cobro de suscripciones (megaplan F3): API de plataforma, lectura de la tienda,
permisos y borrado forzado."""
from datetime import date
from decimal import Decimal

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.organization import Branch, BranchType, Organization
from app.models.platform import PlatformAuditLog
from app.models.users import PlatformRole, Role, User, UserOrganization
from app.modules.suscripciones import services
from app.modules.suscripciones.models import CargoSuscripcion, PagoSuscripcion, Suscripcion

HOY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def _hoy_fijo(monkeypatch):
    monkeypatch.setattr(services, "hoy_mx", lambda: HOY)


def _token(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}


def _usuario(db, org, username, role, platform_role=PlatformRole.NONE):
    u = User(username=username, password_hash=get_password_hash("test1234"), role=role,
             is_active=True, platform_role=platform_role)
    db.add(u); db.flush()
    if org is not None:
        db.add(UserOrganization(user_id=u.id, organization_id=org.id, org_role="MEMBER", is_active=True))
        db.flush()
    return u


@pytest.fixture()
def auth_support(db, org):
    return _token(_usuario(db, org, "soporte_plataforma", Role.ADMINISTRADOR, PlatformRole.SUPPORT))


@pytest.fixture()
def otra_org(db):
    o = Organization(name="Otra Tienda", status="ACTIVE", plan="PRO")
    db.add(o); db.flush()
    return o


@pytest.fixture()
def auth_admin_otra(db, otra_org):
    return _token(_usuario(db, otra_org, "admin_otra", Role.ADMINISTRADOR))


def _url(org):
    return f"/api/platform/organizations/{org.id}/suscripcion"


def _alta(client, auth, org, **datos):
    cuerpo = {"plan": "START", "fecha_inicio": "2026-11-15"}
    cuerpo.update(datos)
    r = client.put(_url(org), json=cuerpo, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _cargo(client, auth, org, **datos):
    r = client.post(f"{_url(org)}/cargos", json=datos, headers=auth)
    assert r.status_code in (200, 201), r.text
    return r


class TestPlataforma:
    def test_detalle_sin_suscripcion(self, client, auth_superadmin, org):
        r = client.get(_url(org), headers=auth_superadmin)
        assert r.status_code == 200
        assert r.json()["suscripcion"] is None and r.json()["cargos"] == []

    def test_org_inexistente_404(self, client, auth_superadmin):
        assert client.get("/api/platform/organizations/999999/suscripcion", headers=auth_superadmin).status_code == 404

    def test_alta_sincroniza_plan_y_deja_bitacora(self, client, auth_superadmin, db, org):
        cuerpo = _alta(client, auth_superadmin, org, rfc="xaxx010101000", razon_social="Tienda SA de CV",
                       correo_facturacion="pagos@tienda.mx", notas="trato de palabra")
        sus = cuerpo["suscripcion"]
        assert sus["plan"] == "START" and sus["plan_nombre"] == "ONE START"
        assert Decimal(sus["precio_mxn"]) == Decimal("499") and Decimal(sus["precio_lista_mxn"]) == Decimal("499")
        assert sus["rfc"] == "XAXX010101000" and sus["notas"] == "trato de palabra"
        assert sus["estado"] == "vencida" and sus["estado_manual"] is False   # renovación 15-nov sin pago
        db.expire_all()
        assert db.get(Organization, org.id).plan == "START"
        acciones = [a.action for a in db.query(PlatformAuditLog).filter(PlatformAuditLog.entity_type == "SUSCRIPCION")]
        assert "SUSCRIPCION_ALTA" in acciones and "SUSCRIPCION_CAMBIO_PLAN" in acciones

    def test_plan_desconocido_400(self, client, auth_superadmin, org):
        r = client.put(_url(org), json={"plan": "PLATINO"}, headers=auth_superadmin)
        assert r.status_code == 400
        assert "PLATINO" in r.json()["detail"]

    def test_put_de_organizacion_refleja_el_plan(self, client, auth_superadmin, db, org):
        _alta(client, auth_superadmin, org)
        r = client.put(f"/api/platform/organizations/{org.id}", json={"plan": "BUSINESS"}, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        sus = client.get(_url(org), headers=auth_superadmin).json()["suscripcion"]
        assert sus["plan"] == "BUSINESS"
        assert Decimal(sus["precio_mxn"]) == Decimal("499")   # el pactado no se mueve solo

    def test_cargo_idempotente_201_luego_200(self, client, auth_superadmin, db, org):
        _alta(client, auth_superadmin, org)
        r1 = _cargo(client, auth_superadmin, org)
        r2 = _cargo(client, auth_superadmin, org)
        assert (r1.status_code, r1.json()["creado"]) == (201, True)
        assert (r2.status_code, r2.json()["creado"]) == (200, False)
        assert r1.json()["cargo"]["id"] == r2.json()["cargo"]["id"]
        assert db.query(CargoSuscripcion).filter_by(organization_id=org.id).count() == 1

    def test_cargo_sin_suscripcion_409(self, client, auth_superadmin, org):
        assert client.post(f"{_url(org)}/cargos", json={}, headers=auth_superadmin).status_code == 409

    def test_pago_parcial_y_total(self, client, auth_superadmin, org):
        _alta(client, auth_superadmin, org)
        cargo_id = _cargo(client, auth_superadmin, org).json()["cargo"]["id"]
        url = f"/api/platform/suscripciones/cargos/{cargo_id}/pagos"

        r = client.post(url, json={"importe": "200.00", "metodo": "transferencia", "referencia": "SPEI 1"},
                        headers=auth_superadmin)
        assert r.status_code == 201, r.text
        cargo = r.json()["cargos"][0]
        assert cargo["estado"] == "pendiente" and Decimal(cargo["saldo"]) == Decimal("299")
        assert cargo["vencido"] is True
        assert cargo["pagos"][0]["registrado_por"] == "superadmin_test"
        assert r.json()["suscripcion"]["proxima_renovacion"] == "2026-11-15"

        assert client.post(url, json={"importe": "300", "metodo": "efectivo"}, headers=auth_superadmin).status_code == 422

        r = client.post(url, json={"importe": "299", "metodo": "deposito"}, headers=auth_superadmin)
        assert r.status_code == 201
        cargo = r.json()["cargos"][0]
        assert cargo["estado"] == "pagado" and Decimal(cargo["saldo"]) == 0 and len(cargo["pagos"]) == 2
        assert r.json()["suscripcion"]["proxima_renovacion"] == "2026-12-15"
        assert r.json()["suscripcion"]["estado"] == "al_corriente"

        assert client.post(url, json={"importe": "1", "metodo": "efectivo"}, headers=auth_superadmin).status_code == 409

    def test_pago_invalido_422(self, client, auth_superadmin, org):
        _alta(client, auth_superadmin, org)
        cargo_id = _cargo(client, auth_superadmin, org).json()["cargo"]["id"]
        url = f"/api/platform/suscripciones/cargos/{cargo_id}/pagos"
        for cuerpo in ({"importe": "0", "metodo": "efectivo"}, {"importe": "10", "metodo": "bitcoin"},
                       {"importe": "10.999", "metodo": "efectivo"}, {"metodo": "efectivo"}):
            assert client.post(url, json=cuerpo, headers=auth_superadmin).status_code == 422, cuerpo

    def test_cancelar_cargo(self, client, auth_superadmin, org):
        _alta(client, auth_superadmin, org)
        cargo_id = _cargo(client, auth_superadmin, org).json()["cargo"]["id"]
        r = client.post(f"/api/platform/suscripciones/cargos/{cargo_id}/cancelar",
                        json={"motivo": "duplicado"}, headers=auth_superadmin)
        assert r.status_code == 200
        assert r.json()["cargos"][0]["estado"] == "cancelado"
        assert r.json()["cargos"][0]["motivo_cancelacion"] == "duplicado"

    def test_estado_manual_suspendida_no_bloquea_nada(self, client, auth_superadmin, auth_admin, org):
        _alta(client, auth_superadmin, org, estado="suspendida")
        sus = client.get(_url(org), headers=auth_superadmin).json()["suscripcion"]
        assert sus["estado"] == "suspendida" and sus["estado_manual"] is True
        # Informativa: la tienda sigue entrando.
        assert client.get("/api/suscripcion/mia", headers=auth_admin).status_code == 200

    def test_lista_con_totales_y_filtro(self, client, auth_superadmin, db, org, otra_org):
        _alta(client, auth_superadmin, org)                     # START 499, vencida
        _cargo(client, auth_superadmin, org)
        _alta(client, auth_superadmin, otra_org, plan="PRO", precio_mxn="800.00",
              fecha_inicio="2026-11-01", proxima_renovacion="2026-12-20")   # al corriente
        r = client.get("/api/platform/suscripciones", headers=auth_superadmin)
        assert r.status_code == 200
        t = r.json()["totales"]
        assert Decimal(t["cartera_vencida"]) == Decimal("499")
        assert Decimal(t["ingreso_mensual_recurrente"]) == Decimal("800")
        assert t["por_estado"]["vencida"] == 1 and t["por_estado"]["al_corriente"] == 1
        assert {i["organizacion"] for i in r.json()["items"]} == {"Test Org", "Otra Tienda"}

        r = client.get("/api/platform/suscripciones?estado=vencida", headers=auth_superadmin)
        assert [i["organization_id"] for i in r.json()["items"]] == [org.id]
        assert Decimal(r.json()["items"][0]["saldo_vencido"]) == Decimal("499")
        assert Decimal(r.json()["totales"]["ingreso_mensual_recurrente"]) == Decimal("800")  # totales no se filtran

        r = client.get("/api/platform/suscripciones?q=otra", headers=auth_superadmin)
        assert [i["organizacion"] for i in r.json()["items"]] == ["Otra Tienda"]
        assert client.get("/api/platform/suscripciones?estado=morosa", headers=auth_superadmin).status_code == 400


class TestPermisos:
    def test_support_lee_pero_no_escribe(self, client, auth_superadmin, auth_support, db, org):
        _alta(client, auth_superadmin, org)
        cargo_id = _cargo(client, auth_superadmin, org).json()["cargo"]["id"]

        assert client.get("/api/platform/suscripciones", headers=auth_support).status_code == 200
        assert client.get(_url(org), headers=auth_support).status_code == 200

        assert client.put(_url(org), json={"precio_mxn": "1"}, headers=auth_support).status_code == 403
        assert client.post(f"{_url(org)}/cargos", json={"periodo_desde": "2027-01-15"},
                           headers=auth_support).status_code == 403
        assert client.post(f"/api/platform/suscripciones/cargos/{cargo_id}/pagos",
                           json={"importe": "10", "metodo": "efectivo"}, headers=auth_support).status_code == 403
        assert client.post(f"/api/platform/suscripciones/cargos/{cargo_id}/cancelar",
                           json={}, headers=auth_support).status_code == 403
        db.expire_all()
        assert db.query(PagoSuscripcion).count() == 0
        assert db.query(CargoSuscripcion).filter_by(organization_id=org.id).count() == 1
        assert db.query(Suscripcion).filter_by(organization_id=org.id).one().precio_mxn == Decimal("499.00")

    def test_la_tienda_no_entra_a_plataforma(self, client, auth_admin, org):
        assert client.get("/api/platform/suscripciones", headers=auth_admin).status_code == 403
        assert client.get(_url(org), headers=auth_admin).status_code == 403
        assert client.put(_url(org), json={"plan": "ULTRA_PLUS"}, headers=auth_admin).status_code == 403

    def test_sin_sesion(self, client, org):
        assert client.get("/api/suscripcion/mia").status_code == 401
        assert client.get(_url(org)).status_code == 401


class TestTienda:
    def test_admin_ve_lo_suyo_sin_notas_internas(self, client, auth_superadmin, auth_admin, org):
        _alta(client, auth_superadmin, org, notas="cliente difícil")
        cargo_id = _cargo(client, auth_superadmin, org).json()["cargo"]["id"]
        client.post(f"/api/platform/suscripciones/cargos/{cargo_id}/pagos",
                    json={"importe": "100", "metodo": "transferencia", "referencia": "SPEI 9", "notas": "interna"},
                    headers=auth_superadmin)

        r = client.get("/api/suscripcion/mia", headers=auth_admin)
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["plan"]["clave"] == "START" and cuerpo["plan"]["max_usuarios"] == 3
        assert cuerpo["uso"]["usuarios_activos"] >= 1
        assert cuerpo["suscripcion"]["estado"] == "vencida"
        assert cuerpo["suscripcion"]["notas"] is None
        pago = cuerpo["cargos"][0]["pagos"][0]
        assert pago["referencia"] == "SPEI 9" and pago["notas"] is None and pago["registrado_por"] is None

    def test_duenio_tambien(self, client, db, org):
        duenio = _usuario(db, org, "duenia", Role.DUEÑO)
        r = client.get("/api/suscripcion/mia", headers=_token(duenio))
        assert r.status_code == 200
        assert r.json()["suscripcion"] is None and r.json()["plan"]["clave"] == "FREE"

    def test_cajera_y_gerente_no_ven_nada(self, client, auth_superadmin, auth_cajero_a, auth_gerente_a, org):
        _alta(client, auth_superadmin, org)
        for auth in (auth_cajero_a, auth_gerente_a):
            r = client.get("/api/suscripcion/mia", headers=auth)
            assert r.status_code == 403
            assert "suscripcion" not in r.json()

    def test_una_tienda_no_ve_la_de_otra(self, client, auth_superadmin, auth_admin_otra, org, otra_org):
        _alta(client, auth_superadmin, org, precio_mxn="123.00")
        _cargo(client, auth_superadmin, org)
        _alta(client, auth_superadmin, otra_org, plan="PRO", precio_mxn="777.00")

        r = client.get("/api/suscripcion/mia", headers=auth_admin_otra)
        assert r.status_code == 200
        assert r.json()["suscripcion"]["organization_id"] == otra_org.id
        assert Decimal(r.json()["suscripcion"]["precio_mxn"]) == Decimal("777")
        assert r.json()["cargos"] == []

        # Ni pidiendo la otra organización por cabecera.
        ajena = dict(auth_admin_otra, **{"X-Organization-ID": str(org.id)})
        assert client.get("/api/suscripcion/mia", headers=ajena).status_code == 403


class TestBorradoForzado:
    def test_se_lleva_suscripcion_cargos_y_pagos(self, client, auth_superadmin, db, org, otra_org):
        db.add(Branch(name="Matriz", branch_type=BranchType.STORE, can_sell=True, is_active=True,
                      organization_id=otra_org.id))
        db.commit()
        _alta(client, auth_superadmin, otra_org, plan="PRO")
        cargo_id = _cargo(client, auth_superadmin, otra_org).json()["cargo"]["id"]
        client.post(f"/api/platform/suscripciones/cargos/{cargo_id}/pagos",
                    json={"importe": "100", "metodo": "efectivo"}, headers=auth_superadmin)
        # La de la organización que se queda no se debe tocar.
        _alta(client, auth_superadmin, org)
        _cargo(client, auth_superadmin, org)
        otra_id = otra_org.id

        r = client.delete(f"/api/platform/organizations/{otra_id}?force=true", headers=auth_superadmin)
        assert r.status_code == 200, r.text
        borrado = r.json()["deleted"]
        assert borrado["suscripcion_pagos"] == 1 and borrado["suscripcion_cargos"] == 1 and borrado["suscripciones"] == 1

        db.expire_all()
        for modelo in (PagoSuscripcion, CargoSuscripcion, Suscripcion):
            assert db.query(modelo).filter(modelo.organization_id == otra_id).count() == 0
        assert db.query(Suscripcion).filter_by(organization_id=org.id).count() == 1
        assert db.query(CargoSuscripcion).filter_by(organization_id=org.id).count() == 1
