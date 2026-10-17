"""Qué campos del formulario de producto ve cada giro (principio 3 del mega plan)."""
from app.modules.products.campos import CAMPOS_FICHA, campos_producto
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
    db.commit()
    r = client.get("/api/users/me/context",
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert "campos_producto" in cuerpo
    assert "gender" in cuerpo["campos_producto"]["visibles"]
    assert cuerpo["campos_producto"]["ocultos"] == []
