"""Tests: carga de catalogo desde una exportacion de Data X POS.

El archivo de entrada es un .xlsx que se arma aqui mismo con `zipfile` y el
mismo XML minimo que escribe Data X POS: texto en `sharedStrings.xml` y
numeros como celdas sin atributo `t`. Asi la prueba ejercita el lector real
(stdlib) en vez de una ruta de juguete.
"""
import importlib
import zipfile
from xml.sax.saxutils import escape

import pytest

from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.products import (
    Department,
    Product,
    ProductBranchStatus,
    ProductPrice,
    ProductVariant,
)

imp = importlib.import_module("scripts.import_datax_export")

CABECERAS = [
    "Código", "Descripción", "Costo", "Imágen",
    "¿Aplica Precio 1?", "Cantidad minima - Precio 1", "Precio 1",
    "¿Aplica Precio 2?", "Cantidad minima - Precio 2", "Precio 2",
    "¿Aplica Precio 3?", "Cantidad minima - Precio 3", "Precio 3",
    "¿Aplica Precio 4?", "Precio 4",
    "¿Aplica Precio 5?", "Precio 5",
    "¿Aplica inventario?", "Stock", "Mínimo", "Máximo", "Departamento",
]

FILA = {
    "Código": "H-625", "Descripción": "CASCADA", "Costo": "",
    "Imágen": "https://cdn.dataxpos.mx/productos/sin-imagen.png",
    "¿Aplica Precio 1?": "Sí", "Cantidad minima - Precio 1": "1.0", "Precio 1": "75.0",
    "¿Aplica Precio 2?": "Sí", "Cantidad minima - Precio 2": "3.0", "Precio 2": "65.0",
    "¿Aplica Precio 3?": "Sí", "Cantidad minima - Precio 3": "100.0", "Precio 3": "60.0",
    "¿Aplica Precio 4?": "No", "Precio 4": "0",
    "¿Aplica Precio 5?": "No", "Precio 5": "0",
    "¿Aplica inventario?": "Sí", "Stock": "57.0", "Mínimo": "10.0", "Máximo": "120.0",
    "Departamento": "Accesorio",
}


def _es_numero(v: str) -> bool:
    try:
        float(v)
    except (TypeError, ValueError):
        return False
    return True


def _xlsx(tmp_path, filas, nombre="datax.xlsx"):
    """Arma un .xlsx con la misma codificacion que exporta Data X POS."""
    compartidas: list[str] = []
    indices: dict[str, int] = {}

    def _idx(texto: str) -> int:
        if texto not in indices:
            indices[texto] = len(compartidas)
            compartidas.append(texto)
        return indices[texto]

    def _columna(i: int) -> str:
        letra = ""
        i += 1
        while i:
            i, resto = divmod(i - 1, 26)
            letra = chr(65 + resto) + letra
        return letra

    xml_filas = []
    for nfila, valores in enumerate([{c: c for c in CABECERAS}] + filas, start=1):
        celdas = []
        for i, cab in enumerate(CABECERAS):
            v = valores.get(cab, "")
            if v == "" or v is None:
                continue  # Data X POS omite la celda vacia, no la escribe vacia
            ref = f"{_columna(i)}{nfila}"
            if nfila > 1 and _es_numero(v):
                celdas.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                celdas.append(f'<c r="{ref}" t="s"><v>{_idx(str(v))}</v></c>')
        xml_filas.append(f'<row r="{nfila}">{"".join(celdas)}</row>')

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    hoja = f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData>{"".join(xml_filas)}</sheetData></worksheet>'
    sst = "".join(f"<si><t>{escape(s)}</t></si>" for s in compartidas)
    cadenas = f'<?xml version="1.0" encoding="UTF-8"?><sst {ns} count="{len(compartidas)}" uniqueCount="{len(compartidas)}">{sst}</sst>'

    ruta = tmp_path / nombre
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("xl/sharedStrings.xml", cadenas)
        z.writestr("xl/worksheets/sheet1.xml", hoja)
    return str(ruta)


