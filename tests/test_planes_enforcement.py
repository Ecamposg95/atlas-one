"""Tests: los topes y el gating de plan en las rutas (usuarios, sucursales, toggle, PUT)."""
import pytest

from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch
from app.modules.tenants.models import BranchType, IndustryType


def _nuevo_usuario(username="nuevo"):
    return {"username": username, "password": "clave-segura-1", "role": "CAJERO", "full_name": "Nuevo", "is_active": True}


class TestUsuarios:
    def test_free_con_dos_activos_rechaza_el_tercero(self, client, auth_admin, db, org, admin_user, cajero_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code == 403
        assert r.json()["detail"] == "Tu plan ONE FREE permite 2 usuarios activos. Para agregar más, sube a ONE START."

    def test_free_con_uno_activo_acepta(self, client, auth_admin, db, org, admin_user):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_inactivo_no_cuenta(self, client, auth_admin, db, org, admin_user, cajero_a):
        org.plan = "FREE"; cajero_a.is_active = False; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_reactivar_al_tope_rechaza(self, client, auth_admin, db, org, admin_user, cajero_a):
        """Review Focus #1."""
        org.plan = "FREE"
        # tercer usuario, inactivo: admin + cajero_a ya llenan el tope
        r = client.post("/api/users/", json=dict(_nuevo_usuario("dormido"), is_active=False), headers=auth_admin)
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]
        r = client.put(f"/api/users/{uid}", json={"is_active": True}, headers=auth_admin)
        assert r.status_code == 403
        assert "ONE START" in r.json()["detail"]

    def test_editar_sin_reactivar_no_pasa_por_el_tope(self, client, auth_admin, db, org, admin_user, cajero_a):
        org.plan = "FREE"; db.commit()
        r = client.put(f"/api/users/{cajero_a.id}", json={"full_name": "Cajero Uno"}, headers=auth_admin)
        assert r.status_code == 200, r.text

    def test_ultra_plus_nunca_bloquea(self, client, auth_admin, db, org, admin_user, cajero_a, gerente_a):
        org.plan = "ULTRA_PLUS"; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code in (200, 201), r.text


