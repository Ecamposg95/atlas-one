"""La propina es de gastronomía: el preset la siembra, el módulo la manda.

El dueño lo pidió así el 24/09/26. Se implementa con un módulo, no mirando el
preset, para que una cafetería de otra cartera pueda prenderla sin tocar código.
"""
from scripts.init_presets_v2 import MODULES_CATALOG, PRESETS

GASTRO = {"ATLAS_ONE_GASTRO", "ATLAS_ONE_RESTAURANT", "ATLAS_ONE_CAFE", "ATLAS_ONE_BAR"}


def _mods(preset_id):
    return next(p["mods"] for p in PRESETS if p["id"] == preset_id)


def test_tips_existe_en_el_catalogo_de_modulos():
    assert "tips" in {m[0] for m in MODULES_CATALOG}


def test_los_presets_gastro_nacen_con_propina():
    for pid in GASTRO:
        assert "tips" in _mods(pid), f"{pid} debería traer propina"


def test_mostrador_y_boutique_no_nacen_con_propina():
    for pid in ("ATLAS_POS", "ATLAS_POS_BOUTIQUE"):
        assert "tips" not in _mods(pid), f"{pid} no es un giro con propina"


# --- El backfill: las tiendas gastro que YA existían también reciben la propina ---
# `apply_industry_preset` solo corre al dar de alta la organización, así que sin
# backfill un restaurante vivo se quedaría sin propina al desplegar. La lista de
# `_backfill_gastro_modules` está escrita a mano y no deriva de PRESETS: sin esta
# prueba, borrar "tips" de ahí no pondría roja ninguna otra.

from app.modules.tenants.models import IndustryType, Organization  # noqa: E402
from app.services.capabilities_service import get_organization_capabilities  # noqa: E402
from scripts.init_presets_v2 import seed_modules_and_presets  # noqa: E402


def test_el_backfill_enciende_la_propina_en_las_tiendas_gastro_que_ya_existian(db):
    gastro = [
        Organization(name=f"Vieja {i.name}", status="ACTIVE", industry_type=i)
        for i in (IndustryType.ATLAS_ONE_RESTAURANT, IndustryType.ATLAS_ONE_CAFE,
                  IndustryType.ATLAS_ONE_BAR, IndustryType.ATLAS_ONE_GASTRO)
    ]
    db.add_all(gastro)
    db.commit()

    seed_modules_and_presets(db)

    for o in gastro:
        assert "tips" in get_organization_capabilities(db, o.id), o.name


def test_el_backfill_no_le_da_propina_a_una_tienda_de_mostrador(db):
    tienda = Organization(name="Mostrador viejo", status="ACTIVE",
                          industry_type=IndustryType.ATLAS_POS)
    db.add(tienda)
    db.commit()

    seed_modules_and_presets(db)

    assert "tips" not in get_organization_capabilities(db, tienda.id)
