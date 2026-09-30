"""Tests: carga de catalogo desde la exportacion de rmazh (scripts/import_rmazh_export.py).

El xlsx se arma aqui con `zipfile` y el XML minimo que escribe openpyxl (el
exportador de rmazh usa openpyxl): texto en `sharedStrings.xml`, numeros como
celdas sin atributo `t`. Asi la prueba ejercita el lector real.
"""
import importlib
import zipfile
from decimal import Decimal
from xml.sax.saxutils import escape

import pytest

from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.products import Brand, Department, Product, ProductBranchStatus, ProductPrice, ProductVariant

imp = importlib.import_module("scripts.import_rmazh_export")

CABECERAS = [
    "SKU", "Nombre", "Descripcion", "Unidad", "Departamento", "Marca", "Codigo Barras",
    "Precio Base", "Costo", "Stock", "Incluye IVA",
] + [f"P{i} {f}" for i in range(1, 6) for f in ["Nombre", "Min", "Precio", "Empaque"]] \
  + [f"E{i} {f}" for i in range(1, 4) for f in ["Nombre", "Barcode", "Cantidad", "Precio"]]

CASCANUECES = {
    "SKU": "8888172121301", "Nombre": "CASCANUECES", "Descripcion": "", "Unidad": "pza",
    "Departamento": "Ncoqueta", "Marca": "Rmazh", "Codigo Barras": "8888172121301",
    "Precio Base": 220, "Costo": 140, "Stock": 2556, "Incluye IVA": "No",
    "P1 Nombre": "Mayoreo", "P1 Min": 3, "P1 Precio": 210,
}
STITCH = {
    "SKU": "STITCH", "Nombre": "STITCH", "Departamento": "General", "Marca": "Rmazh",
    "Codigo Barras": "", "Precio Base": 140, "Costo": 70, "Stock": 10000, "Incluye IVA": "Si",
    "P1 Nombre": "Mayoreo", "P1 Min": 3, "P1 Precio": 120,
    "P2 Nombre": "Caja", "P2 Min": 12, "P2 Precio": 100,
}


def _es_numero(v) -> bool:
    try:
        float(v)
    except (TypeError, ValueError):
        return False
    return True


