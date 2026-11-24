"""F0 seguridad: las cookies de sesión llevan `Secure` según `COOKIE_SECURE` (auto por omisión)."""
import pytest


def _cookie_login(client, headers=None):
    r = client.post("/api/auth/login", data={"username": "admin_test", "password": "test1234"}, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.headers["set-cookie"].lower()


@pytest.fixture(autouse=True)
def _sin_variable(monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)


def test_auto_por_http_sale_sin_secure(client, admin_user):
    c = _cookie_login(client)
    assert "access_token=" in c and "secure" not in c
    assert "samesite=lax" in c and "httponly" in c


def test_auto_detras_de_proxy_https_sale_secure(client, admin_user):
    c = _cookie_login(client, {"X-Forwarded-Proto": "https"})
    assert "secure" in c and "samesite=lax" in c and "httponly" in c


def test_true_fuerza_secure(client, admin_user, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    assert "secure" in _cookie_login(client)


def test_false_lo_apaga_aunque_sea_https(client, admin_user, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "false")
    assert "secure" not in _cookie_login(client, {"X-Forwarded-Proto": "https"})


def test_context_switch_tambien(client, admin_user, auth_admin):
    r = client.post("/api/auth/context/switch", headers={**auth_admin, "X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert "secure" in r.headers["set-cookie"].lower()


def test_cookie_de_soporte_tambien(client, org, auth_superadmin):
    r = client.post("/api/platform/set-support-context", json={"organization_id": org.id},
                    headers={**auth_superadmin, "X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert "secure" in r.headers["set-cookie"].lower()
