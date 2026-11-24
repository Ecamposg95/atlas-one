"""F0 seguridad: la cookie `support_org_id` solo la pone y la usa el personal de plataforma."""
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.users import PlatformRole, Role
from tests.conftest import _make_user


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': u.username, 'role': u.role.value})}"}


def test_set_support_context_sin_sesion_es_401(client, org):
    r = client.post("/api/platform/set-support-context", json={"organization_id": org.id})
    assert r.status_code == 401
    assert "support_org_id" not in r.headers.get("set-cookie", "")


def test_clear_support_context_sin_sesion_es_401(client):
    assert client.post("/api/platform/clear-support-context").status_code == 401


def test_set_support_context_usuario_de_tienda_es_403(client, org, auth_admin, auth_cajero_a):
    for h in (auth_admin, auth_cajero_a):
        r = client.post("/api/platform/set-support-context", json={"organization_id": org.id}, headers=h)
        assert r.status_code == 403
        assert "support_org_id" not in r.headers.get("set-cookie", "")
        assert client.post("/api/platform/clear-support-context", headers=h).status_code == 403


def test_set_support_context_superadmin_y_support(client, db, org, auth_superadmin):
    soporte = _make_user(db, org, None, "soporte_f0", Role.ADMINISTRADOR, PlatformRole.SUPPORT)
    for h in (auth_superadmin, _auth(soporte)):
        r = client.post("/api/platform/set-support-context", json={"organization_id": org.id}, headers=h)
        assert r.status_code == 200
        assert f"support_org_id={org.id}" in r.headers["set-cookie"]
        client.cookies.clear()
        assert client.post("/api/platform/clear-support-context", headers=h).status_code == 200


def test_set_support_context_rechaza_org_no_numerica(client, auth_superadmin):
    r = client.post("/api/platform/set-support-context", json={"organization_id": "abc"}, headers=auth_superadmin)
    assert r.status_code == 400


def test_la_cookie_se_ignora_si_no_es_personal_de_plataforma(client, db, org, branch_a, auth_admin_a):
    """Un usuario de tienda con una cookie plantada sigue en SU organización."""
    otra = Organization(name="Otra Org F0", status="ACTIVE")
    db.add(otra)
    db.flush()
    client.cookies.set("support_org_id", str(otra.id))
    try:
        r = client.get("/api/reports/audit/discrepancies", headers=auth_admin_a)
    finally:
        client.cookies.clear()
    assert r.status_code == 200
