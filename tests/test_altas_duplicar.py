"""POST /api/products/{id}/duplicate por `services.duplicar_producto`.

Bugs cerrados (spec §2.1): la copia perdía color/talla, nacía sin código de
barras y recorría también las variantes retiradas.
"""
import inspect
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.products import PackagingUnit, Product, ProductPrice, ProductVariant
from app.services.barcodes import es_codigo_interno


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestDuplicar:
    def test_conserva_color_y_talla_y_asigna_codigo(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY-R-M", 100, [(branch_a.id, True)])
        v.color, v.size, v.variant_name = "Rojo", "M", "Rojo / M"
        v.barcode = "7500000000011"
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json()["sku"] == "PLY-R-M-COPY-1"
        copia = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-R-M-COPY-1").one()
        assert (copia.color, copia.size, copia.variant_name) == ("Rojo", "M", "Rojo / M")
        assert es_codigo_interno(org.id, copia.barcode)
        assert copia.barcode != v.barcode

    def test_no_copia_variantes_retiradas(self, client, db, org, branch_a, auth_admin):
        p, _ = _make_product(db, org, "Playera", "PLY-2", 100, [(branch_a.id, True)])
        db.add(ProductVariant(
            product_id=p.id, sku="PLY-2-L", price=Decimal("100"), cost=Decimal("50"),
            organization_id=org.id, deleted_at=datetime.now(timezone.utc),
        ))
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        copia = db.get(Product, r.json()["id"])
        assert [x.sku for x in copia.variants] == ["PLY-2-COPY-1"]

    def test_copia_empaques_y_escalones_enlazados(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Refresco", "REF-1", 10, [(branch_a.id, True)])
        caja = PackagingUnit(variant_id=v.id, name="Caja", barcode="CAJA-1", units_per_package=Decimal("24"),
                             package_price=Decimal("200"), organization_id=org.id)
        db.add(caja); db.flush()
        db.add(ProductPrice(variant_id=v.id, price_name="Caja", min_quantity=Decimal("24"),
                            unit_price=Decimal("8"), linked_package_id=caja.id, organization_id=org.id))
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "REF-1-COPY-1").one()
        pkg = db.query(PackagingUnit).filter(PackagingUnit.variant_id == nueva.id).one()
        assert (pkg.name, pkg.barcode) == ("Caja", None)   # el barcode del empaque no se copia (único)
        precio = db.query(ProductPrice).filter(ProductPrice.variant_id == nueva.id).one()
        assert precio.linked_package_id == pkg.id

    def test_sin_variantes_vivas_es_409(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Vacía", "VAC-1", 100, [(branch_a.id, True)])
        v.deleted_at = datetime.now(timezone.utc)
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert db.query(Product).filter(Product.name == "Vacía (copia)").count() == 0

    def test_cajero_sin_modulo_catalog_es_403(self, client, org, products_setup, auth_cajero_a):
        product, _ = products_setup["product_a"]
        r = client.post(f"/api/products/{product.id}/duplicate", headers=_h(auth_cajero_a, org))
        assert r.status_code == 403, r.text
        assert "catalog" in r.json()["detail"]

    def test_duplicate_product_cabe_en_40_lineas(self):
        from app.modules.products.router.core import duplicate_product
        assert len(inspect.getsource(duplicate_product).splitlines()) < 40
