"""Preset "Atlas POS Boutique": Atlas POS mas el modulo `scanner` para cajeros.

El modulo `scanner` gobierna si un cajero ve el Scanner de tienda en la barra
lateral. Debe existir en el catalogo, venir SOLO en el preset boutique (las
tiendas ATLAS_POS no cambian) y activarse al aplicar el preset a una org.
"""
from app.models.modules import IndustryPreset, Module
from app.modules.tenants.models import IndustryType
from app.services.capabilities_service import (
    apply_industry_preset,
    get_organization_capabilities,
    seed_global_modules,
)
from scripts.init_presets_v2 import ATLAS_POS_MODS, seed_modules_and_presets


def _preset(db, industry: str) -> IndustryPreset:
    row = db.query(IndustryPreset).filter(IndustryPreset.industry_type == industry).first()
    assert row is not None, f"falta el preset {industry}"
    return row


def test_boutique_industry_type_exists():
    assert IndustryType.ATLAS_POS_BOUTIQUE.value == "ATLAS_POS_BOUTIQUE"


def test_seed_boutique_preset_is_atlas_pos_plus_scanner(db):
    seed_modules_and_presets(db)
    assert db.query(Module).filter(Module.key == "scanner").first() is not None
    boutique = _preset(db, "ATLAS_POS_BOUTIQUE")
    assert "scanner" in boutique.modules
    assert set(ATLAS_POS_MODS) <= set(boutique.modules)
    assert boutique.is_deprecated is False


def test_seed_atlas_pos_does_not_get_scanner(db):
    """Las tiendas que ya operan con ATLAS_POS no deben cambiar."""
    seed_modules_and_presets(db)
    assert "scanner" not in _preset(db, "ATLAS_POS").modules


def test_apply_boutique_preset_enables_scanner_for_org(db, org):
    seed_modules_and_presets(db)
    apply_industry_preset(db, org.id, IndustryType.ATLAS_POS_BOUTIQUE)
    assert "scanner" in get_organization_capabilities(db, org.id)


def test_startup_catalog_includes_scanner(db):
    """`app/main.py` siembra este catalogo al arrancar; sin `scanner` ahi el
    FK de organization_modules rechaza el preset en una base nueva."""
    seed_global_modules(db)
    assert db.query(Module).filter(Module.key == "scanner").first() is not None
