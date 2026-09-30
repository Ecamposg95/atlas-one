"""Tests: traspaso de usuarios desde rmazh con su hash (scripts/import_rmazh_users.py)."""
import importlib

import pytest

from app.modules.users.models import User, UserOrganization

imp = importlib.import_module("scripts.import_rmazh_users")

HASH = "$2a$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab"
PIN = "$2a$12$zyxwvutsrqponmlkjihgfeZYXWVUTSRQPONMLKJIHGFEDCBA9876543210zz"

MIRNA = {"id": 41, "username": "Mirna", "full_name": "Mirna", "email": None, "personal_email": None,
         "phone": None, "rol": "ADMINISTRADOR", "is_active": True, "branch_id": 26,
         "password_hash": HASH, "reprint_pin_hash": PIN}
JOSE = {"id": 42, "username": "Jose", "full_name": "Jose Rivas", "email": None, "personal_email": None,
        "phone": "5512345678", "rol": "CAJERO", "is_active": True, "branch_id": 27,
        "password_hash": HASH, "reprint_pin_hash": None}


class TestCrea:
    def test_crea_admin_y_cajero_con_su_hash(self, db, org, branch_a):
        r = imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        assert r["creados"] == 2 and r["actualizados"] == 0

        mirna = db.query(User).filter(User.username == "Mirna").one()
        assert mirna.role.value == "ADMINISTRADOR"
        assert mirna.password_hash == HASH
        assert mirna.reprint_pin_hash == PIN
        assert mirna.branch_id == branch_a.id
        assert mirna.platform_role.value == "NONE"
        enlace = db.query(UserOrganization).filter_by(user_id=mirna.id, organization_id=org.id).one()
        assert enlace.org_role == "ADMIN"

        jose = db.query(User).filter(User.username == "Jose").one()
        assert jose.role.value == "CAJERO"
        assert jose.full_name == "Jose Rivas"
        assert jose.phone == "5512345678"
        assert jose.reprint_pin_hash is None
        enlace = db.query(UserOrganization).filter_by(user_id=jose.id, organization_id=org.id).one()
        assert enlace.org_role == "MEMBER"

    def test_respeta_is_active_false(self, db, org, branch_a):
        imp.import_rmazh_users(db, [dict(JOSE, is_active=False)], org.id, branch_a.id)
        assert db.query(User).filter(User.username == "Jose").one().is_active is False


class TestActualiza:
    def test_reemplaza_el_hash_del_admin_que_creo_onboard(self, db, org, branch_a, admin_a):
        """onboard_org.py crea al admin con contrasena generada; aqui recupera la real."""
        viejo = admin_a.password_hash
        r = imp.import_rmazh_users(db, [dict(MIRNA, username="admin_a")], org.id, branch_a.id)
        assert r["creados"] == 0 and r["actualizados"] == 1
        db.refresh(admin_a)
        assert admin_a.password_hash == HASH and admin_a.password_hash != viejo
        assert admin_a.reprint_pin_hash == PIN
        assert admin_a.full_name == "Mirna"

    def test_es_idempotente(self, db, org, branch_a):
        imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        r = imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        assert r["creados"] == 0 and r["actualizados"] == 2
        assert db.query(User).filter(User.username.in_(["Mirna", "Jose"])).count() == 2
        assert db.query(UserOrganization).filter_by(organization_id=org.id).count() == 2


class TestRechaza:
    def test_username_de_otra_organizacion_aborta_sin_escribir(self, db, org, branch_a):
        from app.models.organization import Organization
        from app.modules.users.models import PlatformRole, Role
        otra = Organization(name="Otra Org", status="ACTIVE")
        db.add(otra); db.flush()
        ajeno = User(username="Jose", password_hash=HASH, role=Role.CAJERO, platform_role=PlatformRole.NONE, is_active=True)
        db.add(ajeno); db.flush()
        db.add(UserOrganization(user_id=ajeno.id, organization_id=otra.id, org_role="MEMBER", is_active=True)); db.flush()

        with pytest.raises(ValueError, match="Jose.*otra organizacion"):
            imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        assert db.query(User).filter(User.username == "Mirna").first() is None, "nada se escribio"

    def test_rol_desconocido_aborta_con_el_nombre_del_rol(self, db, org, branch_a):
        """Review Focus #4."""
        with pytest.raises(ValueError, match="SUPERVISOR"):
            imp.import_rmazh_users(db, [dict(JOSE, rol="SUPERVISOR")], org.id, branch_a.id)
        assert db.query(User).filter(User.username == "Jose").first() is None

    def test_sin_hash_bcrypt_aborta(self, db, org, branch_a):
        with pytest.raises(ValueError, match="hash"):
            imp.import_rmazh_users(db, [dict(JOSE, password_hash="plano")], org.id, branch_a.id)

    def test_sucursal_de_otra_organizacion_aborta(self, db, org, branch_a):
        from app.models.organization import Organization, Branch
        from app.modules.tenants.models import BranchType
        otra = Organization(name="Otra Org", status="ACTIVE")
        db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True,
                       is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        with pytest.raises(ValueError, match="pertenece"):
            imp.import_rmazh_users(db, [JOSE], org.id, ajena.id)


class TestDryRun:
    def test_dry_run_no_escribe(self, db, org, branch_a):
        r = imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id, dry_run=True)
        assert r["creados"] == 2
        assert db.query(User).filter(User.username.in_(["Mirna", "Jose"])).count() == 0
