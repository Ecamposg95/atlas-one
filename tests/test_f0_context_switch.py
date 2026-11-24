"""F0 seguridad: `context/switch` solo deja entrar a sucursales de una organización del usuario."""
from app.models.organization import Branch, BranchType, Organization
from app.models.users import UserOrganization


def _sucursal_ajena(db):
    otra = Organization(name="Otra Org Switch", status="ACTIVE")
    db.add(otra)
    db.flush()
    b = Branch(name="Ajena", branch_type=BranchType.STORE, organization_id=otra.id, is_active=True)
    db.add(b)
    db.flush()
    return otra, b


def test_switch_a_sucursal_propia(client, branch_a, auth_admin):
    r = client.post(f"/api/auth/context/switch?branch_id={branch_a.id}", headers=auth_admin)
    assert r.status_code == 200
    assert r.json()["ctx_id"] == branch_a.id


def test_switch_a_sucursal_de_otra_organizacion_es_404(client, db, auth_admin):
    _, ajena = _sucursal_ajena(db)
    r = client.post(f"/api/auth/context/switch?branch_id={ajena.id}", headers=auth_admin)
    assert r.status_code == 404
    assert "access_token" not in r.json()


def test_switch_con_membresia_inactiva_es_404(client, db, admin_user, auth_admin):
    otra, ajena = _sucursal_ajena(db)
    db.add(UserOrganization(user_id=admin_user.id, organization_id=otra.id, org_role="ADMIN", is_active=False))
    db.flush()
    r = client.post(f"/api/auth/context/switch?branch_id={ajena.id}", headers=auth_admin)
    assert r.status_code == 404


def test_switch_con_membresia_activa_en_la_otra_org(client, db, admin_user, auth_admin):
    otra, ajena = _sucursal_ajena(db)
    db.add(UserOrganization(user_id=admin_user.id, organization_id=otra.id, org_role="MEMBER", is_active=True))
    db.flush()
    r = client.post(f"/api/auth/context/switch?branch_id={ajena.id}", headers=auth_admin)
    assert r.status_code == 200


def test_superadmin_entra_a_cualquier_sucursal(client, db, auth_superadmin):
    _, ajena = _sucursal_ajena(db)
    r = client.post(f"/api/auth/context/switch?branch_id={ajena.id}", headers=auth_superadmin)
    assert r.status_code == 200


def test_switch_a_hq_sigue_funcionando(client, auth_admin):
    r = client.post("/api/auth/context/switch", headers=auth_admin)
    assert r.status_code == 200
    assert r.json()["ctx_type"] == "HQ"