def _xlsx(tmp_path, filas, nombre="rmazh.xlsx"):
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
                continue
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
        # La exportacion real trae una segunda hoja "Listas_Validacion": no debe leerse.
        z.writestr("xl/worksheets/sheet2.xml", f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>')
    return str(ruta)


@pytest.fixture()
def cargar(db, org, branch_a, admin_user, tmp_path):
    def _cargar(filas, **kw):
        ruta = _xlsx(tmp_path, filas)
        return imp.import_rmazh_export(db, ruta, org.id, branch_a.id, **kw)
    return _cargar


class TestCatalogo:
    def test_crea_producto_variante_precio_costo_iva(self, db, org, branch_a, cargar):
        r = cargar([CASCANUECES])
        assert r["creados"] == 1 and r["omitidos"] == 0

        p = db.query(Product).filter(Product.organization_id == org.id).one()
        assert p.name == "CASCANUECES"
        v = db.query(ProductVariant).filter(ProductVariant.product_id == p.id).one()
        assert v.sku == "8888172121301"
        assert v.barcode == "8888172121301"
        assert v.variant_name == "Estándar"
        assert Decimal(str(v.price)) == Decimal("220")
        assert Decimal(str(v.cost)) == Decimal("140")
        assert v.has_iva is False
        pbs = db.query(ProductBranchStatus).filter_by(variant_id=v.id, branch_id=branch_a.id).one()
        assert pbs.is_active_pos is True and pbs.is_visible is True

    def test_departamento_ncoqueta_y_general_no_se_crean(self, db, org, cargar):
        cargar([CASCANUECES, STITCH])
        assert db.query(Department).filter(Department.organization_id == org.id).count() == 0
        for p in db.query(Product).filter(Product.organization_id == org.id):
            assert p.department_id is None

    def test_departamento_real_si_se_crea(self, db, org, cargar):
        r = cargar([dict(CASCANUECES, Departamento="Navidad")])
        assert r["departamentos_creados"] == 1
        d = db.query(Department).filter(Department.organization_id == org.id).one()
        assert d.name == "Navidad"
        assert db.query(Product).one().department_id == d.id

    def test_conservar_departamentos_crea_ncoqueta(self, db, org, cargar):
        cargar([CASCANUECES], conservar_departamentos=True)
        assert db.query(Department).filter(Department.name == "Ncoqueta").count() == 1

    def test_marca_se_ignora_salvo_bandera(self, db, org, cargar):
        cargar([CASCANUECES])
        assert db.query(Brand).filter(Brand.organization_id == org.id).count() == 0
        assert db.query(Product).one().brand_id is None

    def test_conservar_marcas_crea_rmazh(self, db, org, cargar):
        r = cargar([CASCANUECES], conservar_marcas=True)
        assert r["marcas_creadas"] == 1
        b = db.query(Brand).filter(Brand.organization_id == org.id).one()
        assert b.name == "Rmazh" and db.query(Product).one().brand_id == b.id

    def test_sin_codigo_de_barras_entra_con_sku_y_barcode_nulo(self, db, cargar):
        cargar([STITCH])
        v = db.query(ProductVariant).one()
        assert v.sku == "STITCH" and v.barcode is None

    def test_iva_variantes_de_escritura(self, db, cargar):
        """Review Focus #3."""
        filas = [
            dict(STITCH, SKU=f"S{i}", Nombre=f"S{i}", **{"Incluye IVA": v})
            for i, v in enumerate(["SI", "sí", "Sí", "1", "No", "", "quizas"])
        ]
        cargar(filas)
        iva = {v.sku: v.has_iva for v in db.query(ProductVariant)}
        assert iva == {"S0": True, "S1": True, "S2": True, "S3": True, "S4": False, "S5": False, "S6": False}

    def test_sin_nombre_se_omite_con_incidencia(self, db, cargar):
        r = cargar([dict(CASCANUECES, Nombre="")])
        assert r["omitidos"] == 1 and r["creados"] == 0
        assert any("sin nombre" in i for i in r["incidencias"])

    def test_costo_vacio_queda_en_cero_nunca_nulo(self, db, cargar):
        cargar([dict(CASCANUECES, Costo="")])
        v = db.query(ProductVariant).one()
        assert v.cost is not None and Decimal(str(v.cost)) == 0

    def test_precio_base_ausente_carga_cero_con_incidencia(self, db, cargar):
        r = cargar([dict(CASCANUECES, **{"Precio Base": ""})])
        v = db.query(ProductVariant).one()
        assert Decimal(str(v.price)) == 0
        assert any("Precio Base" in i for i in r["incidencias"])

    def test_sku_repetido_en_la_org_recibe_sufijo(self, db, org, cargar):
        cargar([CASCANUECES])
        r = cargar([dict(CASCANUECES, Nombre="CASCANUECES GRANDE", **{"Codigo Barras": "111"})])
        skus = sorted(v.sku for v in db.query(ProductVariant))
        assert skus == ["8888172121301", "8888172121301-2"]
        assert r["codigos_generados"] == 1

    def test_empaques_y_unidad_se_ignoran_con_aviso(self, db, cargar):
        r = cargar([dict(CASCANUECES, **{"E1 Nombre": "Caja 12", "E1 Cantidad": 12, "E1 Precio": 2000})])
        assert r["creados"] == 1
        assert any("empaque" in i.lower() for i in r["incidencias"])

    def test_destino_ajeno_aborta(self, db, org, branch_a, tmp_path):
        from app.models.organization import Organization, Branch
        from app.modules.tenants.models import BranchType
        otra = Organization(name="Otra", status="ACTIVE"); db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        ruta = _xlsx(tmp_path, [CASCANUECES])
        with pytest.raises(ValueError, match="pertenece"):
            imp.import_rmazh_export(db, ruta, org.id, ajena.id)

    def test_sin_cabeceras_de_rmazh_aborta(self, db, org, branch_a, tmp_path):
        import zipfile as zf
        ruta = tmp_path / "otro.xlsx"
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        with zf.ZipFile(ruta, "w") as z:
            z.writestr("xl/sharedStrings.xml", f'<sst {ns} count="1" uniqueCount="1"><si><t>Código</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>')
        with pytest.raises(ValueError, match="cabeceras"):
            imp.import_rmazh_export(db, str(ruta), org.id, branch_a.id)
