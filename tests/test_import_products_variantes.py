"""Un CSV con Color/Talla agrupa filas del mismo nombre en un producto con N
variantes; sin esas columnas, importa como siempre (una fila = un producto)."""
import csv
import importlib

from app.models.inventory import StockOnHand
from app.models.products import Product, ProductVariant

imp = importlib.import_module("scripts.import_products")

CABECERAS = ["Nombre*", "Categoría", "Código", "Descripción", "Costo unitario", "Precio*",
             "Mostrar en el catálogo", "Controlar stock", "Stock actual", "Stock mínimo", "Color", "Talla"]


def _csv(tmp_path, filas):
    ruta = tmp_path / "ropa.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CABECERAS)
        w.writeheader()
        for f in filas:
            w.writerow({**{c: "" for c in CABECERAS}, **f})
    return str(ruta)


BASE = {"Nombre*": "Playera lisa", "Categoría": "Playeras", "Costo unitario": "60", "Precio*": "120",
        "Mostrar en el catálogo": "S", "Controlar stock": "S", "Stock mínimo": "1"}


def test_agrupa_por_nombre_en_un_producto_con_variantes(db, org, branch_a, tmp_path):
    filas = [
        {**BASE, "Código": "PLY-R-S", "Color": "Rojo", "Talla": "S", "Stock actual": "3"},
        {**BASE, "Código": "PLY-R-M", "Color": "Rojo", "Talla": "M", "Stock actual": "5"},
        {**BASE, "Código": "PLY-N-M", "Color": "Negro", "Talla": "M", "Stock actual": "0", "Precio*": "130"},
    ]
    r = imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
    assert r["creados"] == 1 and r.get("variantes_creadas") == 3
    p = db.query(Product).filter(Product.organization_id == org.id, Product.name == "Playera lisa").one()
    vs = {v.sku: v for v in db.query(ProductVariant).filter(ProductVariant.product_id == p.id).all()}
    assert set(vs) == {"PLY-R-S", "PLY-R-M", "PLY-N-M"}
    assert vs["PLY-R-M"].variant_name == "Rojo / M"
    assert vs["PLY-N-M"].price == 130
    stock = {v.sku: db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one().qty_on_hand for v in vs.values()}
    assert stock["PLY-R-M"] == 5 and stock["PLY-N-M"] == 0


def test_sin_columnas_de_variante_importa_como_antes(db, org, branch_a, tmp_path):
    filas = [{**BASE, "Código": "GOR-1", "Nombre*": "Gorra"}, {**BASE, "Código": "GOR-2", "Nombre*": "Gorra"}]
    r = imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
    # Mismo nombre SIN color/talla = dos productos, como hoy.
    assert r["creados"] == 2


def test_pareja_repetida_se_reporta_y_omite(db, org, branch_a, tmp_path):
    filas = [
        {**BASE, "Código": "PLY-1", "Color": "Rojo", "Talla": "S"},
        {**BASE, "Código": "PLY-2", "Color": "rojo", "Talla": "s"},
    ]
    r = imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
    assert r["creados"] == 1 and r["omitidos"] == 1
    assert any("Rojo / S" in x for x in r["incidencias"])
