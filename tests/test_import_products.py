"""Tests: carga masiva de catalogo desde CSV (scripts/import_products.py)."""
import csv
import importlib

import pytest

from app.models.inventory import StockOnHand
from app.models.organization import Branch
from app.models.products import Department, Product, ProductVariant, ProductBranchStatus

imp = importlib.import_module("scripts.import_products")

CABECERAS = [
    "Nombre*", "Categoría", "Código", "Descripción", "Costo unitario",
    "Precio*", "Mostrar en el catálogo", "Controlar stock",
    "Stock actual", "Stock mínimo",
]


def _csv(tmp_path, filas):
    ruta = tmp_path / "productos.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CABECERAS)
        w.writeheader()
        for f in filas:
            w.writerow({**{c: "" for c in CABECERAS}, **f})
    return str(ruta)


FILA = {
    "Nombre*": "Folder oficio", "Categoría": "papeleria", "Código": "FOL-01",
    "Costo unitario": "7", "Precio*": "15", "Mostrar en el catálogo": "S",
    "Controlar stock": "S", "Stock actual": "427", "Stock mínimo": "400",
}


class TestImportacion:
    def test_crea_producto_variante_estado_y_existencias(self, db, org, branch_a, tmp_path):
        r = imp.import_products(db, _csv(tmp_path, [FILA]), org.id, branch_a.id)
        assert r["creados"] == 1

        p = db.query(Product).filter(Product.organization_id == org.id, Product.name == "Folder oficio").one()
        assert p.is_active is True

        v = db.query(ProductVariant).filter(ProductVariant.product_id == p.id).one()
        assert v.sku == "FOL-01"
        assert v.variant_name == "Estándar", (
            "toda ruta de creacion de la aplicacion asigna 'Estándar'; dejarlo "
            "en NULL tumbaba el cobro con un 500 en sales.py"
        )
        assert float(v.price) == 15.0
        assert float(v.cost) == 7.0
        assert v.organization_id == org.id

        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == v.id, ProductBranchStatus.branch_id == branch_a.id).one()
        assert pbs.is_active_pos is True
        assert pbs.is_visible is True
        assert float(pbs.min_stock_alert) == 400.0

        soh = db.query(StockOnHand).filter(
            StockOnHand.variant_id == v.id, StockOnHand.branch_id == branch_a.id).one()
        assert float(soh.qty_on_hand) == 427.0

    def test_crea_la_categoria_una_sola_vez(self, db, org, branch_a, tmp_path):
        filas = [FILA, {**FILA, "Nombre*": "Otro", "Código": "FOL-02"}]
        imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
        deps = db.query(Department).filter(Department.organization_id == org.id, Department.name == "papeleria").all()
        assert len(deps) == 1
        prods = db.query(Product).filter(Product.organization_id == org.id).all()
        assert all(p.department_id == deps[0].id for p in prods)

    def test_desambigua_codigos_repetidos(self, db, org, branch_a, tmp_path):
        filas = [
            {**FILA, "Nombre*": "Ap3759", "Código": "MAC-03"},
            {**FILA, "Nombre*": "Ap3761", "Código": "MAC-03"},
            {**FILA, "Nombre*": "Ap3298", "Código": "MAC-03"},
        ]
        r = imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
        assert r["creados"] == 3
        skus = sorted(v.sku for v in db.query(ProductVariant).filter(ProductVariant.organization_id == org.id))
        assert skus == ["MAC-03", "MAC-03-2", "MAC-03-3"]
        assert len(set(skus)) == 3, "el indice unico de SKU por organizacion no admite repetidos"
        assert r["codigos_generados"] == 2

    def test_genera_codigo_cuando_falta(self, db, org, branch_a, tmp_path):
        r = imp.import_products(db, _csv(tmp_path, [{**FILA, "Nombre*": "Sin codigo", "Código": ""}]), org.id, branch_a.id)
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        assert v.sku, "debe recibir un codigo generado"
        assert r["codigos_generados"] == 1

    def test_es_idempotente_por_sku(self, db, org, branch_a, tmp_path):
        ruta = _csv(tmp_path, [FILA])
        primera = imp.import_products(db, ruta, org.id, branch_a.id)
        segunda = imp.import_products(db, ruta, org.id, branch_a.id)
        assert primera["creados"] == 1
        assert segunda["creados"] == 0
        assert segunda["omitidos"] == 1
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 1

    def test_no_toca_otras_organizaciones(self, db, org, branch_a, tmp_path):
        from app.models.organization import Organization
        otra_org = Organization(name="Organizacion ajena", is_active=True)
        db.add(otra_org); db.commit(); db.refresh(otra_org)
        otra_suc = Branch(name="Ajena", organization_id=otra_org.id, is_active=True)
        db.add(otra_suc); db.commit()

        imp.import_products(db, _csv(tmp_path, [FILA]), org.id, branch_a.id)

        assert db.query(Product).filter(Product.organization_id == otra_org.id).count() == 0
        assert db.query(ProductVariant).filter(ProductVariant.organization_id == otra_org.id).count() == 0
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 1

    def test_fila_sin_nombre_se_ignora(self, db, org, branch_a, tmp_path):
        r = imp.import_products(db, _csv(tmp_path, [{**FILA, "Nombre*": ""}]), org.id, branch_a.id)
        assert r["creados"] == 0
        assert r["ignorados"] == 1

    def test_precio_invalido_es_error_claro(self, db, org, branch_a, tmp_path):
        with pytest.raises(ValueError, match="precio"):
            imp.import_products(db, _csv(tmp_path, [{**FILA, "Precio*": "no-es-numero"}]), org.id, branch_a.id)

    def test_costo_en_blanco_queda_en_cero(self, db, org, branch_a, tmp_path):
        fila = {**FILA, "Código": "FOL-02", "Costo unitario": ""}
        imp.import_products(db, _csv(tmp_path, [fila]), org.id, branch_a.id)
        v = db.query(ProductVariant).filter(
            ProductVariant.organization_id == org.id, ProductVariant.sku == "FOL-02").one()
        assert v.cost is not None, "costo NULL rompe margenes y ficha"
        assert float(v.cost) == 0.0
