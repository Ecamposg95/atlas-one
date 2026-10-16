"""Alta de producto por `services.crear_producto` (POST /api/products/)."""
import inspect
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductPrice, ProductVariant


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _cuerpo(sku, **extra):
    return {"name": f"Prod {sku}", "sku": sku, "price": "100", "cost": "50", **extra}


def _archivar(db, producto, variante):
    ahora = datetime.now(timezone.utc)
    producto.deleted_at = ahora
    producto.is_active = False
    variante.deleted_at = ahora
    db.flush()


class TestSkuUnico:
    def test_mayusculas_distintas_es_409(self, client, db, org, branch_a, auth_admin):
        _make_product(db, org, "Playera", "PLY-1", 100, [(branch_a.id, True)])
        db.flush()
        r = client.post("/api/products/", json=_cuerpo("ply-1", target_branch_ids=[branch_a.id]),
                        headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "El SKU 'ply-1' ya existe en esta organización."

    def test_sku_de_producto_archivado_es_409_y_lo_dice(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Vieja", "ARCH-1", 100, [(branch_a.id, True)])
        _archivar(db, p, v)
        r = client.post("/api/products/", json=_cuerpo("ARCH-1"), headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]

    def test_sku_con_espacios_se_guarda_recortado(self, client, db, org, branch_a, auth_admin):
        r = client.post("/api/products/", json=_cuerpo("  REC-1 ", target_branch_ids=[branch_a.id]),
                        headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json()["sku"] == "REC-1"


class TestHqSinDestinos:
    def test_queda_habilitado_en_todas_las_que_venden(self, client, db, org, branch_a, branch_b, hq_branch, auth_admin_sin_sucursal):
        r = client.post("/api/products/", json=_cuerpo("HQ-1"), headers=_h(auth_admin_sin_sucursal, org))
        assert r.status_code == 200, r.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "HQ-1").one()
        pbs = {p.branch_id for p in db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all()}
        assert pbs == {branch_a.id, branch_b.id}, "HQ no vende: no se habilita ahí"
        soh = {s.branch_id: s.qty_on_hand for s in db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).all()}
        assert soh == {branch_a.id: Decimal("0"), branch_b.id: Decimal("0")}

    def test_con_existencia_y_varias_que_venden_pide_sucursal(self, client, db, org, branch_a, branch_b, auth_admin_sin_sucursal):
        r = client.post("/api/products/", json=_cuerpo("HQ-2", initial_stock="5"), headers=_h(auth_admin_sin_sucursal, org))
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Indica en qué sucursal entra la existencia inicial: no se reparte sola entre varias sucursales."
        r2 = client.post("/api/products/", json=_cuerpo("HQ-2", initial_stock="5", branch_id=branch_b.id),
                         headers=_h(auth_admin_sin_sucursal, org))
        assert r2.status_code == 200, r2.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "HQ-2").one()
        soh = {s.branch_id: s.qty_on_hand for s in db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).all()}
        assert soh == {branch_a.id: Decimal("0"), branch_b.id: Decimal("5")}

    def test_sin_ninguna_que_venda_sigue_siendo_catalogo_global(self, client, db, org, hq_branch, auth_admin_sin_sucursal):
        r = client.post("/api/products/", json=_cuerpo("HQ-3"), headers=_h(auth_admin_sin_sucursal, org))
        assert r.status_code == 200, r.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "HQ-3").one()
        assert db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).count() == 0


class TestValidacionesNuevas:
    def test_escalon_en_cero_tambien_se_rechaza_en_el_alta(self, client, db, org, branch_a, auth_admin):
        r = client.post("/api/products/", json=_cuerpo(
            "ESC-1", target_branch_ids=[branch_a.id],
            prices=[{"price_name": "Caja", "min_quantity": 12, "unit_price": 0}],
        ), headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text
        assert "Caja" in r.json()["detail"]
        assert db.query(ProductVariant).filter(ProductVariant.sku == "ESC-1").count() == 0
        assert db.query(ProductPrice).count() == 0


class TestModuloCatalogo:
    def test_cajero_sin_modulo_catalog_es_403(self, client, org, cajero_a, auth_cajero_a):
        r = client.post("/api/products/", json=_cuerpo("CAJ-1"), headers=_h(auth_cajero_a, org))
        assert r.status_code == 403, r.text
        assert "catalog" in r.json()["detail"]

    def test_cajero_con_modulo_crea(self, client, org, catalog_module_enabled, cajero_a, auth_cajero_a):
        r = client.post("/api/products/", json=_cuerpo("CAJ-2"), headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text


class TestHandlerDelgado:
    def test_create_product_cabe_en_40_lineas(self):
        from app.modules.products.router.core import create_product
        assert len(inspect.getsource(create_product).splitlines()) < 40
