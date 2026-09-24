"""El catálogo declara qué funciones se pueden apagar y de qué módulo dependen.

Es una LISTA BLANCA: lo que no está aquí está siempre encendido. Por eso
administrar usuarios no aparece — el módulo `users` está apagado en las cuatro
tiendas reales y nadie puede quedarse sin dar de alta cajeras.
"""
import inspect
import re

from app.capacidades import CATALOGO, CLAVES, modulo_de, resolver


def _claves_de_modulos_reales() -> set[str]:
    """Une los dos catálogos de módulos que coexisten en el repo (a propósito).

    `scripts/init_presets_v2.py::MODULES_CATALOG` es el que siembra
    `railway_init.py` en cada DESPLIEGUE. `app/services/capabilities_service.py`
    trae otro catálogo propio (`seed_global_modules`), que se siembra en cada
    ARRANQUE de la aplicación (`app/main.py`, evento `startup`). Los dos están
    vivos a la vez — no es un catálogo con nombres viejos sin usar — así que un
    módulo cuenta como "real" si aparece en cualquiera de los dos. Validar solo
    contra uno de ellos da falsos fallos: una función podría exigir un módulo
    que sí se siembra al arrancar pero no está en el de despliegue (p. ej.
    `invoicing`), o viceversa. Unificar ambos catálogos es trabajo de otra ola
    — toca el arranque de la aplicación, no las capacidades.
    """
    from scripts.init_presets_v2 import MODULES_CATALOG
    claves_despliegue = {m[0] for m in MODULES_CATALOG}

    # No se ejecuta seed_global_modules (evitaría depender de una DB en esta
    # prueba); se lee de su propia fuente qué claves declara, resolviendo cada
    # constante MOD_* contra el módulo real.
    from app.services import capabilities_service
    fuente = inspect.getsource(capabilities_service.seed_global_modules)
    constantes = re.findall(r'"key":\s*(MOD_\w+)', fuente)
    claves_arranque = {getattr(capabilities_service, c) for c in constantes}

    return claves_despliegue | claves_arranque


def test_cada_funcion_apunta_a_un_modulo_que_existe():
    claves_reales = _claves_de_modulos_reales()
    for f in CATALOGO:
        assert f["modulo"] in claves_reales, (
            f"la función '{f['clave']}' exige el módulo '{f['modulo']}', que no existe "
            f"en ninguno de los dos catálogos de módulos (init_presets_v2 ni "
            f"capabilities_service)"
        )


def test_cada_entrada_trae_los_campos_obligatorios():
    for f in CATALOGO:
        for campo in ("clave", "modulo", "nombre", "donde", "ayuda"):
            assert f.get(campo), f"a '{f.get('clave', '?')}' le falta '{campo}'"
        assert isinstance(f["donde"], list) and f["donde"]


def test_no_hay_claves_repetidas():
    claves = [f["clave"] for f in CATALOGO]
    assert len(claves) == len(set(claves))


def test_administrar_usuarios_no_es_apagable():
    """Lista blanca: si `users` entrara al catálogo, las cuatro tiendas reales
    —que lo tienen apagado— se quedarían sin poder dar de alta una cajera."""
    assert all(f["modulo"] != "users" for f in CATALOGO)


def test_modulo_de_responde_la_clave_correcta():
    assert modulo_de("propina") == "tips"
    assert modulo_de("no-existe") is None


def test_resolver_devuelve_solo_lo_que_la_tienda_puede():
    assert resolver({"core", "pos", "tips"}) == ["propina"]
    assert resolver({"core", "pos"}) == []
    assert resolver({"core", "pos", "tips", "invoicing"}) == ["factura", "propina"]


def test_claves_es_el_conjunto_de_claves():
    assert CLAVES == {f["clave"] for f in CATALOGO}
