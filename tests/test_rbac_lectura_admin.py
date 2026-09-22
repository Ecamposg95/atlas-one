"""Los GET de Usuarios y Organizacion tambien piden rol, no solo los POST/PUT.

Antes de este cambio bastaba una sesion valida: un CAJERO que escribiera
`/users` en la barra de direcciones veia el listado completo del personal
(username, rol, sucursal y quien tiene PIN de reimpresion), y en
`/organization` los datos fiscales, el tipo de cambio y la comision de
tarjeta de la empresa. El frontend tampoco tenia guarda de rol en esas rutas,
asi que el backend era la unica linea que quedaba — y no estaba.

Lo que estas pruebas fijan:
  - ADMINISTRADOR y SUPERADMIN leen.
  - CAJERO y GERENTE reciben 403.
  - `/users/me` sigue abierto: cada quien lee su propia ficha.
"""
import pytest


def _get(client, url, auth, org):
    return client.get(url, headers={**auth, "X-Organization-ID": str(org.id)})


class TestListadoDeUsuarios:
    def test_la_administradora_lo_lee(self, client, org, auth_admin):
        assert _get(client, "/api/users/", auth_admin, org).status_code == 200

    def test_el_superadmin_de_plataforma_lo_lee(self, client, org, auth_superadmin):
        assert _get(client, "/api/users/", auth_superadmin, org).status_code == 200

    @pytest.mark.parametrize("fixture", ["auth_cajero_a", "auth_gerente_a"])
    def test_el_mostrador_no_lo_lee(self, client, org, request, fixture):
        auth = request.getfixturevalue(fixture)
        assert _get(client, "/api/users/", auth, org).status_code == 403

    def test_la_cajera_tampoco_lee_la_ficha_de_otra_persona(
        self, client, org, admin_user, auth_cajero_a
    ):
        resp = _get(client, f"/api/users/{admin_user.id}", auth_cajero_a, org)
        assert resp.status_code == 403

    def test_pero_si_lee_la_suya(self, client, org, cajero_a, auth_cajero_a):
        resp = _get(client, "/api/users/me", auth_cajero_a, org)
        assert resp.status_code == 200
        assert resp.json()["username"] == cajero_a.username


class TestFichaDeLaOrganizacion:
    def test_la_administradora_la_lee(self, client, org, auth_admin):
        resp = _get(client, "/api/organization/", auth_admin, org)
        assert resp.status_code == 200
        assert resp.json()["id"] == org.id

    def test_el_superadmin_de_plataforma_la_lee(self, client, org, auth_superadmin):
        assert _get(client, "/api/organization/", auth_superadmin, org).status_code == 200

    @pytest.mark.parametrize("fixture", ["auth_cajero_a", "auth_gerente_a"])
    def test_el_mostrador_no_la_lee(self, client, org, request, fixture):
        auth = request.getfixturevalue(fixture)
        assert _get(client, "/api/organization/", auth, org).status_code == 403

    def test_el_contexto_de_usuario_sigue_abierto(self, client, org, auth_cajero_a):
        """El POS necesita /users/me/context para saber que modulos tiene."""
        resp = _get(client, "/api/users/me/context", auth_cajero_a, org)
        assert resp.status_code == 200
        assert "enabled_modules" in resp.json()
