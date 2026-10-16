"""POST /api/products/upload por `services.importacion.importar_fila`."""
import inspect
import io
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from app.services.barcodes import es_codigo_interno

CABECERAS = ["SKU", "Nombre", "Departamento", "Precio Base", "Costo", "Stock"]


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _csv(filas, cabeceras=CABECERAS):
    buf = io.StringIO()
    buf.write(",".join(cabeceras) + "\n")
    for f in filas:
        buf.write(",".join(str(f.get(c, "")) for c in cabeceras) + "\n")
    return buf.getvalue().encode("utf-8")


def _subir(client, auth, org, filas, cabeceras=CABECERAS, **form):
    return client.post(
        "/api/products/upload",
        headers=_h(auth, org),
        files={"file": ("catalogo.csv", _csv(filas, cabeceras), "text/csv")},
        data=form,
    )


def _fila(sku, **extra):
    base = {"SKU": sku, "Nombre": f"Prod {sku}", "Departamento": "General",
            "Precio Base": "10", "Costo": "5", "Stock": "1"}
    base.update(extra)
    return base


class TestGuardias:
    def test_vendedor_es_403(self, client, org, auth_vendedor_sin_sucursal):
        r = _subir(client, auth_vendedor_sin_sucursal, org, [_fila("V-1")])
        assert r.status_code == 403, r.text

    def test_cajero_sin_modulo_catalog_es_403(self, client, org, cajero_a, auth_cajero_a):
        r = _subir(client, auth_cajero_a, org, [_fila("C-1")])
        assert r.status_code == 403, r.text
        assert "catalog" in r.json()["detail"]

    def test_cajero_con_modulo_importa_a_su_sucursal(self, client, db, org, branch_a, catalog_module_enabled,
                                                     cajero_a, auth_cajero_a):
        r = _subir(client, auth_cajero_a, org, [_fila("C-2", Stock="2")])
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 1 and r.json()["failed"] == 0
        v = db.query(ProductVariant).filter(ProductVariant.sku == "C-2").one()
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).one()
        assert (pbs.branch_id, pbs.is_active_pos, pbs.is_active_hq) == (branch_a.id, True, False)
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert (soh.branch_id, soh.qty_on_hand) == (branch_a.id, Decimal("2"))

    def test_target_branch_ids_mal_formado_es_400_de_entrada(self, client, org, branch_a, auth_admin_sin_sucursal):
        r = _subir(client, auth_admin_sin_sucursal, org, [_fila("T-1")],
                   scope="selected", target_branch_ids="abc")
        assert r.status_code == 400, r.text


class TestFilaNueva:
    def test_pasa_por_crear_producto(self, client, db, org, hq_branch, admin_user, auth_admin):
        r = _subir(client, auth_admin, org, [_fila("N-1", Stock="3")])
        assert r.status_code == 200, r.text
        assert r.json() == {"created": 1, "updated": 0, "failed": 0, "pending": 0, "details": []}
        v = db.query(ProductVariant).filter(ProductVariant.sku == "N-1").one()
        assert es_codigo_interno(org.id, v.barcode)
        assert Decimal(str(v.tax_rate)) == Decimal("16")
        # admin_user tiene sucursal HQ: todo cae ahí, como siempre.
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).one()
        assert pbs.branch_id == hq_branch.id
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert (soh.branch_id, soh.qty_on_hand) == (hq_branch.id, Decimal("3"))

    def test_sku_archivado_se_reporta_como_fila_fallida_accionable(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Vieja", "ARCH-1", 10, [(branch_a.id, True)])
        ahora = datetime.now(timezone.utc)
        p.deleted_at = ahora; p.is_active = False; v.deleted_at = ahora
        db.flush()
        r = _subir(client, auth_admin, org, [_fila("ARCH-1")])
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert (cuerpo["created"], cuerpo["failed"]) == (0, 1)
        assert "archivado" in cuerpo["details"][0]["error"]
        assert cuerpo["details"][0]["row"] == 2

    def test_sku_con_otra_caja_actualiza_en_vez_de_duplicar(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY-1", 100, [(branch_a.id, True)])
        db.flush()
        r = _subir(client, auth_admin, org, [_fila("ply-1", **{"Precio Base": "120"})])
        assert r.status_code == 200, r.text
        assert (r.json()["created"], r.json()["updated"]) == (0, 1)
        db.refresh(v)
        assert Decimal(str(v.price)) == Decimal("120")
        assert db.query(ProductVariant).filter(ProductVariant.product_id == p.id).count() == 1

    def test_dry_run_no_escribe_y_reporta(self, client, db, org, auth_admin):
        r = _subir(client, auth_admin, org, [_fila("DRY-1"), _fila("")], dry_run="true")
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert (cuerpo["total_rows"], cuerpo["to_create"], cuerpo["errors"]) == (1, 1, 0)
        assert cuerpo["preview"][0]["action"] == "NEW"
        assert db.query(ProductVariant).filter(ProductVariant.sku == "DRY-1").count() == 0


class TestHandlerDelgado:
    def test_upload_products_cabe_en_40_lineas(self):
        from app.modules.products.router.import_export import upload_products
        assert len(inspect.getsource(upload_products).splitlines()) < 40

    def test_sin_print_en_el_importador(self):
        from app.modules.products.router import import_export
        from app.modules.products.services import importacion
        assert "print(" not in inspect.getsource(import_export)
        assert "print(" not in inspect.getsource(importacion)
