"""F0 seguridad, segunda tanda: el plan de una organización es de SUPERADMIN.

`PUT /api/platform/organizations/{id}` dejaba a SUPPORT cambiar `plan`, y desde
el megaplan F3 eso además mueve la suscripción (lo que se cobra). SUPPORT sigue
editando el resto de la ficha; con `plan` en el cuerpo recibe 403 y no se
guarda nada.
"""
import pytest

from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.users import PlatformRole, Role
from tests.conftest import _make_user


@pytest.fixture()
def auth_soporte(db, org):
    u = _make_user(db, org, None, "soporte_plan", Role.ADMINISTRADOR, PlatformRole.SUPPORT)
    return {"Authorization": f"Bearer {create_access_token(data={'sub': u.username, 'role': u.role.value})}"}


def _org(db, org):
    db.expire_all()
    return db.query(Organization).filter(Organization.id == org.id).one()


def test_support_no_cambia_el_plan(client, db, org, auth_soporte):
    antes = _org(db, org).plan
    r = client.put(f"/api/platform/organizations/{org.id}", json={"plan": "PRO"}, headers=auth_soporte)
    assert r.status_code == 403, r.text
    assert "plan" in r.json()["detail"]
    assert _org(db, org).plan == antes


def test_support_con_plan_y_otros_campos_no_guarda_nada(client, db, org, auth_soporte):
    """Se rechaza la petición entera: nada de aplicar el teléfono y callar el plan."""
    antes = _org(db, org)
    plan, telefono = antes.plan, antes.phone
    r = client.put(f"/api/platform/organizations/{org.id}",
                   json={"plan": "PRO", "phone": "5550001111"}, headers=auth_soporte)
    assert r.status_code == 403, r.text
    despues = _org(db, org)
    assert (despues.plan, despues.phone) == (plan, telefono)


def test_support_sigue_editando_lo_demas(client, db, org, auth_soporte):
    r = client.put(f"/api/platform/organizations/{org.id}",
                   json={"phone": "5550002222"}, headers=auth_soporte)
    assert r.status_code == 200, r.text
    assert _org(db, org).phone == "5550002222"


def test_superadmin_si_cambia_el_plan(client, db, org, auth_superadmin):
    r = client.put(f"/api/platform/organizations/{org.id}", json={"plan": "PRO"}, headers=auth_superadmin)
    assert r.status_code == 200, r.text
    assert _org(db, org).plan == "PRO"
