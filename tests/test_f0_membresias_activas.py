"""F0 seguridad: el login y el acceso a cortes miran membresías ACTIVAS, en orden fijo."""
from datetime import datetime, timezone
from decimal import Decimal

from app.core.security import get_password_hash
from app.models.cash import CashSession, CashSessionStatus
from app.models.organization import Branch, BranchType, Organization
from app.models.users import Role, User, UserOrganization


def _org(db, nombre):
    o = Organization(name=nombre, status="ACTIVE")
    db.add(o)
    db.flush()
    return o


def _usuario(db, username, membresias):
    """`membresias`: lista de (org, activa), en el orden en que se insertan."""
    u = User(username=username, password_hash=get_password_hash("test1234"), role=Role.ADMINISTRADOR, is_active=True)
    db.add(u)
    db.flush()
    for o, activa in membresias:
        db.add(UserOrganization(user_id=u.id, organization_id=o.id, org_role="MEMBER", is_active=activa))
        db.flush()
    return u


def _login(client, username):
    r = client.post("/api/auth/login", data={"username": username, "password": "test1234"})
    assert r.status_code == 200, r.text
    return r.json()


def test_login_ignora_la_membresia_inactiva(client, db):
    vieja, vigente = _org(db, "Vieja F0"), _org(db, "Vigente F0")
    _usuario(db, "dos_orgs_f0", [(vieja, False), (vigente, True)])
    d = _login(client, "dos_orgs_f0")
    assert d["user"]["organization_id"] == vigente.id
    assert d["organization"]["id"] == vigente.id


def test_login_sin_membresia_activa_no_reporta_organizacion(client, db):
    vieja = _org(db, "Solo Vieja F0")
    _usuario(db, "sin_activa_f0", [(vieja, False)])
    d = _login(client, "sin_activa_f0")
    assert d["user"]["organization_id"] is None and d["organization"] is None


def test_login_con_dos_activas_elige_siempre_la_de_menor_id(client, db):
    a, b = _org(db, "A F0"), _org(db, "B F0")
    _usuario(db, "orden_f0", [(b, True), (a, True)])     # se inserta primero la de id mayor
    assert _login(client, "orden_f0")["user"]["organization_id"] == min(a.id, b.id)


def _corte_en(db, o, user):
    b = Branch(name=f"Suc {o.name}", branch_type=BranchType.STORE, organization_id=o.id, is_active=True)
    db.add(b)
    db.flush()
    s = CashSession(user_id=user.id, branch_id=b.id, status=CashSessionStatus.CLOSED,
                    opening_balance=Decimal("0"), closing_balance=Decimal("0"),
                    closed_at=datetime.now(timezone.utc))
    db.add(s)
    db.flush()
    return s


def _auth(client, username):
    return {"Authorization": f"Bearer {_login(client, username)['access_token']}"}


def test_corte_de_la_segunda_organizacion_del_usuario(client, db):
    """Con dos membresías activas, el corte de cualquiera de las dos es suyo."""
    a, b = _org(db, "Caja A F0"), _org(db, "Caja B F0")
    u = _usuario(db, "caja_dos_f0", [(a, True), (b, True)])
    h = _auth(client, "caja_dos_f0")
    for o in (a, b):
        s = _corte_en(db, o, u)
        assert client.get(f"/api/cash/{s.id}/audit-log", headers=h).status_code == 200


def test_corte_de_organizacion_con_membresia_inactiva_es_403(client, db):
    a, b = _org(db, "Caja C F0"), _org(db, "Caja D F0")
    u = _usuario(db, "caja_inactiva_f0", [(a, False), (b, True)])
    s = _corte_en(db, a, u)
    r = client.get(f"/api/cash/{s.id}/audit-log", headers=_auth(client, "caja_inactiva_f0"))
    assert r.status_code == 403


def test_corte_de_organizacion_ajena_es_403(client, db):
    a, ajena = _org(db, "Caja E F0"), _org(db, "Caja Ajena F0")
    u = _usuario(db, "caja_ajena_f0", [(a, True)])
    s = _corte_en(db, ajena, u)
    r = client.get(f"/api/cash/{s.id}/audit-log", headers=_auth(client, "caja_ajena_f0"))
    assert r.status_code == 403
