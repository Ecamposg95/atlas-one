"""POST /api/products/upload por `services.importacion.importar_fila`."""
import inspect
import io
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from conftest import _auth_header, _make_product, _make_user
from app.models import PlatformAuditLog, InventoryMovement, PackagingUnit, ProductPrice, Department, Product
from app.modules.users.models import Role
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


class TestGuardiasAdicionales:
    def test_gerente_sin_sucursal_es_403_de_entrada(self, client, db, org, catalog_module_enabled):
        g = _make_user(db, org, None, "gerente_sin_suc", Role.GERENTE)
        r = _subir(client, _auth_header(g), org, [_fila("G-1")])
        assert r.status_code == 403, r.text
        assert "sucursal asignada" in r.json()["detail"]

    def test_sucursal_ajena_es_422_de_entrada(self, client, db, org, branch_a, auth_admin_sin_sucursal):
        r = _subir(client, auth_admin_sin_sucursal, org, [_fila("X-1")],
                   scope="selected", target_branch_ids="999999")
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Una o más sucursales objetivo no pertenecen a tu organización."

    def test_cajero_deja_auditoria(self, client, db, org, branch_a, catalog_module_enabled, cajero_a, auth_cajero_a):
        r = _subir(client, auth_cajero_a, org, [_fila("AUD-1")])
        assert r.status_code == 200 and r.json()["created"] == 1, r.text
        assert db.query(PlatformAuditLog).filter(PlatformAuditLog.action == "PRODUCT_CREATE_CAJERO").count() == 1


class TestExistenciaYCatalogo:
    def test_fila_nueva_stock_en_destino_y_cero_en_las_demas(self, client, db, org, hq_branch, branch_a,
                                                            auth_admin_sin_sucursal):
        r = _subir(client, auth_admin_sin_sucursal, org, [_fila("S-1", Stock="3")],
                   scope="all", branch_id=str(hq_branch.id))
        assert r.status_code == 200 and r.json()["created"] == 1, r.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "S-1").one()
        filas = {s.branch_id: s.qty_on_hand for s in db.query(StockOnHand).filter(StockOnHand.variant_id == v.id)}
        assert filas[hq_branch.id] == Decimal("3")
        assert filas[branch_a.id] == Decimal("0")

    def test_update_fija_existencia_absoluta_con_kardex(self, client, db, org, hq_branch, admin_user, auth_admin):
        p, v = _make_product(db, org, "Gorra", "GOR-1", 50, [(hq_branch.id, True)])
        db.flush()
        r = _subir(client, auth_admin, org, [_fila("GOR-1", Stock="7")])
        assert r.status_code == 200 and r.json()["updated"] == 1, r.text
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id, StockOnHand.branch_id == hq_branch.id).one()
        assert soh.qty_on_hand == Decimal("7")
        mov = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).order_by(InventoryMovement.id.desc()).first()
        assert mov.reference == "Excel Upload" and mov.qty_after == Decimal("7")

    def test_departamento_de_fila_fallida_no_contamina_a_las_siguientes(self, client, db, org, hq_branch, auth_admin):
        r = _subir(client, auth_admin, org, [
            _fila("D-1", Departamento="NuevoDep", **{"Precio Base": "0"}),
            _fila("D-2", Departamento="NuevoDep"),
        ])
        assert r.status_code == 200, r.text
        assert (r.json()["created"], r.json()["failed"]) == (1, 1)
        assert db.query(Department).filter(Department.name == "NuevoDep", Department.organization_id == org.id).count() == 1

    def test_fila_nueva_que_falla_despues_de_crear_no_deja_nada(self, client, db, org, hq_branch, auth_admin, monkeypatch):
        from app.modules.products.services import importacion
        def _boom(*a, **k):
            raise importacion.FilaInvalida("falla provocada")
        monkeypatch.setattr(importacion, "_empaques_y_escalones", _boom)
        r = _subir(client, auth_admin, org, [_fila("F-1")])
        assert (r.json()["created"], r.json()["failed"]) == (0, 1)
        assert db.query(ProductVariant).filter(ProductVariant.sku == "F-1").count() == 0
        assert db.query(Product).filter(Product.name == "Prod F-1").count() == 0

    def test_empaques_y_escalones_por_columnas(self, client, db, org, hq_branch, auth_admin):
        cab = CABECERAS + ["E1 Nombre", "E1 Cantidad", "E1 Precio", "P1 Nombre", "P1 Min", "P1 Precio", "P1 Empaque"]
        r = _subir(client, auth_admin, org, [_fila("E-1", **{
            "E1 Nombre": "Caja", "E1 Cantidad": "12", "E1 Precio": "100",
            "P1 Nombre": "Mayoreo", "P1 Min": "12", "P1 Precio": "9", "P1 Empaque": "Caja"})], cabeceras=cab)
        assert r.status_code == 200 and r.json()["created"] == 1, r.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "E-1").one()
        pkg = db.query(PackagingUnit).filter(PackagingUnit.variant_id == v.id).one()
        assert pkg.units_per_package == Decimal("12")
        tier = db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).one()
        assert tier.linked_package_id == pkg.id


