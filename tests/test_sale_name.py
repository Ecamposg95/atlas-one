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

    def test_etiqueta_escrita_a_mano_del_catalogo_viejo(self):
        """Sin color ni talla, la etiqueta guardada es lo unico que distingue
        dos variantes viejas: "600ml" y "2L" del mismo refresco."""
        assert variant_sale_name(None, "Refresco", None, None, None, "600ml") == "Refresco (600ml)"
        assert variant_sale_name(None, "Refresco", None, None, None, "2L") == "Refresco (2L)"

    def test_la_etiqueta_neutra_no_ensucia_el_nombre(self):
        for neutra in ("Estándar", "estandar", "Default", "  ", None):
            assert variant_sale_name(None, "Playera", None, None, None, neutra) == "Playera"

    def test_color_y_talla_ganan_a_la_etiqueta_guardada(self):
        assert variant_sale_name(None, "Playera", None, None, "M", "vieja") == "Playera (M)"

    def test_con_marca_la_etiqueta_vieja_no_se_usa(self):
        assert variant_sale_name("Gucci", "Playera", None, None, None, "600ml") == "Gucci · Playera"


class TestMarcaNeutra:
    """"Sin marca" es una marca real en el catalogo de varias tiendas (la crean
    para poder llenar el campo). No debe encabezar el nombre de venta ni salir
    como renglon de marca en el ticket."""

    def test_sin_marca_no_encabeza_el_nombre(self):
        assert sale_name("Sin marca", "Chamarra", None) == "Chamarra"
        assert sale_name("Sin Marca", "Playera", "manga larga") == "Playera manga larga"
        assert variant_sale_name("sin marca", "Playera", None, None, "M") == "Playera (M)"

    def test_una_marca_real_si(self):
        assert sale_name("Gucci", "Chamarra", None) == "Gucci · Chamarra"