@pytest.fixture()
def cargar(db, org, branch_a, admin_user, tmp_path):
    """Corre el importador sobre un archivo armado al vuelo."""
    def _cargar(filas, dry_run=False, nombre="datax.xlsx"):
        ruta = _xlsx(tmp_path, filas, nombre=nombre)
        return imp.import_datax_export(
            db, ruta, org.id, branch_a.id, dry_run=dry_run
        )
    return _cargar


class TestCatalogo:
    def test_crea_producto_variante_y_precio_base(self, db, org, branch_a, cargar):
        r = cargar([FILA])
        assert r["creados"] == 1

        p = db.query(Product).filter(Product.organization_id == org.id).one()
        assert p.name == "CASCADA"
        assert p.is_active is True

        v = db.query(ProductVariant).filter(ProductVariant.product_id == p.id).one()
        assert v.sku == "H-625"
        assert v.barcode == "H-625"
        assert v.variant_name == "Estándar"
        assert float(v.price) == 75.0, "el precio base es Precio 1"
        assert v.cost is None, "la exportacion trae el costo vacio casi siempre"
        assert v.organization_id == org.id

    def test_toma_el_costo_cuando_viene(self, db, org, cargar):
        cargar([{**FILA, "Costo": "40.0"}])
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        assert float(v.cost) == 40.0

    def test_ignora_la_imagen_marcador(self, db, org, cargar):
        r = cargar([FILA])
        p = db.query(Product).filter(Product.organization_id == org.id).one()
        assert p.image_url is None, "sin-imagen.png es el marcador del POS de origen"
        assert not any("imagen" in i for i in r["incidencias"])

    def test_avisa_cuando_el_producto_si_trae_imagen(self, db, org, cargar):
        r = cargar([{**FILA, "Imágen": "https://cdn.dataxpos.mx/productos/h-625.png"}])
        assert any("imagen propia" in i and "H-625" in i for i in r["incidencias"]), (
            "la carga no descarga imagenes: debe decir cuales quedaron fuera"
        )


class TestEscalones:
    def test_crea_un_escalon_por_cada_precio_aplicado(self, db, org, cargar):
        r = cargar([FILA])
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        escalones = sorted(
            db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).all(),
            key=lambda e: float(e.min_quantity),
        )
        assert [e.price_name for e in escalones] == ["Menudeo", "Mayoreo", "Volumen"]
        assert [float(e.min_quantity) for e in escalones] == [1.0, 3.0, 100.0]
        assert [float(e.unit_price) for e in escalones] == [75.0, 65.0, 60.0]
        assert all(e.organization_id == org.id for e in escalones)
        assert r["escalones"] == 3

    def test_precio_no_aplicado_no_crea_escalon(self, db, org, cargar):
        cargar([{**FILA, "¿Aplica Precio 3?": "No",
                 "Cantidad minima - Precio 3": "0", "Precio 3": "0"}])
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        nombres = {e.price_name for e in db.query(ProductPrice).filter(ProductPrice.variant_id == v.id)}
        assert nombres == {"Menudeo", "Mayoreo"}

    def test_precio_4_aplicado_se_reporta_y_no_se_carga(self, db, org, cargar):
        r = cargar([{**FILA, "¿Aplica Precio 4?": "Sí", "Precio 4": "50.0"}])
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        assert db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).count() == 3
        assert any("Precio 4" in i and "H-625" in i for i in r["incidencias"]), (
            "sin cantidad minima no hay escalon posible: debe avisar, no callar"
        )