class TestTasaIva:
    def _existente(self, db, org, hq_branch, sku, tasa):
        p, v = _make_product(db, org, "Con IVA", sku, 100, [(hq_branch.id, True)])
        v.tax_rate = Decimal(tasa)
        db.flush()
        return v

    def test_update_con_tasa_cero_la_aplica(self, client, db, org, hq_branch, admin_user, auth_admin):
        v = self._existente(db, org, hq_branch, "IVA-1", "16")
        r = _subir(client, auth_admin, org, [_fila("IVA-1", **{"Tasa IVA": "0"})], cabeceras=CABECERAS + ["Tasa IVA"])
        assert r.json()["updated"] == 1, r.text
        db.refresh(v)
        assert Decimal(str(v.tax_rate)) == Decimal("0")

    def test_update_sin_columna_conserva_la_tasa(self, client, db, org, hq_branch, admin_user, auth_admin):
        v = self._existente(db, org, hq_branch, "IVA-2", "0")
        r = _subir(client, auth_admin, org, [_fila("IVA-2")])
        assert r.json()["updated"] == 1, r.text
        db.refresh(v)
        assert Decimal(str(v.tax_rate)) == Decimal("0")

    def test_tasa_fuera_de_rango_falla_la_fila(self, client, db, org, hq_branch, admin_user, auth_admin):
        v = self._existente(db, org, hq_branch, "IVA-3", "16")
        r = _subir(client, auth_admin, org, [_fila("IVA-3", **{"Tasa IVA": "150"})], cabeceras=CABECERAS + ["Tasa IVA"])
        assert (r.json()["updated"], r.json()["failed"]) == (0, 1), r.text
        db.refresh(v)
        assert Decimal(str(v.tax_rate)) == Decimal("16")


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

    def test_sku_con_cajas_distintas_prefiere_la_exacta(self, client, db, org, branch_a, auth_admin):
        _, v1 = _make_product(db, org, "Mayus", "PLY-9", 100, [(branch_a.id, True)])
        _, v2 = _make_product(db, org, "Minus", "ply-9", 100, [(branch_a.id, True)])
        db.flush()
        r = _subir(client, auth_admin, org, [_fila("ply-9", **{"Precio Base": "77"})])
        assert r.json()["updated"] == 1, r.text
        db.refresh(v1); db.refresh(v2)
        assert (Decimal(str(v2.price)), Decimal(str(v1.price))) == (Decimal("77"), Decimal("100"))

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


class TestPrecio:
    def test_precio_cero_en_fila_nueva_y_en_existente_falla_sin_tocar_nada(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY-0", 100, [(branch_a.id, True)])
        db.flush()
        r = _subir(client, auth_admin, org, [
            _fila("PLY-0", **{"Precio Base": "0"}),      # existente
            _fila("NUEVO-0", **{"Precio Base": ""}),     # nueva, precio en blanco
            _fila("NEG-1", **{"Precio Base": "-3"}),     # nueva, negativo
        ])
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert (cuerpo["created"], cuerpo["updated"], cuerpo["failed"]) == (0, 0, 3)
        assert all("mayor a cero" in d["error"] for d in cuerpo["details"])
        db.refresh(v)
        assert Decimal(str(v.price)) == Decimal("100"), "el precio anterior queda intacto"
        assert db.query(ProductVariant).filter(ProductVariant.sku.in_(["NUEVO-0", "NEG-1"])).count() == 0


class TestCommit:
    def test_commit_fallido_es_500_y_no_reporta_exito(self, client, db, org, auth_admin, monkeypatch):
        def _revienta():
            raise RuntimeError("disco lleno")
        monkeypatch.setattr(db, "commit", _revienta, raising=False)
        r = _subir(client, auth_admin, org, [_fila("CM-1")])
        assert r.status_code == 500, r.text
        assert "No se pudieron guardar" in r.json()["detail"]
        assert "created" not in r.json()

    def test_commit_por_lote_fallido_tambien_es_500(self, client, db, org, auth_admin, monkeypatch):
        """El commit cada 50 filas tampoco se traga: la fila 50 dispara el lote."""
        def _revienta():
            raise RuntimeError("conexión perdida")
        monkeypatch.setattr(db, "commit", _revienta, raising=False)
        r = _subir(client, auth_admin, org, [_fila(f"LOTE-{i}") for i in range(50)])
        assert r.status_code == 500, r.text
        assert "hasta la fila 51" in r.json()["detail"]