# ── 3. SKU sugerido ──────────────────────────────────────────────────────────
class TestSkuSugerido:
    def test_marca_de_dos_palabras_usa_iniciales(self):
        assert sku_sugerido("Louis Vuitton", "Chamarra", "Mezclilla", "Beige", "M") == \
            "LV-CHAM-MEZ-BEI-M"

    def test_marca_de_una_palabra_usa_tres_letras_y_omite_vacios(self):
        assert sku_sugerido("Gucci", "Pantalón formal", None, None, "32") == "GUC-PANT-F-32"

    def test_palabras_extra_del_nombre_van_como_iniciales(self):
        # Sin esto, las blusas de manga corta, larga y sin mangas de la misma
        # marca colisionaban en PRA-BLUS.
        assert sku_sugerido("Prada", "Blusa manga corta", None, None, None) == "PRA-BLUS-MC"
        assert sku_sugerido("Prada", "Blusa sin mangas", None, None, None) == "PRA-BLUS-SM"
        assert sku_sugerido("Loro Piana", "Playera premium cuello redondo", None, None, "CH") == "LP-PLAY-PCR-CH"
        assert sku_sugerido(None, "Pantalón de pants", None, None, None) == "PANT-P"

    def test_genero_mujer_y_nino_se_marcan_hombre_no(self):
        assert sku_sugerido("Gucci", "Pantalón", None, None, None, gender="MUJER") == "GUC-PANT-MUJ"
        assert sku_sugerido("Gucci", "Pantalón", "Mezclilla", None, None, gender="HOMBRE") == "GUC-PANT-MEZ"
        assert sku_sugerido("Gucci", "Pantalón", None, None, None, gender="UNISEX") == "GUC-PANT"
        assert sku_sugerido("Gucci", "Playera", None, None, "4", gender="nino") == "GUC-PLAY-NIN-4"

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

    def test_dos_variantes_viejas_se_distinguen_por_su_etiqueta(
        self, client, db, org, branch_a, auth_admin
    ):
        """Catalogo viejo: etiqueta a mano, sin color ni talla. En pantalla se
        tienen que seguir llamando distinto (el ticket ya lo hacia)."""
        from app.models.products import ProductVariant
        p, v = _make_product(db, org, "Refresco", "REF-600", 20, [(branch_a.id, True)])
        v.variant_name = "600ml"
        hermana = ProductVariant(
            product_id=p.id, sku="REF-2L", variant_name="2L",
            price=Decimal("35"), cost=Decimal("20"), organization_id=org.id,
        )
        db.add(hermana)
        db.commit()

        g = client.get(f"/api/products/{p.id}", headers=_h(auth_admin, org))
        assert g.status_code == 200, g.text
        nombres = {x["sku"]: x["sale_name"] for x in g.json()["variants"]}
        assert nombres == {"REF-600": "Refresco (600ml)", "REF-2L": "Refresco (2L)"}
        assert g.json()["sale_name"] == "Refresco"

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

    def test_el_escaneo_exacto_no_busca_por_marca_ni_modelo(
        self, client, db, org, auth_cajero_a, catalogo
    ):
        """`exact=true` compara SOLO codigos: el `or_` de marca/modelo vive en
        la rama parcial y no puede aflojar el escaneo del pasillo."""
        r = client.get("/api/products/pos/search?q=vuitton&exact=true",
                       headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert r.json() == []
        r2 = client.get("/api/products/pos/search?q=mezclilla&exact=true",
                        headers=_h(auth_cajero_a, org))
        assert r2.json() == []
        # El SKU exacto de esa misma prenda si la encuentra.
        r3 = client.get("/api/products/pos/search?q=CH-1&exact=true",
                        headers=_h(auth_cajero_a, org))
        assert [p["name"] for p in r3.json()] == ["Chamarra"]


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


# ── 8. Estilo de linea del ticket (configuracion de la organizacion) ────────
class TestEstiloDeLineaDelTicket:
    def test_arranca_compacto(self, client, org, auth_admin):
        r = client.get("/api/organization/", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json()["ticket_line_style"] == "compact"

    def test_admin_lo_enciende(self, client, db, org, auth_admin):
        r = client.put("/api/organization/", json={"ticket_line_style": "detailed"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.ticket_line_style == "detailed"

    def test_valor_invalido_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/", json={"ticket_line_style": "bonito"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text

    def test_null_no_borra_la_columna(self, client, db, org, auth_admin):
        """La columna es NOT NULL y el panel manda el objeto completo: un
        `null` es "no tocar", no un 500 al commitear."""
        org.ticket_line_style = "detailed"
        db.commit()
        r = client.put("/api/organization/", json={"ticket_line_style": None},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.ticket_line_style == "detailed"


# ── 9. Duplicar y buscar conservan la ficha ─────────────────────────────────
class TestDuplicarYBuscar:
    @pytest.fixture()
    def chamarra(self, db, org, branch_a, auth_admin, client):
        marca = Brand(name="Louis Vuitton", organization_id=org.id)
        db.add(marca); db.flush()
        p, v = _make_product(db, org, "Chamarra", "CH-1", 4000, [(branch_a.id, True)])
        p.brand_id, p.model, p.gender, p.material = marca.id, "mezclilla", "MUJER", "Algodón"
        db.commit()
        return p

    def test_la_copia_conserva_genero_modelo_y_material(
        self, client, db, org, chamarra, auth_admin
    ):
        r = client.post(f"/api/products/{chamarra.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        copia = r.json()
        assert (copia["gender"], copia["model"], copia["material"]) == \
            ("MUJER", "mezclilla", "Algodón")
        assert copia["sale_name"] == "Louis Vuitton · Chamarra (copia) mezclilla"

    def test_la_busqueda_de_catalogo_trae_el_nombre_de_venta(
        self, db, org, chamarra, admin_user
    ):
        """`search_products` no pasa por `_compute_product_read`: si no llenara
        `sale_name`, esa pantalla llamaria distinto a la misma prenda.

        Se llama la funcion directo y no por HTTP: `GET /api/products/search`
        lo tapa `GET /api/products/{product_id}` del router `core`, que se
        monta antes (bug preexistente de orden de rutas, fuera de alcance).
        """
        from app.modules.products.router.search import search_products

        filas = search_products(q="chamarra", db=db, current_user=admin_user, org_id=org.id)
        fila = next(x for x in filas if x.name == "Chamarra")
        assert fila.sale_name == "Louis Vuitton · Chamarra mezclilla"
        assert fila.variants[0].sale_name == "Louis Vuitton · Chamarra mezclilla"