class TestExistencias:
    def test_el_stock_inicial_entra_como_movimiento(self, db, org, branch_a, admin_user, cargar):
        r = cargar([FILA])
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()

        mov = db.query(InventoryMovement).filter(
            InventoryMovement.variant_id == v.id,
            InventoryMovement.branch_id == branch_a.id,
        ).one()
        assert mov.movement_type == MovementType.ADJUSTMENT_IN
        assert float(mov.qty_change) == 57.0
        assert float(mov.qty_before) == 0.0
        assert float(mov.qty_after) == 57.0
        assert mov.reference == imp.REFERENCIA_CARGA
        assert mov.user_id == admin_user.id, "el autor es el admin de la organizacion"
        assert mov.organization_id == org.id

        soh = db.query(StockOnHand).filter(
            StockOnHand.variant_id == v.id, StockOnHand.branch_id == branch_a.id).one()
        assert float(soh.qty_on_hand) == 57.0
        assert soh.is_active is True
        assert r["movimientos"] == 1

    def test_sin_inventario_no_hay_movimiento(self, db, org, cargar):
        r = cargar([{**FILA, "¿Aplica inventario?": "No", "Stock": "0"}])
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        assert db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).count() == 0
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert float(soh.qty_on_hand) == 0.0
        assert soh.is_active is False
        assert r["movimientos"] == 0

    def test_stock_cero_no_genera_movimiento(self, db, org, cargar):
        r = cargar([{**FILA, "Stock": "0"}])
        assert r["movimientos"] == 0

    def test_minimo_y_maximo_van_al_estado_de_sucursal(self, db, org, branch_a, cargar):
        cargar([FILA])
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == v.id,
            ProductBranchStatus.branch_id == branch_a.id).one()
        assert float(pbs.min_stock_alert) == 10.0
        assert float(pbs.max_stock_limit) == 120.0
        assert pbs.is_active_pos is True

    def test_maximo_cero_queda_vacio(self, db, org, cargar):
        cargar([{**FILA, "Máximo": "0", "Mínimo": "0"}])
        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.organization_id == org.id).one()
        assert pbs.max_stock_limit is None, "un tope de 0 dejaria la sucursal sin capacidad"
        assert pbs.min_stock_alert is None


class TestDepartamentos:
    def test_crea_el_departamento_una_sola_vez(self, db, org, cargar):
        cargar([FILA, {**FILA, "Código": "H-626", "Descripción": "CASCADA CHICA"}])
        deps = db.query(Department).filter(
            Department.organization_id == org.id, Department.name == "Accesorio").all()
        assert len(deps) == 1
        prods = db.query(Product).filter(Product.organization_id == org.id).all()
        assert all(p.department_id == deps[0].id for p in prods)

    def test_sin_departamento_no_crea_departamento(self, db, org, cargar):
        cargar([{**FILA, "Departamento": "Sin departamento"}])
        assert db.query(Department).filter(Department.organization_id == org.id).count() == 0
        p = db.query(Product).filter(Product.organization_id == org.id).one()
        assert p.department_id is None


class TestOmisiones:
    def test_renglon_de_prueba_se_omite(self, db, org, cargar):
        r = cargar([
            {**FILA, "Código": "123", "Descripción": "PRUEBA", "Stock": "0"},
            FILA,
        ])
        assert r["creados"] == 1
        assert r["omitidos"] == 1
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 1
        assert any("123" in i and "PRUEBA" in i for i in r["incidencias"])

    def test_renglon_sin_descripcion_se_omite(self, db, org, cargar):
        r = cargar([{**FILA, "Descripción": ""}])
        assert r["creados"] == 0
        assert r["omitidos"] == 1


