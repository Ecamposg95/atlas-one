"""El modulo `variants` gobierna la UI de color/talla. Debe existir en el
catalogo, venir en el preset boutique y NO en ATLAS_POS."""
from app.models.modules import IndustryPreset, Module
from app.modules.tenants.models import IndustryType
from app.services.capabilities_service import (
    apply_industry_preset, get_organization_capabilities, seed_global_modules,
)
from scripts.init_presets_v2 import seed_modules_and_presets


def _preset(db, industry):
    row = db.query(IndustryPreset).filter(IndustryPreset.industry_type == industry).first()
    assert row is not None, industry
    return row


def test_catalogo_v2_tiene_variants(db):
    seed_modules_and_presets(db)
    assert db.query(Module).filter(Module.key == "variants").first() is not None


def test_boutique_trae_variants_y_atlas_pos_no(db):
    seed_modules_and_presets(db)
    assert "variants" in _preset(db, "ATLAS_POS_BOUTIQUE").modules
    assert "variants" not in _preset(db, "ATLAS_POS").modules


def test_aplicar_boutique_activa_variants(db, org):
    seed_modules_and_presets(db)
    apply_industry_preset(db, org.id, IndustryType.ATLAS_POS_BOUTIQUE)
    assert "variants" in get_organization_capabilities(db, org.id)


def test_catalogo_de_arranque_tiene_variants(db):
    seed_global_modules(db)
    assert db.query(Module).filter(Module.key == "variants").first() is not None
