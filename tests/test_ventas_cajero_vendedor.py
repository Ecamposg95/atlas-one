"""El VENDEDOR es rol de mostrador (2026-11-20): misma regla que la cajera en
`app/services/ventas_cajero.py`. Solo ve ventas de hoy de su sucursal y no
recibe los totales del dia."""
import pytest

from app.models.users import Role
from app.services.ventas_cajero import es_cajero


@pytest.fixture()
def auth_vendedor_a(db, org, branch_a):
    from conftest import _auth_header, _make_user
    return _auth_header(_make_user(db, org, branch_a, "vendedor_mostrador", Role.VENDEDOR))


def test_es_cajero_incluye_al_vendedor_y_no_al_gerente():
    class U:  # basta el atributo
        def __init__(self, role): self.role = role
    assert es_cajero(U(Role.CAJERO)) and es_cajero(U(Role.VENDEDOR))
    assert not es_cajero(U(Role.GERENTE)) and not es_cajero(U(Role.SOPORTE_OPERATIVO))


def test_el_vendedor_no_recibe_totales_del_dia(client, auth_vendedor_a):
    assert client.get("/api/sales/stats", headers=auth_vendedor_a).status_code == 403
    assert client.get("/api/reports/daily-summary", headers=auth_vendedor_a).status_code == 403


def _habilitar(db, org, key):
    from app.models.modules import Module, OrganizationModule
    if not db.query(Module).filter(Module.key == key).first():
        db.add(Module(key=key, name=key))
    db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def test_el_vendedor_lista_sus_ventas_de_hoy(client, db, org, auth_vendedor_a):
    _habilitar(db, org, "pos")
    r = client.get("/api/sales/?start_date=2020-01-01&end_date=2020-01-31", headers=auth_vendedor_a)
    assert r.status_code == 200      # las fechas del query se descartan: solo hoy