class TestIdempotencia:
    def test_correrlo_dos_veces_no_duplica_nada(self, db, org, branch_a, tmp_path, admin_user):
        ruta = _xlsx(tmp_path, [FILA, {**FILA, "Código": "H-626", "Descripción": "OTRA"}])
        primera = imp.import_datax_export(db, ruta, org.id, branch_a.id)
        segunda = imp.import_datax_export(db, ruta, org.id, branch_a.id)

        assert primera["creados"] == 2 and primera["actualizados"] == 0
        assert segunda["creados"] == 0 and segunda["actualizados"] == 2
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 2
        assert db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).count() == 2
        assert db.query(ProductPrice).filter(ProductPrice.organization_id == org.id).count() == 6
        assert db.query(Department).filter(Department.organization_id == org.id).count() == 1
        assert segunda["departamentos_creados"] == 0

    def test_el_stock_no_se_vuelve_a_cargar(self, db, org, branch_a, tmp_path, admin_user):
        ruta = _xlsx(tmp_path, [FILA])
        imp.import_datax_export(db, ruta, org.id, branch_a.id)
        segunda = imp.import_datax_export(db, ruta, org.id, branch_a.id)

        assert segunda["movimientos"] == 0
        assert db.query(InventoryMovement).filter(
            InventoryMovement.organization_id == org.id).count() == 1
        soh = db.query(StockOnHand).filter(StockOnHand.organization_id == org.id).one()
        assert float(soh.qty_on_hand) == 57.0, "la segunda corrida no puede duplicar existencias"

    def test_actualiza_precio_y_escalones_del_archivo_nuevo(self, db, org, branch_a, tmp_path, admin_user):
        imp.import_datax_export(db, _xlsx(tmp_path, [FILA], nombre="v1.xlsx"), org.id, branch_a.id)
        imp.import_datax_export(
            db,
            _xlsx(tmp_path, [{**FILA, "Precio 1": "80.0", "Precio 2": "70.0"}], nombre="v2.xlsx"),
            org.id, branch_a.id,
        )
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        assert float(v.price) == 80.0
        mayoreo = db.query(ProductPrice).filter(
            ProductPrice.variant_id == v.id, ProductPrice.price_name == "Mayoreo").one()
        assert float(mayoreo.unit_price) == 70.0

    def test_codigo_repetido_se_desambigua_y_sigue_siendo_idempotente(
        self, db, org, branch_a, tmp_path, admin_user
    ):
        filas = [
            {**FILA, "Código": "2024033050038", "Descripción": "POPULAR-LIGA"},
            {**FILA, "Código": "2024033050038", "Descripción": "LIGA-POPULAR"},
        ]
        ruta = _xlsx(tmp_path, filas)
        primera = imp.import_datax_export(db, ruta, org.id, branch_a.id)
        assert primera["creados"] == 2
        variantes = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).all()
        assert sorted(v.sku for v in variantes) == ["2024033050038", "2024033050038-2"]
        assert {v.barcode for v in variantes} == {"2024033050038"}, (
            "el codigo de barras real no se desambigua: es el mismo en ambos renglones"
        )

        segunda = imp.import_datax_export(db, ruta, org.id, branch_a.id)
        assert segunda["creados"] == 0 and segunda["actualizados"] == 2
        assert db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).count() == 2

    def test_codigo_vacio_recibe_uno_generado(self, db, org, branch_a, tmp_path, admin_user):
        ruta = _xlsx(tmp_path, [{**FILA, "Código": ""}])
        r = imp.import_datax_export(db, ruta, org.id, branch_a.id)
        v = db.query(ProductVariant).filter(ProductVariant.organization_id == org.id).one()
        assert v.sku and v.barcode is None
        assert r["codigos_generados"] == 1
        segunda = imp.import_datax_export(db, ruta, org.id, branch_a.id)
        assert segunda["creados"] == 0, "sin codigo, la identidad es el nombre del producto"


class TestSeguridad:
    def test_el_ensayo_no_guarda_nada(self, db, org, branch_a, admin_user, cargar):
        r = cargar([FILA], dry_run=True)
        assert r["creados"] == 1
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 0
        assert db.query(InventoryMovement).filter(
            InventoryMovement.organization_id == org.id).count() == 0

    def test_no_toca_otras_organizaciones(self, db, org, branch_a, admin_user, cargar):
        from app.models.organization import Organization
        otra = Organization(name="Organizacion ajena", is_active=True)
        db.add(otra)
        db.flush()

        cargar([FILA])

        assert db.query(Product).filter(Product.organization_id == otra.id).count() == 0
        assert db.query(ProductVariant).filter(ProductVariant.organization_id == otra.id).count() == 0
        assert db.query(ProductPrice).filter(ProductPrice.organization_id == otra.id).count() == 0
        assert db.query(InventoryMovement).filter(
            InventoryMovement.organization_id == otra.id).count() == 0
