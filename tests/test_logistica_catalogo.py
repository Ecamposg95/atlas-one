"""Catálogo de contenedores y cajas (/api/logistics/containers|boxes): exige usuario
y vive por organización (regla de oro 5). Antes era global, sin autenticación y
el GET sembraba filas sin organization_id."""
import pytest

from app.models.logistics import BoxType, ContainerType
from app.modules.tenants.models import Branch, BranchType, Organization
from app.modules.users.models import Role
from tests.conftest import _auth_header, _make_user


@pytest.fixture()
def auth_otra_org(db):
    o = Organization(name="Otra Org", status="ACTIVE")
    db.add(o)
    db.flush()
    b = Branch(name="Matriz otra", branch_type=BranchType.STORE, can_sell=True, is_active=True, organization_id=o.id)
    db.add(b)
    db.flush()
    u = _make_user(db, o, b, "admin_otra", Role.ADMINISTRADOR)
    return _auth_header(u)


def test_sin_usuario_401(client):
    assert client.get("/api/logistics/containers").status_code == 401
    assert client.get("/api/logistics/boxes").status_code == 401


def test_crear_y_listar_por_organizacion(client, auth_admin, auth_otra_org, db, org):
    r = client.post("/api/logistics/containers", headers=auth_admin,
                    json={"name": "Camioneta demo", "inner_length": 420, "inner_width": 200, "inner_height": 190, "max_weight_kg": 1000})
    assert r.status_code == 200, r.text
    r = client.post("/api/logistics/boxes", headers=auth_admin,
                    json={"name": "Caja chica demo", "outer_length": 30, "outer_width": 20, "outer_height": 15, "weight_empty_kg": 0.5})
    assert r.status_code == 200, r.text
    assert db.query(ContainerType).filter(ContainerType.organization_id == org.id).count() == 1
    assert db.query(BoxType).filter(BoxType.organization_id == org.id).count() == 1

    mios = client.get("/api/logistics/containers", headers=auth_admin).json()
    assert [c["name"] for c in mios] == ["Camioneta demo"]
    assert [b["name"] for b in client.get("/api/logistics/boxes", headers=auth_admin).json()] == ["Caja chica demo"]

    # La otra organización no ve nada y el GET ya no siembra filas globales.
    assert client.get("/api/logistics/containers", headers=auth_otra_org).json() == []
    assert client.get("/api/logistics/boxes", headers=auth_otra_org).json() == []
    assert db.query(ContainerType).count() == 1