class TestSucursales:
    def test_free_con_una_que_vende_rechaza_otra_tienda(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Tienda 2", "branch_type": "STORE", "can_sell": True}, headers=auth_admin)
        assert r.status_code == 403
        assert r.json()["detail"] == "Tu plan ONE FREE permite 1 sucursal que vende. Para abrir otra, sube a ONE PRO."

    def test_almacen_no_cuenta(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Bodega", "branch_type": "WAREHOUSE"}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_tienda_que_no_vende_no_cuenta(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Exhibicion", "branch_type": "STORE", "can_sell": False}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_pasar_a_vender_al_tope_rechaza(self, client, auth_admin, db, org, admin_user, branch_a):
        """Review Focus #2."""
        org.plan = "FREE"
        b = Branch(name="Exhibicion", branch_type=BranchType.STORE, can_sell=False, is_active=True, organization_id=org.id)
        db.add(b); db.commit()
        r = client.put(f"/api/branches/{b.id}", json={"can_sell": True}, headers=auth_admin)
        assert r.status_code == 403
        assert "ONE PRO" in r.json()["detail"]

    def test_editar_la_que_ya_vende_no_pasa_por_el_tope(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.put(f"/api/branches/{branch_a.id}", json={"can_sell": True, "name": "Sucursal A renombrada"}, headers=auth_admin)
        assert r.status_code == 200, r.text

    def test_matriz_con_venta_explicita_cuenta(self, client, auth_admin_a, db, org, admin_a, branch_a):
        """Review Focus #2: una HQ nueva con can_sell=True es una sucursal que vende.
        Usa admin_a (sucursal A, sin HQ previa) para que el guard de 'HQ unica' no se dispare antes."""
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Matriz", "branch_type": "HQ", "can_sell": True}, headers=auth_admin_a)
        assert r.status_code == 403, r.text

    def test_reactivar_sucursal_al_tope_rechaza(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; branch_a.is_active = False; db.commit()
        r = client.post("/api/branches/", json={"name": "Tienda 2", "branch_type": "STORE", "can_sell": True}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text
        r = client.put(f"/api/branches/{branch_a.id}", json={"is_active": True}, headers=auth_admin)
        assert r.status_code == 403
        assert r.json()["detail"] == "Tu plan ONE FREE permite 1 sucursal que vende. Para abrir otra, sube a ONE PRO."

    def test_crear_sucursal_inactiva_que_vende_no_cuenta(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Dormida", "branch_type": "STORE", "can_sell": True, "is_active": False}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_pro_permite_la_segunda(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "PRO"; db.commit()
        r = client.post("/api/branches/", json={"name": "Tienda 2", "branch_type": "STORE", "can_sell": True}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text


class TestToggleModulo:
    @pytest.fixture(autouse=True)
    def _catalogo(self, db):
        from app.services.capabilities_service import seed_global_modules
        seed_global_modules(db)

    def test_encender_quotes_en_free_rechaza_con_start(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/quotes?enable=true", headers=auth_superadmin)
        assert r.status_code == 403
        assert "ONE START" in r.json()["detail"]
        assert db.query(OrganizationModule).filter_by(organization_id=org.id, module_key="quotes").first() is None

    def test_encender_quotes_en_start_pasa(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "START"; db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/quotes?enable=true", headers=auth_superadmin)
        assert r.status_code == 200, r.text

    def test_apagar_siempre_pasa(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True)); db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/quotes?enable=false", headers=auth_superadmin)
        assert r.status_code == 200, r.text

    def test_encender_modulo_del_preset_en_free_pasa(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.RESTAURANT_FULL; org.plan = "FREE"; db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/tables?enable=true", headers=auth_superadmin)
        assert r.status_code == 200, r.text


class TestCambioDePlan:
    def test_put_plan_valido_no_toca_modulos(self, client, auth_superadmin, db, org):
        """Review Focus #5."""
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "PRO"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True))
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True)); db.commit()
        antes = sorted((m.module_key, m.is_enabled) for m in db.query(OrganizationModule).filter_by(organization_id=org.id))
        r = client.put(f"/api/platform/organizations/{org.id}", json={"plan": "FREE"}, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        assert r.json()["plan"] == "FREE"
        db.expire_all()
        despues = sorted((m.module_key, m.is_enabled) for m in db.query(OrganizationModule).filter_by(organization_id=org.id))
        assert antes == despues

    def test_put_plan_desconocido_400_con_las_claves(self, client, auth_superadmin, db, org):
        r = client.put(f"/api/platform/organizations/{org.id}", json={"plan": "GOLD"}, headers=auth_superadmin)
        assert r.status_code == 400
        assert "FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS" in r.json()["detail"]

    def test_put_sin_plan_sigue_igual(self, client, auth_superadmin, db, org):
        r = client.put(f"/api/platform/organizations/{org.id}", json={"name": "Renombrada"}, headers=auth_superadmin)
        assert r.status_code == 200, r.text


class TestHerencia:
    def test_modulo_fuera_de_plan_encendido_sigue_pasando_require_module(self, client, auth_admin, db, org, admin_user, hq_branch):
        """Review Focus #4: nada se apaga."""
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True)); db.commit()
        r = client.get("/api/quotes/", headers=auth_admin)
        assert r.status_code != 403, r.text


class TestOnboard:
    def test_onboard_rechaza_plan_desconocido(self, db):
        import importlib
        on = importlib.import_module("scripts.onboard_org")
        with pytest.raises(ValueError, match="FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS"):
            on.onboard(db, name="Org Plan Malo", industry="ATLAS_POS", admin_username="plan_malo", password="x" * 12, plan="GOLD")

    def test_onboard_acepta_ultra_plus(self, db):
        import importlib
        on = importlib.import_module("scripts.onboard_org")
        r = on.onboard(db, name="Org Ultra", industry="ATLAS_POS", admin_username="ultra_admin", password="x" * 12, plan="ULTRA_PLUS")
        assert r["plan"] == "ULTRA_PLUS"
