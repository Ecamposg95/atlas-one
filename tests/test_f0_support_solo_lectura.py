"""F0 seguridad: SUPPORT no asigna administradores, no hace bootstrap ni exporta."""
import pytest

from app.core.security import create_access_token
from app.models.organization import Branch
from app.models.users import PlatformRole, Role, User
from tests.conftest import _make_user


@pytest.fixture()
def auth_soporte(db, org):
    u = _make_user(db, org, None, "soporte_f0", Role.ADMINISTRADOR, PlatformRole.SUPPORT)
    return {"Authorization": f"Bearer {create_access_token(data={'sub': u.username, 'role': u.role.value})}"}


def test_support_no_asigna_administradores(client, db, org, auth_soporte):
    r = client.post(f"/api/platform/organizations/{org.id}/admins",
                    json={"username": "intruso_f0", "password": "secreto123", "full_name": "Intruso"},
                    headers=auth_soporte)
    assert r.status_code == 403
    assert db.query(User).filter(User.username == "intruso_f0").first() is None


def test_support_no_hace_bootstrap(client, db, org, auth_soporte):
    r = client.post(f"/api/platform/organizations/{org.id}/bootstrap", headers=auth_soporte)
    assert r.status_code == 403
    assert db.query(Branch).filter(Branch.organization_id == org.id).count() == 0


def test_support_no_exporta(client, org, auth_soporte):
    assert client.get(f"/api/platform/organizations/{org.id}/export", headers=auth_soporte).status_code == 403


def test_support_sigue_leyendo(client, auth_soporte):
    assert client.get("/api/platform/organizations", headers=auth_soporte).status_code == 200


def test_superadmin_conserva_las_tres(client, db, org, auth_superadmin):
    assert client.get(f"/api/platform/organizations/{org.id}/export", headers=auth_superadmin).status_code == 200
    assert client.post(f"/api/platform/organizations/{org.id}/bootstrap", headers=auth_superadmin).status_code == 200
    r = client.post(f"/api/platform/organizations/{org.id}/admins",
                    json={"username": "dueno_f0", "password": "secreto123", "full_name": "Dueño"},
                    headers=auth_superadmin)
    assert r.status_code == 200, r.text
