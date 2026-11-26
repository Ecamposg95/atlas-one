"""Estado de construcción por módulo (app/services/estado_modulos.py).

Guardia: todo módulo que el catálogo, un plan o un preset nombre tiene que
declarar si está `disponible`, `en_construccion` u `oculto`. Sin esto un módulo
nuevo entraría al menú y a los planes sin que nadie decidiera si ya se ofrece.
"""
import inspect
import re

import pytest

from app.models.modules import Module, OrganizationModule
from app.modules.tenants.models import IndustryType
from app.services import estado_modulos as em


def _catalogo_completo() -> set[str]:
    """Los dos catálogos vivos: el de despliegue (init_presets_v2) y el de
    arranque (seed_global_modules). Ver tests/test_catalogo_capacidades.py."""
    from app.services import capabilities_service
    from scripts.init_presets_v2 import MODULES_CATALOG

    fuente = inspect.getsource(capabilities_service.seed_global_modules)
    constantes = re.findall(r'"key":\s*(MOD\w+)', fuente)
    arranque = {getattr(capabilities_service, c) for c in constantes}
    return {m[0] for m in MODULES_CATALOG} | arranque


def _nombrados_por_planes_y_presets() -> set[str]:
    from app.services import plans
    from app.services.capabilities_service import INDUSTRY_PRESETS
    from scripts.init_presets_v2 import MODULE_UPSELL, PRESETS

    claves = set(plans.MODULOS_BASE) | set(plans.MODULOS_CRECIMIENTO) | set(plans.MODULOS_FUERA_DE_PLAN)
    for p in plans.PLANES:
        claves |= set(p.modulos_crecimiento)
    for p in PRESETS:
        claves |= set(p["mods"])
    for mods in INDUSTRY_PRESETS.values():
        claves |= set(mods)
    claves |= set(MODULE_UPSELL)
    return claves


class TestDeclaracion:
    def test_todo_modulo_del_catalogo_declara_estado(self):
        faltan = sorted(_catalogo_completo() - set(em.ESTADO_MODULOS))
        assert not faltan, (
            f"módulos del catálogo sin estado declarado en app/services/estado_modulos.py: {faltan}"
        )

    def test_todo_modulo_de_un_plan_o_preset_declara_estado(self):
        faltan = sorted(_nombrados_por_planes_y_presets() - set(em.ESTADO_MODULOS))
        assert not faltan, f"planes/presets nombran módulos sin estado declarado: {faltan}"

    def test_no_se_declaran_modulos_que_nadie_nombra(self):
        sobran = sorted(set(em.ESTADO_MODULOS) - _catalogo_completo() - _nombrados_por_planes_y_presets())
        assert not sobran, f"estado declarado para módulos que no existen en el catálogo: {sobran}"

    def test_los_estados_son_validos(self):
        raros = {k: v for k, v in em.ESTADO_MODULOS.items() if v not in em.ESTADOS}
        assert not raros

    def test_la_base_esta_toda_disponible(self):
        """Lo que cualquier plan trae no puede ser una promesa sin construir.

        Excepción: `invoicing` está en la base solo porque es la casilla de IVA
        del cobro (capacidad `factura`), que sí funciona; no tiene pantalla y la
        facturación CFDI que su nombre sugiere sigue sin existir (§4.1)."""
        from app.services.plans import MODULOS_BASE
        assert em.solo_no_disponibles(MODULOS_BASE) == ["invoicing"]

    def test_el_formato_lo_puede_leer_el_frontend(self):
        """vitest (estadoModulos.test.ts) lee el archivo con esta misma expresión."""
        texto = inspect.getsource(em)
        leido = dict(re.findall(r'^\s*"([a-z_]+)":\s*(DISPONIBLE|EN_CONSTRUCCION|OCULTO),', texto, re.M))
        assert {k: v.lower() for k, v in leido.items()} == em.ESTADO_MODULOS


