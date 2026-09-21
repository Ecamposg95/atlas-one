"""Ficha boutique: genero/modelo/material, nombre de venta y SKU sugerido.

El dueño de la boutique captura "Chamarra" con marca "Louis Vuitton" y modelo
"mezclilla"; lo que tiene que leer el cajero en el POS, la ficha, la etiqueta y
el ticket es **"Louis Vuitton · Chamarra mezclilla · Talla M"** — la marca
primero, que es como se pide la prenda en el mostrador.

Regla de oro del archivo: un producto SIN marca ni modelo se sigue llamando
exactamente como hoy, aqui y en el renglon del ticket (`Nombre` / `Nombre (M)`).
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.organization import Organization
from app.models.products import Brand, ProductVariant
from app.modules.products.sale_name import (
    GENDERS,
    sale_name,
    sku_sugerido,
    variant_sale_name,
)
from app.routers.sales import _line_description
from conftest import _make_product


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


# ── 1. Nombre de venta del producto ──────────────────────────────────────────
class TestSaleName:
    def test_marca_primero_y_modelo_pegado_al_nombre(self):
        assert sale_name("Louis Vuitton", "Chamarra", "mezclilla") == \
            "Louis Vuitton · Chamarra mezclilla"

    def test_sin_marca_es_nombre_y_modelo(self):
        assert sale_name(None, "Chamarra", "mezclilla") == "Chamarra mezclilla"

    def test_sin_marca_ni_modelo_es_el_nombre_de_hoy(self):
        assert sale_name(None, "Chamarra", None) == "Chamarra"
        assert sale_name("", "Chamarra", "  ") == "Chamarra"

    def test_sin_modelo_pero_con_marca(self):
        assert sale_name("Gucci", "Playera", None) == "Gucci · Playera"

    def test_colapsa_espacios_de_captura(self):
        assert sale_name("  Gucci ", " Playera  cuello  V ", None) == \
            "Gucci · Playera cuello V"


# ── 2. Nombre de venta de la variante ────────────────────────────────────────
class TestVariantSaleName:
    def test_marca_nombre_modelo_y_talla(self):
        assert variant_sale_name("Louis Vuitton", "Chamarra", "mezclilla", None, "M") == \
            "Louis Vuitton · Chamarra mezclilla · Talla M"

    def test_color_y_talla_juntos(self):
        assert variant_sale_name("Louis Vuitton", "Chamarra", None, "Beige", "M") == \
            "Louis Vuitton · Chamarra · Beige, Talla M"

    def test_solo_color(self):
        assert variant_sale_name("Gucci", "Playera", None, "Beige", None) == \
            "Gucci · Playera · Beige"

    def test_sin_atributos_es_el_nombre_de_venta(self):
        assert variant_sale_name("Gucci", "Playera", None, None, None) == "Gucci · Playera"

    def test_sin_marca_ni_modelo_conserva_el_formato_de_hoy(self):
        """El ticket de hoy dice "Playera (M)"; sin marca ni modelo no cambia."""
        assert variant_sale_name(None, "Playera", None, None, "M") == "Playera (M)"
        assert variant_sale_name(None, "Playera", None, "Rojo", "M") == "Playera (Rojo / M)"
        assert variant_sale_name(None, "Playera", None, None, None) == "Playera"


# ── 3. SKU sugerido ──────────────────────────────────────────────────────────
class TestSkuSugerido:
    def test_marca_de_dos_palabras_usa_iniciales(self):
        assert sku_sugerido("Louis Vuitton", "Chamarra", "Mezclilla", "Beige", "M") == \
            "LV-CHAM-MEZ-BEI-M"

    def test_marca_de_una_palabra_usa_tres_letras_y_omite_vacios(self):
        assert sku_sugerido("Gucci", "Pantalón formal", None, None, "32") == "GUC-PANT-32"

    @pytest.mark.parametrize("marca,esperado", [
        ("Chrome Hearts", "CH"),
        ("Dolce & Gabbana", "DG"),
        ("Tiffany & Co.", "TC"),
        ("Amiri", "AMI"),
    ])
    def test_iniciales_de_marca(self, marca, esperado):
        assert sku_sugerido(marca, "Playera", None, None, None) == f"{esperado}-PLAY"

    def test_acentos_y_signos_fuera(self):
        assert sku_sugerido(None, "Suéter", None, None, None) == "SUET"
        assert sku_sugerido(None, "Tenis", None, None, "26.5") == "TENI-265"

    def test_sin_nada_es_cadena_vacia(self):
        assert sku_sugerido(None, "", None, None, None) == ""


# ── 4. Los tres campos en la ficha ───────────────────────────────────────────
class TestFichaDelProducto:
    def _alta(self, client, org, auth, **extra):
        body = {
            "name": "Chamarra", "sku": "CHAM-1", "price": "4000", "cost": "2000",
        }
        body.update(extra)
        return client.post("/api/products/", json=body, headers=_h(auth, org))

    def test_alta_persiste_genero_modelo_y_material(self, client, db, org, branch_a, auth_admin):
        r = self._alta(client, org, auth_admin, gender="MUJER", model="mezclilla",
                       material="Algodón", target_branch_ids=[branch_a.id])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert (cuerpo["gender"], cuerpo["model"], cuerpo["material"]) == \
            ("MUJER", "mezclilla", "Algodón")

    def test_genero_invalido_es_422(self, client, org, branch_a, auth_admin):
        r = self._alta(client, org, auth_admin, gender="DAMA",
                       target_branch_ids=[branch_a.id])
        assert r.status_code == 422, r.text

    def test_generos_validos(self):
        assert GENDERS == ("HOMBRE", "MUJER", "UNISEX", "NINO")

    def test_get_devuelve_sale_name_del_producto_y_de_cada_talla(
        self, client, db, org, branch_a, auth_admin
    ):
        marca = Brand(name="Louis Vuitton", organization_id=org.id)
        db.add(marca); db.flush()
        r = self._alta(client, org, auth_admin, model="mezclilla", brand_id=marca.id,
                       color="Beige", size="M", target_branch_ids=[branch_a.id],
                       extra_variants=[{"color": "Beige", "size": "L"}])
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]

        g = client.get(f"/api/products/{pid}", headers=_h(auth_admin, org))
        assert g.status_code == 200, g.text
        cuerpo = g.json()
        assert cuerpo["sale_name"] == "Louis Vuitton · Chamarra mezclilla"
        nombres = {v["size"]: v["sale_name"] for v in cuerpo["variants"]}
        assert nombres == {
            "M": "Louis Vuitton · Chamarra mezclilla · Beige, Talla M",
            "L": "Louis Vuitton · Chamarra mezclilla · Beige, Talla L",
        }

    def test_producto_sin_marca_ni_modelo_se_llama_como_hoy(
        self, client, db, org, branch_a, auth_admin
    ):
        p, v = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        db.commit()
        g = client.get(f"/api/products/{p.id}", headers=_h(auth_admin, org))
        assert g.status_code == 200, g.text
        assert g.json()["sale_name"] == "Gorra"
        assert g.json()["variants"][0]["sale_name"] == "Gorra"

    def test_update_cambia_los_tres_campos(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        db.commit()
        r = client.put(f"/api/products/{p.id}", json={
            "gender": "UNISEX", "model": "clásica", "material": "Lana",
        }, headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(p)
        assert (p.gender, p.model, p.material) == ("UNISEX", "clásica", "Lana")
        assert r.json()["sale_name"] == "Gorra clásica"


# ── 5. Sugerencia de SKU por HTTP ────────────────────────────────────────────
class TestSkuSuggestEndpoint:
    def test_sugiere_y_marca_disponible(self, client, org, auth_admin):
        r = client.get("/api/products/sku-suggest", params={
            "brand": "Louis Vuitton", "name": "Chamarra", "model": "Mezclilla",
            "color": "Beige", "size": "M",
        }, headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json() == {"sku": "LV-CHAM-MEZ-BEI-M", "available": True}

    def test_no_disponible_si_ya_existe_en_la_organizacion(
        self, client, db, org, branch_a, auth_admin
    ):
        _make_product(db, org, "Chamarra", "LV-CHAM", 4000, [(branch_a.id, True)])
        db.commit()
        r = client.get("/api/products/sku-suggest", params={
            "brand": "Louis Vuitton", "name": "Chamarra",
        }, headers=_h(auth_admin, org))
        assert r.json() == {"sku": "LV-CHAM", "available": False}

    def test_el_mismo_sku_en_otra_organizacion_sigue_disponible(
        self, client, db, org, auth_admin
    ):
        otra = Organization(name="Otra Tienda", status="ACTIVE")
        db.add(otra); db.flush()
        _make_product(db, otra, "Chamarra", "LV-CHAM", 4000)
        db.commit()
        r = client.get("/api/products/sku-suggest", params={
            "brand": "Louis Vuitton", "name": "Chamarra",
        }, headers=_h(auth_admin, org))
        assert r.json() == {"sku": "LV-CHAM", "available": True}


# ── 6. Busqueda por marca y por modelo ───────────────────────────────────────
class TestBusquedaPorMarcaYModelo:
    @pytest.fixture()
    def catalogo(self, db, org, branch_a):
        marca = Brand(name="Louis Vuitton", organization_id=org.id)
        db.add(marca); db.flush()
        p, v = _make_product(db, org, "Chamarra", "CH-1", 4000, [(branch_a.id, True)])
        p.brand_id = marca.id
        p.model = "mezclilla"
        _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        db.commit()
        return p

    def test_encuentra_por_marca(self, client, org, auth_cajero_a, catalogo):
        r = client.get("/api/products/pos/search?q=vuitton", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert [p["name"] for p in r.json()] == ["Chamarra"]

    def test_encuentra_por_modelo(self, client, org, auth_cajero_a, catalogo):
        r = client.get("/api/products/pos/search?q=mezcli", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert [p["name"] for p in r.json()] == ["Chamarra"]

    def test_sigue_encontrando_por_nombre(self, client, org, auth_cajero_a, catalogo):
        r = client.get("/api/products/pos/search?q=gorra", headers=_h(auth_cajero_a, org))
        assert [p["name"] for p in r.json()] == ["Gorra"]


# ── 7. Renglon de la venta (lo que se congela en sales_lines.description) ────
def _variant(nombre, *, marca=None, modelo=None, color=None, talla=None, etiqueta=None):
    from app.modules.products.variant_label import variant_label
    producto = SimpleNamespace(
        name=nombre,
        model=modelo,
        brand_id="b1" if marca else None,
        brand=SimpleNamespace(name=marca) if marca else None,
    )
    return SimpleNamespace(
        product=producto, color=color, size=talla,
        variant_name=etiqueta if etiqueta is not None else variant_label(color, talla),
    )


class TestLineDescription:
    def test_sin_marca_ni_modelo_con_talla_sigue_dando_nombre_talla(self):
        assert _line_description(_variant("Playera", talla="M")) == "Playera (M)"

    def test_sin_nada_es_el_nombre(self):
        assert _line_description(_variant("Playera")) == "Playera"

    def test_etiqueta_libre_heredada_se_respeta(self):
        """Catálogo viejo: `variant_name` a mano y color/talla vacíos."""
        assert _line_description(_variant("Refresco", etiqueta="600ml")) == "Refresco (600ml)"

    def test_con_marca_usa_el_nombre_de_venta(self):
        v = _variant("Chamarra", marca="Louis Vuitton", modelo="mezclilla", talla="M")
        assert _line_description(v) == "Louis Vuitton · Chamarra mezclilla · Talla M"

    def test_con_marca_sin_talla(self):
        v = _variant("Playera", marca="Gucci")
        assert _line_description(v) == "Gucci · Playera"
