"""Tests: catalogo de planes, reglas de modulos y topes (app/services/plans.py)."""
import pytest

from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch
from app.modules.tenants.models import BranchType, IndustryType
from app.modules.users.models import PlatformRole, Role, User, UserOrganization
from app.services import plans


def _usuario(db, org, username, activo=True, platform_role=PlatformRole.NONE, enlace_activo=True, role=Role.CAJERO):
    u = User(username=username, password_hash="x", role=role, is_active=activo, platform_role=platform_role)
    db.add(u); db.flush()
    db.add(UserOrganization(user_id=u.id, organization_id=org.id, org_role="MEMBER", is_active=enlace_activo)); db.flush()
    return u


def _sucursal(db, org, nombre, can_sell=True, activa=True, tipo=BranchType.STORE):
    b = Branch(name=nombre, branch_type=tipo, can_sell=can_sell, is_active=activa, organization_id=org.id)
    db.add(b); db.flush()
    return b


def _sembrar_catalogo(db):
    """Catalogo real de modulos: seed_global_modules mas MODULES_CATALOG de
    init_presets_v2 (ahi viven hr, ai, finance, purchasing, etc.)."""
    from app.services.capabilities_service import seed_global_modules
    from scripts.init_presets_v2 import MODULES_CATALOG
    seed_global_modules(db)
    for key, name, desc, scope, status in MODULES_CATALOG:
        if not db.query(Module).filter(Module.key == key).first():
            db.add(Module(key=key, name=name, description=desc, scope=scope, status=status))
    db.flush()


class TestCatalogo:
    def test_seis_planes_en_orden(self):
        assert [p.clave for p in plans.PLANES] == ["FREE", "START", "PRO", "BUSINESS", "SCALE", "ULTRA_PLUS"]
        assert plans.PLANES_POR_CLAVE["ULTRA_PLUS"].nombre == "ULTRA+"

    def test_cada_plan_incluye_al_anterior(self):
        for ant, sig in zip(plans.PLANES, plans.PLANES[1:]):
            assert ant.modulos_crecimiento <= sig.modulos_crecimiento, (ant.clave, sig.clave)
            if ant.max_usuarios is not None and sig.max_usuarios is not None:
                assert ant.max_usuarios <= sig.max_usuarios
            if ant.max_sucursales_venta is not None and sig.max_sucursales_venta is not None:
                assert ant.max_sucursales_venta <= sig.max_sucursales_venta

    def test_topes_del_spec(self):
        topes = {p.clave: (p.max_usuarios, p.max_sucursales_venta) for p in plans.PLANES}
        assert topes == {
            "FREE": (2, 1), "START": (3, 1), "PRO": (10, 2),
            "BUSINESS": (25, 5), "SCALE": (100, 20), "ULTRA_PLUS": (None, None),
        }

    def test_modulos_de_crecimiento_del_spec(self):
        c = {p.clave: set(p.modulos_crecimiento) for p in plans.PLANES}
        assert c["FREE"] == set()
        assert c["START"] == {"quotes", "promotions"}
        assert c["PRO"] == c["START"] | {"purchasing", "warehouse", "logistics", "invoicing"}
        assert c["BUSINESS"] == c["PRO"] | {"finance", "hr", "commissions", "memberships", "customer_portal"}
        assert c["SCALE"] == c["BUSINESS"] | {"ai"}
        assert c["ULTRA_PLUS"] == c["SCALE"] and plans.PLANES_POR_CLAVE["ULTRA_PLUS"].permite_todo
        assert plans.MODULOS_CRECIMIENTO == frozenset(c["SCALE"])

    def test_base_y_crecimiento_no_se_pisan(self):
        assert not (plans.MODULOS_BASE & plans.MODULOS_CRECIMIENTO)

    def test_todo_modulo_gobernado_existe_en_el_catalogo(self, db):
        _sembrar_catalogo(db)
        claves = {k for (k,) in db.query(Module.key)}
        assert plans.MODULOS_CRECIMIENTO <= claves
        assert plans.MODULOS_BASE <= claves

    @pytest.mark.parametrize("clave", [None, "", "XYZ", "free"])
    def test_obtener_plan_desconocido_es_free(self, clave):
        assert plans.obtener_plan(clave).clave == "FREE"

    def test_es_plan_valido(self):
        assert plans.es_plan_valido("ULTRA_PLUS") and plans.es_plan_valido("FREE")
        assert not plans.es_plan_valido("GOLD") and not plans.es_plan_valido(None)
        assert plans.claves_validas() == ["FREE", "START", "PRO", "BUSINESS", "SCALE", "ULTRA_PLUS"]