class TestConsulta:
    def test_estado_de(self):
        assert em.estado_de("pos") == em.DISPONIBLE
        assert em.estado_de("commissions") == em.OCULTO
        assert em.estado_de("appointments") == em.EN_CONSTRUCCION
        # Un módulo creado a mano desde plataforma no tiene código detrás.
        assert em.estado_de("modulo_inventado") == em.OCULTO
        assert em.esta_disponible("quotes") and not em.esta_disponible("promotions")

    def test_no_disponibles_y_filtros(self):
        nd = em.no_disponibles()
        assert "pos" not in nd and nd["memberships"] == em.OCULTO and nd["ai"] == em.EN_CONSTRUCCION
        assert em.solo_disponibles(["quotes", "promotions", "pos"]) == ["pos", "quotes"]
        assert em.solo_no_disponibles(["quotes", "promotions", "pos"]) == ["promotions"]


def _cabeceras(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture
def _catalogo(client, db):  # client primero: su startup siembra con otra conexión
    from app.services.capabilities_service import seed_global_modules
    from scripts.init_presets_v2 import MODULE_UPSELL, MODULES_CATALOG
    seed_global_modules(db)
    for key, name, desc, scope, status in MODULES_CATALOG:
        if not db.query(Module).filter(Module.key == key).first():
            db.add(Module(key=key, name=name, description=desc, scope=scope, status=status))
    db.flush()
    for mod in db.query(Module).all():
        mod.upsell_metadata = MODULE_UPSELL.get(mod.key)
    db.commit()


class TestCanales:
    def test_me_context_lleva_los_no_disponibles_sin_recortar_los_encendidos(self, client, db, auth_admin, org, _catalogo):
        """Encendido se queda encendido: solo viaja, aparte, qué no mostrar."""
        db.add(OrganizationModule(organization_id=org.id, module_key="commissions", is_enabled=True))
        db.commit()
        cuerpo = client.get("/api/users/me/context", headers=_cabeceras(auth_admin, org)).json()
        assert "commissions" in cuerpo["enabled_modules"]
        assert cuerpo["modulos_no_disponibles"] == em.no_disponibles()
        assert cuerpo["modulos_no_disponibles"]["commissions"] == "oculto"

    def test_planes_dicen_que_parte_de_la_promesa_no_esta_construida(self, client, auth_superadmin, _catalogo):
        planes = {p["clave"]: p for p in client.get("/api/platform/plans", headers=auth_superadmin).json()}
        assert planes["FREE"]["modulos_no_disponibles"] == []
        # Desde la limpieza de la promesa (2026-11-26) los planes ya no venden lo
        # no construido; solo queda `ai`, pendiente de decisión, marcado.
        assert planes["START"]["modulos_no_disponibles"] == []
        assert planes["SCALE"]["modulos_no_disponibles"] == ["ai"]
        for p in planes.values():
            assert set(p["modulos_no_disponibles"]) <= set(p["modulos_crecimiento"])

    def test_plataforma_ve_el_estado_de_cada_modulo_y_puede_encenderlo(self, client, auth_superadmin, db, org, _catalogo):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "ULTRA_PLUS"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/modules", headers=auth_superadmin)
        por_clave = {m["key"]: m for m in r.json()}
        assert por_clave["pos"]["estado"] == "disponible"
        assert por_clave["commissions"]["estado"] == "oculto"
        assert por_clave["appointments"]["estado"] == "en_construccion"
        # No se esconde ni se bloquea: el superadministrador lo sigue encendiendo.
        r = client.patch(
            f"/api/platform/organizations/{org.id}/modules/commissions?enable=true", headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text

    def test_catalogo_de_plataforma_trae_estado(self, client, auth_superadmin, _catalogo):
        cat = {m["key"]: m for m in client.get("/api/platform/modules/catalog", headers=auth_superadmin).json()}
        assert cat["quotes"]["estado"] == "disponible" and cat["invoicing"]["estado"] == "en_construccion"

    def test_el_upsell_no_recomienda_lo_que_no_esta_construido(self, client, auth_superadmin, db, org, _catalogo):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/upsell-recommendations", headers=auth_superadmin)
        assert r.status_code == 200, r.text
        recs = {x["module_key"] for x in r.json()["recommendations"]}
        assert "quotes" in recs and "purchasing" in recs
        assert not (recs & set(em.no_disponibles())), sorted(recs & set(em.no_disponibles()))
