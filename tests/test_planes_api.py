"""Tests: API de plataforma de planes (catalogo, uso, marcas por modulo)."""
import pytest

from app.models.modules import OrganizationModule
from app.modules.tenants.models import IndustryType


@pytest.fixture(autouse=True)
def _catalogo(client, db):  # client primero: su startup siembra con otra conexion
    # Catalogo completo: seed_global_modules no siembra ai/hr/finance/purchasing,
    # que viven en MODULES_CATALOG de init_presets_v2.
    from app.models.modules import Module
    from app.services.capabilities_service import seed_global_modules
    from scripts.init_presets_v2 import MODULES_CATALOG
    seed_global_modules(db)
    for key, name, desc, scope, status in MODULES_CATALOG:
        if not db.query(Module).filter(Module.key == key).first():
            db.add(Module(key=key, name=name, description=desc, scope=scope, status=status))
    db.commit()


class TestCatalogo:
    def test_lista_seis_planes_en_orden(self, client, auth_superadmin):
        r = client.get("/api/platform/plans", headers=auth_superadmin)
        assert r.status_code == 200
        claves = [p["clave"] for p in r.json()]
        assert claves == ["FREE", "START", "PRO", "BUSINESS", "SCALE", "ULTRA_PLUS"]
        ultra = r.json()[-1]
        assert ultra["nombre"] == "ULTRA+" and ultra["max_usuarios"] is None and ultra["permite_todo"] is True
        assert r.json()[1]["modulos_crecimiento"] == sorted(["quotes", "promotions"])

    def test_requiere_plataforma(self, client, auth_admin):
        r = client.get("/api/platform/plans", headers=auth_admin)
        assert r.status_code in (401, 403)


class TestPlanUso:
    def test_uso_y_fuera_de_plan(self, client, auth_superadmin, db, org, admin_user, hq_branch, branch_a):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True)); db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/plan-uso", headers=auth_superadmin)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["plan"]["clave"] == "FREE" and j["plan"]["max_usuarios"] == 2
        assert j["usuarios_activos"] == 1  # admin_user; el superadmin es de plataforma y no cuenta
        assert j["sucursales_venta"] == 1
        assert j["modulos_fuera_de_plan"] == ["quotes"]

    def test_org_inexistente_404(self, client, auth_superadmin):
        r = client.get("/api/platform/organizations/999999/plan-uso", headers=auth_superadmin)
        assert r.status_code == 404


class TestModulosConPlan:
    def test_cada_modulo_trae_plan_minimo_y_permitido(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/modules", headers=auth_superadmin)
        assert r.status_code == 200
        por_clave = {m["key"]: m for m in r.json()}
        assert por_clave["pos"]["plan_minimo"] is None and por_clave["pos"]["permitido_por_plan"] is True
        assert por_clave["quotes"]["plan_minimo"] == "START" and por_clave["quotes"]["permitido_por_plan"] is False
        assert por_clave["tables"]["plan_minimo"] is None and por_clave["tables"]["permitido_por_plan"] is False
        assert por_clave["ai"]["plan_minimo"] == "SCALE"

    def test_en_ultra_plus_todo_permitido(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "ULTRA_PLUS"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/modules", headers=auth_superadmin)
        assert all(m["permitido_por_plan"] for m in r.json())


class TestUpsellConPlan:
    def test_recomendacion_trae_plan_minimo(self, client, auth_superadmin, db, org):
        # El endpoint solo considera modulos con upsell_metadata, que el
        # fixture del catalogo no siembra: se pone la real de init_presets_v2.
        from app.models.modules import Module
        from scripts.init_presets_v2 import MODULE_UPSELL
        for mod in db.query(Module).all():
            mod.upsell_metadata = MODULE_UPSELL.get(mod.key)
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/upsell-recommendations", headers=auth_superadmin)
        assert r.status_code == 200
        recs = {x["module_key"]: x for x in r.json()["recommendations"]}
        # ATLAS_POS nunca enciende purchasing: siempre es recomendacion.
        assert "purchasing" in recs, sorted(recs)
        assert recs["purchasing"]["plan_minimo"] == "PRO"
        for x in recs.values():
            assert "plan_minimo" in x
