"""Qué campos del formulario de producto ve cada giro (principio 3 del mega plan)."""
from app.modules.products.campos import CAMPOS_FICHA, OCULTOS_BASICO, campos_producto
from app.modules.tenants.models import IndustryType


def test_boutique_ve_la_ficha():
    r = campos_producto("ATLAS_POS_BOUTIQUE", ["core", "catalog", "variants"])
    assert set(CAMPOS_FICHA) <= set(r["visibles"])
    assert r["ocultos"] == []
    assert "variants" in r["visibles"]


def test_pos_normal_esconde_la_ficha_y_sin_modulo_no_hay_variantes():
    r = campos_producto("ATLAS_POS", ["core", "catalog"])
    assert r["ocultos"] == list(CAMPOS_FICHA)
    assert not (set(CAMPOS_FICHA) & set(r["visibles"]))
    assert "variants" not in r["visibles"]
    # Lo básico siempre va.
    for clave in ("name", "sku", "price", "cost", "packaging_units", "prices"):
        assert clave in r["visibles"]


def test_sin_preset_falla_abierto():
    r = campos_producto(None, [])
    assert r["ocultos"] == []
    assert set(CAMPOS_FICHA) <= set(r["visibles"])


def test_contexto_trae_campos_producto(client, db, auth_admin, org):
    org.industry_type = IndustryType.ATLAS_POS_BOUTIQUE
    # De paga: la org de conftest nace FREE y desde el modo básico eso ya
    # esconde campos. Esta prueba mira la ficha boutique, no el perfil.
    org.plan = "ULTRA_PLUS"
    db.commit()
    r = client.get("/api/users/me/context",
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert "campos_producto" in cuerpo
    assert "gender" in cuerpo["campos_producto"]["visibles"]
    assert cuerpo["campos_producto"]["ocultos"] == []


def test_basico_esconde_marca_descripcion_unidad_foto_tasa_empaques_y_variantes():
    r = campos_producto("ATLAS_POS", ["core", "catalog", "variants"], "basico")
    for clave in OCULTOS_BASICO:
        assert clave in r["ocultos"]
        assert clave not in r["visibles"]
    # El formulario corto del spec §4.2 (+ SKU, que la API exige).
    for clave in ("name", "sku", "barcode", "department_id", "price", "cost",
                  "has_iva", "initial_stock", "prices"):
        assert clave in r["visibles"]
    # La ficha sigue oculta primero y nada se repite.
    assert r["ocultos"][:3] == list(CAMPOS_FICHA)
    assert len(r["ocultos"]) == len(set(r["ocultos"]))


def test_completo_es_el_default_y_no_cambia_nada():
    for preset in ("ATLAS_POS", "ATLAS_POS_BOUTIQUE", None):
        assert campos_producto(preset, ["core", "variants"]) == campos_producto(preset, ["core", "variants"], "completo")


def test_basico_aplica_aunque_no_haya_preset():
    r = campos_producto(None, [], "basico")
    assert "brand_id" in r["ocultos"]
    assert set(CAMPOS_FICHA) <= set(r["visibles"])  # la ficha sigue fallando abierto


def test_contexto_de_una_free_trae_los_ocultos_de_basico(client, db, auth_admin, org):
    org.industry_type = IndustryType.ATLAS_POS
    org.plan = "FREE"
    db.commit()
    cuerpo = client.get("/api/users/me/context",
                        headers={**auth_admin, "X-Organization-ID": str(org.id)}).json()
    assert cuerpo["perfil_ui"] == "basico"
    assert "brand_id" in cuerpo["campos_producto"]["ocultos"]
    assert "description" in cuerpo["campos_producto"]["ocultos"]


def test_contexto_de_una_free_forzada_a_completo_no_esconde_de_mas(client, db, auth_admin, org):
    """Review Focus #4: forzar completo devuelve el formulario entero."""
    org.industry_type = IndustryType.ATLAS_POS
    org.plan = "FREE"
    org.perfil_ui = "completo"
    db.commit()
    cuerpo = client.get("/api/users/me/context",
                        headers={**auth_admin, "X-Organization-ID": str(org.id)}).json()
    assert cuerpo["campos_producto"]["ocultos"] == list(CAMPOS_FICHA)
