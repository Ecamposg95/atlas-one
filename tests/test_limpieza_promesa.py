"""Limpieza de la promesa comercial (2026-11-26, docs/presets/ESTADO-DE-MODULOS.md §4).

- Los presets que se venden no traen módulos sin construir.
- Los giros sin Agenda u órdenes de trabajo quedan «en preparación» (deprecated:
  fuera de los selectores, conservados para quien ya los usa).
- Las organizaciones de los presets legacy pasan a su sucesor v2 sin tocar sus módulos.
- Cajas y contenedores (`/api/logistics`) abre con `logistics` o con la clave vieja `warehouse`.
"""
import pytest

from app.models.modules import IndustryPreset, OrganizationModule
from app.models.organization import IndustryType, Organization
from app.services.estado_modulos import esta_disponible
from scripts.init_presets_v2 import seed_modules_and_presets

VENDIBLES = ["ATLAS_POS", "ATLAS_POS_BOUTIQUE", "ATLAS_ONE_RETAIL", "ATLAS_ONE_RESTAURANT",
             "ATLAS_ONE_CAFE", "ATLAS_ONE_BAR", "ATLAS_ONE_ENTERPRISE", "CUSTOM"]
EN_PREPARACION = ["ATLAS_ONE_BARBER", "ATLAS_ONE_BEAUTY_WELLNESS", "ATLAS_ONE_HEALTH", "ATLAS_ONE_SERVICES"]


def _preset(db, clave):
    return db.query(IndustryPreset).filter(IndustryPreset.industry_type == clave).one()


@pytest.mark.parametrize("clave", VENDIBLES)
def test_los_presets_que_se_venden_solo_traen_lo_construido(db, clave):
    seed_modules_and_presets(db)
    fila = _preset(db, clave)
    assert not fila.is_deprecated
    assert [m for m in fila.modules if not esta_disponible(m)] == []


@pytest.mark.parametrize("clave", EN_PREPARACION)
def test_los_giros_sin_agenda_quedan_en_preparacion(db, clave):
    seed_modules_and_presets(db)
    fila = _preset(db, clave)
    assert fila.is_deprecated and fila.display_name.endswith("(en preparación)")


def test_bar_ya_no_promete_comisiones(db):
    seed_modules_and_presets(db)
    assert "comisión" not in _preset(db, "ATLAS_ONE_BAR").description


def _sembrar(db):
    from app.services.capabilities_service import seed_global_modules
    seed_global_modules(db)          # trae `warehouse`
    seed_modules_and_presets(db)


def test_legacy_migra_al_sucesor_sin_tocar_modulos(db, org):
    _sembrar(db)
    otra = Organization(name="Gastro viejo", industry_type=IndustryType.ATLAS_ONE_GASTRO)
    db.add(otra); db.flush()
    db.add(OrganizationModule(organization_id=otra.id, module_key="commissions", is_enabled=True))
    org.industry_type = IndustryType.ATLAS_ONE_BEAUTY
    db.commit()

    seed_modules_and_presets(db)
    seed_modules_and_presets(db)  # idempotente

    db.refresh(org); db.refresh(otra)
    assert org.industry_type == IndustryType.ATLAS_ONE_BEAUTY_WELLNESS
    assert otra.industry_type == IndustryType.ATLAS_ONE_RESTAURANT
    # Lo encendido se queda encendido (aunque ya no se venda).
    assert db.query(OrganizationModule).filter_by(
        organization_id=otra.id, module_key="commissions", is_enabled=True).count() == 1


@pytest.mark.parametrize("claves, esperado", [
    ((), 403), (("logistics",), 200), (("warehouse",), 200), (("logistics", "warehouse"), 200),
])
def test_cajas_abre_con_logistics_o_con_la_clave_vieja(client, db, org, auth_gerente_a, claves, esperado):
    _sembrar(db)
    db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key.in_(["logistics", "warehouse"]),
    ).delete(synchronize_session=False)
    for k in claves:
        db.add(OrganizationModule(organization_id=org.id, module_key=k, is_enabled=True))
    db.commit()
    assert client.get("/api/logistics/boxes", headers=auth_gerente_a).status_code == esperado
