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