class TestModulosPermitidos:
    def test_pos_free_tiene_base_y_preset_pero_no_quotes(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        permitidos = plans.modulos_permitidos(db, org)
        assert {"pos", "catalog", "labels", "crm"} <= permitidos
        assert "quotes" not in permitidos and "ai" not in permitidos

    def test_pos_start_tiene_quotes(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "START"; db.flush()
        assert "quotes" in plans.modulos_permitidos(db, org)

    def test_gastro_free_conserva_mesas_y_cocina(self, db, org):
        org.industry_type = IndustryType.RESTAURANT_FULL; org.plan = "FREE"; db.flush()
        permitidos = plans.modulos_permitidos(db, org)
        assert {"tables", "kds", "menu"} <= permitidos

    def test_preset_de_la_base_de_datos_manda_sobre_el_fallback(self, db, org):
        from app.models.modules import IndustryPreset
        db.add(IndustryPreset(industry_type="ATLAS_POS", display_name="x", modules=["core", "pos", "workshops"])); db.flush()
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        assert "workshops" in plans.modulos_permitidos(db, org)

    def test_sin_industria_solo_base(self, db, org):
        """Review Focus #3."""
        org.industry_type = None; org.plan = "FREE"; db.flush()
        assert plans.modulos_del_preset(db, None) == set()
        assert plans.modulos_permitidos(db, org) == set(plans.MODULOS_BASE)

    def test_ultra_plus_permite_todo_el_catalogo(self, db, org):
        _sembrar_catalogo(db)
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "ULTRA_PLUS"; db.flush()
        claves = {k for (k,) in db.query(Module.key)}
        assert plans.modulos_permitidos(db, org) == claves

    def test_plan_minimo_para(self):
        assert plans.plan_minimo_para("quotes").clave == "START"
        assert plans.plan_minimo_para("purchasing").clave == "PRO"
        assert plans.plan_minimo_para("hr").clave == "BUSINESS"
        assert plans.plan_minimo_para("ai").clave == "SCALE"
        assert plans.plan_minimo_para("pos") is None
        assert plans.plan_minimo_para("tables") is None


class TestUso:
    def test_cuenta_usuarios_activos_y_sucursales_que_venden(self, db, org, admin_user, hq_branch, branch_a):
        # admin_user (activo, NONE) + hq_branch (no vende) + branch_a (vende)
        _usuario(db, org, "inactivo", activo=False)
        _usuario(db, org, "enlace_apagado", enlace_activo=False)
        _usuario(db, org, "soporte", platform_role=PlatformRole.SUPERADMIN)
        _sucursal(db, org, "Almacen", can_sell=False, tipo=BranchType.WAREHOUSE)
        _sucursal(db, org, "Cerrada", can_sell=True, activa=False)
        u = plans.uso(db, org.id)
        assert u.usuarios_activos == 1
        assert u.sucursales_venta == 1

    def test_cliente_del_portal_no_consume_asiento(self, db, org, admin_user):
        _usuario(db, org, "cliente_portal", role=Role.CLIENTE)
        assert plans.uso(db, org.id).usuarios_activos == 1
        _usuario(db, org, "cajera_real")
        assert plans.uso(db, org.id).usuarios_activos == 2


class TestVerificaciones:
    def test_alta_usuario_al_tope_free_nombra_start(self, db, org, admin_user, cajero_a):
        org.plan = "FREE"; db.flush()
        with pytest.raises(plans.LimitePlanAlcanzado) as e:
            plans.verificar_alta_usuario(db, org)
        assert str(e.value) == "Tu plan ONE FREE permite 2 usuarios activos. Para agregar más, sube a ONE START."

    def test_alta_usuario_bajo_el_tope_pasa(self, db, org, admin_user):
        org.plan = "FREE"; db.flush()
        plans.verificar_alta_usuario(db, org)

    def test_alta_usuario_ultra_plus_nunca_bloquea(self, db, org, admin_user, cajero_a):
        org.plan = "ULTRA_PLUS"; db.flush()
        plans.verificar_alta_usuario(db, org)

    def test_alta_sucursal_al_tope_free_nombra_pro(self, db, org, branch_a):
        org.plan = "FREE"; db.flush()
        with pytest.raises(plans.LimitePlanAlcanzado) as e:
            plans.verificar_alta_sucursal(db, org)
        assert str(e.value) == "Tu plan ONE FREE permite 1 sucursal que vende. Para abrir otra, sube a ONE PRO."

    def test_alta_sucursal_business_con_dos_pasa(self, db, org, branch_a, branch_b):
        org.plan = "BUSINESS"; db.flush()
        plans.verificar_alta_sucursal(db, org)

    def test_mensaje_plural_de_sucursales(self, db, org, branch_a, branch_b):
        org.plan = "PRO"; db.flush()
        with pytest.raises(plans.LimitePlanAlcanzado) as e:
            plans.verificar_alta_sucursal(db, org)
        assert str(e.value) == "Tu plan ONE PRO permite 2 sucursales que venden. Para abrir otra, sube a BUSINESS."

    def test_activar_modulo_fuera_de_plan(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        with pytest.raises(plans.ModuloFueraDePlan) as e:
            plans.verificar_activar_modulo(db, org, "quotes", "Cotizaciones")
        assert str(e.value) == "El módulo Cotizaciones requiere el plan ONE START o superior (la organización está en ONE FREE)."

    def test_activar_modulo_base_o_de_preset_pasa(self, db, org):
        org.industry_type = IndustryType.RESTAURANT_FULL; org.plan = "FREE"; db.flush()
        plans.verificar_activar_modulo(db, org, "pos")
        plans.verificar_activar_modulo(db, org, "tables")

    def test_activar_modulo_vertical_ajeno_al_preset(self, db, org):
        """Review Focus #3: no es base, no es del preset, no lo gobierna ningun plan."""
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        with pytest.raises(plans.ModuloFueraDePlan) as e:
            plans.verificar_activar_modulo(db, org, "tables", "Mesas")
        assert str(e.value) == "El módulo Mesas no forma parte del preset ATLAS_POS de la organización; se habilita con ULTRA+ o cambiando de preset."

    def test_activar_modulo_sin_nombre_usa_la_clave(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        with pytest.raises(plans.ModuloFueraDePlan, match="El módulo quotes requiere"):
            plans.verificar_activar_modulo(db, org, "quotes")

    def test_modulos_fuera_de_plan_lista_los_heredados(self, db, org):
        """Review Focus #4."""
        _sembrar_catalogo(db)
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        for k in ("pos", "quotes", "hr"):
            db.add(OrganizationModule(organization_id=org.id, module_key=k, is_enabled=True))
        db.add(OrganizationModule(organization_id=org.id, module_key="ai", is_enabled=False)); db.flush()
        assert plans.modulos_fuera_de_plan(db, org) == ["hr", "quotes"]
