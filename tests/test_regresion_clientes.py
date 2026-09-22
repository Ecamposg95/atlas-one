"""Regresión de la auditoría funcional del backend (2026-09-22) — clientes.

A-7: al habilitar el portal se creaba el `User` (role=CLIENTE) pero nunca la
fila `UserOrganization`. `get_current_active_organization` resuelve el tenant
sólo por esa tabla, así que el cliente recibía 403 en todo endpoint
org-scoped: el portal nacía inservible.
"""
from app.core.security import create_access_token
from app.models.modules import Module, OrganizationModule
from app.models.users import User, UserOrganization


def _h(headers, org):
    return {**headers, "X-Organization-ID": str(org.id)}


def _habilitar_crm(db, org):
    """El router de clientes exige `require_module("crm")`; ADMIN/DUEÑO lo
    saltan, pero la cuenta de portal (role=CLIENTE) no. Sin esta fila el probe
    de abajo respondería 403 por el módulo y no por el tenant, que es lo que
    esta regresión vigila."""
    if db.query(Module).filter(Module.key == "crm").first() is None:
        db.add(Module(key="crm", name="CRM"))
        db.flush()
    ya = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "crm",
    ).first()
    if ya is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="crm", is_enabled=True))
    else:
        ya.is_enabled = True
    db.commit()


def test_a7_el_alta_con_portal_vincula_al_usuario_con_la_organizacion(
    client, db, org, auth_admin
):
    _habilitar_crm(db, org)
    r = client.post("/api/customers/", json={
        "name": "Cliente Portal Regresion",
        "email": "cliente.portal.regresion@example.com",
        "enable_portal": True,
        "password": "clavesegura123",
    }, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text

    portal_user = db.query(User).filter(
        User.username == "cliente.portal.regresion@example.com"
    ).first()
    assert portal_user is not None

    assoc = db.query(UserOrganization).filter(
        UserOrganization.user_id == portal_user.id,
        UserOrganization.organization_id == org.id,
    ).first()
    assert assoc is not None and assoc.is_active

    # Y el cliente ya resuelve su tenant: antes CUALQUIER endpoint org-scoped
    # respondía 403 ("User belongs to no active organizations").
    token = {"Authorization": f"Bearer {create_access_token({'sub': portal_user.username})}"}
    r2 = client.get("/api/customers/stats", headers=_h(token, org))
    assert r2.status_code == 200, r2.text
    r3 = client.get("/api/customers/stats", headers=token)  # sin header de org
    assert r3.status_code == 200, r3.text


def test_a7_la_edicion_que_habilita_el_portal_tambien_vincula(
    client, db, org, auth_admin
):
    alta = client.post("/api/customers/", json={
        "name": "Cliente Sin Portal",
        "email": "cliente.sin.portal@example.com",
    }, headers=_h(auth_admin, org))
    assert alta.status_code == 200, alta.text
    customer_id = alta.json()["id"]

    assert db.query(User).filter(
        User.username == "cliente.sin.portal@example.com").first() is None

    edit = client.put(f"/api/customers/{customer_id}", json={
        "enable_portal": True,
        "password": "clavesegura456",
    }, headers=_h(auth_admin, org))
    assert edit.status_code == 200, edit.text

    portal_user = db.query(User).filter(
        User.username == "cliente.sin.portal@example.com").first()
    assert portal_user is not None
    assoc = db.query(UserOrganization).filter(
        UserOrganization.user_id == portal_user.id,
        UserOrganization.organization_id == org.id,
    ).first()
    assert assoc is not None and assoc.is_active


def test_a7_no_se_le_agrega_la_organizacion_a_una_cuenta_de_personal(
    client, db, org, auth_admin, cajero_a
):
    """Si el correo del cliente coincide con el de una cuenta de staff, esa
    cuenta NO gana una membresía nueva por el portal."""
    cajero_a.email = "staff.compartido@example.com"
    cajero_a.username = "staff.compartido@example.com"
    db.commit()
    membresias_antes = db.query(UserOrganization).filter(
        UserOrganization.user_id == cajero_a.id).count()

    r = client.post("/api/customers/", json={
        "name": "Cliente Con Correo De Staff",
        "email": "staff.compartido@example.com",
        "enable_portal": True,
        "password": "clavesegura789",
    }, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text

    assert db.query(UserOrganization).filter(
        UserOrganization.user_id == cajero_a.id).count() == membresias_antes
