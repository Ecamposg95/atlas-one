"""El módulo `crm` entra a los presets de mostrador (ATLAS_POS y boutique).

`crm` llevaba en el catálogo desde siempre pero fuera de los dos presets de
mostrador, así que la entrada "Clientes" del menú (`module: 'crm'` en
navConfig.ts) no se veía en NINGUNA tienda POS. Al sumarlo hace falta además el
backfill: `apply_industry_preset` solo corre al dar de alta la organización, y
el router de clientes ahora exige `require_module("crm")` — sin la fila en
`organization_modules` las tiendas que ya existían verían 403.
"""
from app.models.modules import IndustryPreset, OrganizationModule
from app.modules.tenants.models import IndustryType, Organization
from app.services.capabilities_service import (
    INDUSTRY_PRESETS,
    apply_industry_preset,
    get_organization_capabilities,
)
from scripts.init_presets_v2 import seed_modules_and_presets


def _preset(db, industry: str) -> IndustryPreset:
    row = db.query(IndustryPreset).filter(IndustryPreset.industry_type == industry).first()
    assert row is not None, f"falta el preset {industry}"
    return row


def test_los_dos_presets_de_mostrador_traen_crm(db):
    seed_modules_and_presets(db)
    assert "crm" in _preset(db, "ATLAS_POS").modules
    assert "crm" in _preset(db, "ATLAS_POS_BOUTIQUE").modules


def test_el_preset_de_retail_no_repite_crm(db):
    """`crm` se agrega por preset y no a ATLAS_POS_MODS justamente para que el
    preset de retail —que ya lo agregaba por su cuenta— no lo liste dos veces."""
    seed_modules_and_presets(db)
    mods = _preset(db, "ATLAS_ONE_RETAIL").modules
    assert mods.count("crm") == 1


def test_el_fallback_en_codigo_dice_lo_mismo_que_el_seed(db):
    """`capabilities_service.INDUSTRY_PRESETS` solo se consulta si la tabla
    `industry_presets` viene vacía; si divergen, una base nueva nace sin CRM."""
    assert "crm" in INDUSTRY_PRESETS[IndustryType.ATLAS_POS]
    assert "crm" in INDUSTRY_PRESETS[IndustryType.ATLAS_POS_BOUTIQUE]


def test_una_tienda_nueva_nace_con_crm_encendido(db, org):
    seed_modules_and_presets(db)
    apply_industry_preset(db, org.id, IndustryType.ATLAS_POS_BOUTIQUE)
    assert "crm" in get_organization_capabilities(db, org.id)


def test_el_backfill_enciende_crm_en_las_tiendas_que_ya_existian(db):
    """Eleven Fashion, Novedades Kaory, Ginebra e Imaltzin: dadas de alta antes
    de este cambio, tienen el preset pero no la fila del módulo."""
    boutique = Organization(name="Boutique vieja", status="ACTIVE",
                            industry_type=IndustryType.ATLAS_POS_BOUTIQUE)
    pos = Organization(name="Tienda vieja", status="ACTIVE",
                       industry_type=IndustryType.ATLAS_POS)
    db.add_all([boutique, pos])
    db.commit()

    seed_modules_and_presets(db)

    for o in (boutique, pos):
        assert "crm" in get_organization_capabilities(db, o.id), o.name


def test_el_backfill_es_idempotente_y_no_reenciende_lo_apagado(db):
    """Correr el seed dos veces no duplica la fila, y si el cliente apagó el
    módulo a mano el backfill respeta su decisión (es aditivo, no un reset)."""
    tienda = Organization(name="Tienda vieja", status="ACTIVE",
                          industry_type=IndustryType.ATLAS_POS)
    db.add(tienda)
    db.commit()

    seed_modules_and_presets(db)
    filas = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == tienda.id,
        OrganizationModule.module_key == "crm",
    ).all()
    assert len(filas) == 1

    filas[0].is_enabled = False
    db.commit()

    seed_modules_and_presets(db)
    db.expire_all()
    filas = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == tienda.id,
        OrganizationModule.module_key == "crm",
    ).all()
    assert len(filas) == 1
    assert filas[0].is_enabled is False
