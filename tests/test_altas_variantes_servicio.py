"""`crear_variantes` vive en services y usa la misma regla de SKU que el alta."""
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.products import ProductVariant
from app.services.barcodes import es_codigo_interno


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestCrearVariantesDesdeServicio:
    def test_el_router_reexporta_la_misma_funcion(self):
        from app.modules.products.router import variants as router_variants
        from app.modules.products.services import variantes
        assert router_variants.crear_variantes is variantes.crear_variantes
        assert router_variants._pareja_repetida is variantes.pareja_repetida

    def test_sku_generado_que_choca_con_uno_archivado_es_409(self, client, db, org, branch_a, auth_admin):
        p, _ = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        p2, v2 = _make_product(db, org, "Vieja", "PLY-ROJO-M", 100, [(branch_a.id, True)])
        ahora = datetime.now(timezone.utc)
        p2.deleted_at = ahora; p2.is_active = False; v2.deleted_at = ahora
        db.flush()
        r = client.post(f"/api/products/{p.id}/variants",
                        json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]
        assert db.query(ProductVariant).filter(ProductVariant.product_id == p.id).count() == 1

    def test_hermana_recibe_codigo_interno_y_kardex_de_variante(self, client, db, org, branch_a, auth_admin):
        from app.models.inventory import InventoryMovement
        p, _ = _make_product(db, org, "Playera", "PLY2", 100, [(branch_a.id, True)])
        db.flush()
        r = client.post(f"/api/products/{p.id}/variants",
                        json={"variants": [{"color": "Azul", "size": "L", "initial_stock": "2"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 201, r.text
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "PLY2-AZUL-L").one()
        assert es_codigo_interno(org.id, nueva.barcode)
        mov = db.query(InventoryMovement).filter(InventoryMovement.variant_id == nueva.id).one()
        assert (mov.qty_change, mov.reference, mov.notes) == (Decimal("2"), "Alta Inicial", "Creación de variante")
