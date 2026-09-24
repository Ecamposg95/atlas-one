"""El catálogo declara qué funciones se pueden apagar y de qué módulo dependen.

Es una LISTA BLANCA: lo que no está aquí está siempre encendido. Por eso
administrar usuarios no aparece — el módulo `users` está apagado en las cuatro
tiendas reales y nadie puede quedarse sin dar de alta cajeras.
"""
from app.capacidades import CATALOGO, CLAVES, modulo_de, resolver


def test_cada_funcion_apunta_a_un_modulo_que_existe():
    from scripts.init_presets_v2 import MODULES_CATALOG
    claves_reales = {m[0] for m in MODULES_CATALOG}
    for f in CATALOGO:
        assert f["modulo"] in claves_reales, (
            f"la función '{f['clave']}' exige el módulo '{f['modulo']}', que no existe "
            f"en el catálogo de módulos"
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
