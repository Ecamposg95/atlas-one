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
        # Unidad "pza" sin empaques no avisa nada.
        r2 = cargar([CASCANUECES])
        assert not any("empaque" in i.lower() for i in r2["incidencias"])

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


class TestEscalones:
    def test_un_escalon_con_su_nombre_y_minimo(self, db, cargar):
        r = cargar([CASCANUECES])
        assert r["escalones"] == 1
        e = db.query(ProductPrice).one()
        assert e.price_name == "Mayoreo"
        assert Decimal(str(e.min_quantity)) == 3 and Decimal(str(e.unit_price)) == 210

    def test_dos_escalones_conservan_caja(self, db, cargar):
        r = cargar([STITCH])
        assert r["escalones"] == 2
        nombres = {e.price_name: (Decimal(str(e.min_quantity)), Decimal(str(e.unit_price))) for e in db.query(ProductPrice)}
        assert nombres == {"Mayoreo": (Decimal("3"), Decimal("120")), "Caja": (Decimal("12"), Decimal("100"))}

    def test_nombres_numerados_de_rmazh_se_respetan(self, db, cargar):
        cargar([dict(CASCANUECES, **{"P1 Nombre": "Precio 1", "P2 Nombre": "Precio 2", "P2 Min": 6, "P2 Precio": 200})])
        assert {e.price_name for e in db.query(ProductPrice)} == {"Precio 1", "Precio 2"}

    def test_min_vacio_es_uno(self, db, cargar):
        cargar([dict(CASCANUECES, **{"P1 Min": ""})])
        assert Decimal(str(db.query(ProductPrice).one().min_quantity)) == 1

    def test_escalon_sin_precio_no_se_crea_y_avisa(self, db, cargar):
        r = cargar([dict(CASCANUECES, **{"P1 Precio": ""})])
        assert db.query(ProductPrice).count() == 0
        assert any("Mayoreo" in i and "sin precio" in i for i in r["incidencias"])

    def test_escalon_mas_caro_que_el_base_se_carga_y_avisa(self, db, cargar):
        """Review Focus #1: no se corrige en silencio."""
        r = cargar([dict(CASCANUECES, **{"P1 Precio": 300})])
        assert Decimal(str(db.query(ProductPrice).one().unit_price)) == 300
        assert any("mayor que el Precio Base" in i for i in r["incidencias"])

    def test_recorrer_refresca_el_escalon_sin_duplicarlo(self, db, cargar):
        cargar([CASCANUECES])
        cargar([dict(CASCANUECES, **{"P1 Precio": 205})])
        e = db.query(ProductPrice).one()
        assert Decimal(str(e.unit_price)) == 205


class TestExistencias:
    def test_stock_entra_como_movimiento_con_referencia(self, db, org, branch_a, admin_user, cargar):
        r = cargar([CASCANUECES])
        assert r["movimientos"] == 1
        s = db.query(StockOnHand).filter_by(branch_id=branch_a.id).one()
        assert Decimal(str(s.qty_on_hand)) == 2556 and s.is_active is True
        m = db.query(InventoryMovement).one()
        assert m.movement_type == MovementType.ADJUSTMENT_IN
        assert m.reference == imp.REFERENCIA_CARGA
        assert Decimal(str(m.qty_change)) == 2556 and Decimal(str(m.qty_before)) == 0 and Decimal(str(m.qty_after)) == 2556
        assert m.user_id == admin_user.id
        assert m.organization_id == org.id

    def test_stock_cero_crea_fila_sin_movimiento(self, db, branch_a, cargar):
        r = cargar([dict(CASCANUECES, Stock=0)])
        assert r["movimientos"] == 0
        assert db.query(StockOnHand).filter_by(branch_id=branch_a.id).count() == 1
        assert db.query(InventoryMovement).count() == 0

    def test_mayores_a_500_se_listan_y_entran_tal_cual(self, db, cargar):
        r = cargar([CASCANUECES, STITCH])
        assert sorted(r["existencias_altas"]) == [
            ("8888172121301", "CASCANUECES", Decimal("2556")),
            ("STITCH", "STITCH", Decimal("10000")),
        ]
        qty = {v.sku: Decimal(str(s.qty_on_hand)) for s, v in db.query(StockOnHand, ProductVariant).join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)}
        assert qty == {"8888172121301": Decimal("2556"), "STITCH": Decimal("10000")}

    def test_tope_recorta_y_avisa(self, db, cargar):
        r = cargar([STITCH, dict(CASCANUECES, Stock=40)], tope=Decimal("50"))
        qty = {v.sku: Decimal(str(s.qty_on_hand)) for s, v in db.query(StockOnHand, ProductVariant).join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)}
        assert qty == {"STITCH": Decimal("50"), "8888172121301": Decimal("40")}
        assert any("STITCH" in i and "tope" in i for i in r["incidencias"])
        assert Decimal(str(db.query(InventoryMovement).filter_by(variant_id=db.query(ProductVariant).filter_by(sku="STITCH").one().id).one().qty_change)) == 50


class TestCarrySobre:
    def test_codigo_de_barras_repetido_avisa_ambiguo(self, db, cargar):
        r = cargar([
            dict(CASCANUECES, SKU="A1", Nombre="UNO", **{"Codigo Barras": "777"}),
            dict(CASCANUECES, SKU="A2", Nombre="DOS", **{"Codigo Barras": "777"}),
        ])
        assert r["creados"] == 2
        assert db.query(ProductVariant).count() == 2
        avisos = [i for i in r["incidencias"] if "ambiguo" in i]
        assert len(avisos) == 1 and "777" in avisos[0] and "A1" in avisos[0]

    def test_existencias_existentes_se_reactivan(self, db, org, branch_a, cargar):
        cargar([STITCH])
        v = db.query(ProductVariant).one()
        s = db.query(StockOnHand).filter_by(variant_id=v.id).one()
        s.is_active = False
        db.flush()
        cargar([STITCH])
        assert db.query(StockOnHand).filter_by(variant_id=v.id).one().is_active is True


class TestIdempotencia:
    def test_segunda_corrida_no_duplica_ni_recarga_stock(self, db, org, cargar):
        cargar([CASCANUECES, STITCH])
        r = cargar([CASCANUECES, STITCH])
        assert r["creados"] == 0 and r["actualizados"] == 2
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 2
        assert db.query(ProductVariant).count() == 2
        assert db.query(ProductPrice).count() == 3
        assert db.query(InventoryMovement).count() == 2, "el stock no se vuelve a cargar"
        qty = {v.sku: Decimal(str(s.qty_on_hand)) for s, v in db.query(StockOnHand, ProductVariant).join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)}
        assert qty == {"8888172121301": Decimal("2556"), "STITCH": Decimal("10000")}

    def test_renglon_duplicado_en_el_mismo_archivo(self, db, cargar):
        """Review Focus #2: misma (codigo, nombre) dos veces = un producto, un movimiento."""
        r = cargar([CASCANUECES, dict(CASCANUECES, Stock=999)])
        assert r["creados"] == 1 and r["actualizados"] == 1
        assert db.query(Product).count() == 1
        assert db.query(InventoryMovement).count() == 1
        assert Decimal(str(db.query(StockOnHand).one().qty_on_hand)) == 2556


class TestDryRun:
    def test_dry_run_reporta_sin_escribir(self, db, org, cargar):
        r = cargar([CASCANUECES, STITCH], dry_run=True)
        assert r["creados"] == 2 and r["escalones"] == 3 and r["movimientos"] == 2
        assert len(r["existencias_altas"]) == 2
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 0
        assert db.query(InventoryMovement).count() == 0
        assert db.query(Department).count() == 0


class TestCLI:
    def test_pos_search_lee_lo_cargado(self, db, org, branch_a, cargar):
        """Lo que tumba al POS es un NULL en price/cost: el schema de lectura debe aceptar todo."""
        from app.modules.products.schemas import ProductRead
        cargar([CASCANUECES, dict(STITCH, Costo="")])
        for p in db.query(Product).filter(Product.organization_id == org.id):
            ProductRead.model_validate(p)

    def test_main_dry_run_imprime_resumen(self, db, org, branch_a, admin_user, tmp_path, monkeypatch, capsys):
        import sys as _sys
        ruta = _xlsx(tmp_path, [CASCANUECES, STITCH])
        monkeypatch.setattr(_sys, "argv", ["import_rmazh_export.py", ruta, "--org", str(org.id), "--branch", str(branch_a.id), "--dry-run"])
        # El CLI abre su propia sesion; se le presta la de la prueba.
        import app.core.database as database
        monkeypatch.setattr(database, "SessionLocal", lambda: db)
        monkeypatch.setattr(db, "close", lambda: None)
        imp.main()
        out = capsys.readouterr().out
        assert "ENSAYO" in out and "productos creados      2" in out
        assert "EXISTENCIAS MAYORES A 500" in out and "STITCH" in out and "10000" in out


class TestEscalonesSinDuplicar:
    def test_rerun_con_renglon_repetido_no_duplica_escalon_nuevo(self, db, cargar):
        cargar([CASCANUECES])
        fila = dict(CASCANUECES, **{"P2 Nombre": "Caja", "P2 Min": 12, "P2 Precio": 200})
        cargar([fila, fila])
        nombres = [p.price_name for p in db.query(ProductPrice).all()]
        assert sorted(nombres) == ["Caja", "Mayoreo"]

    def test_dos_pn_con_el_mismo_nombre_dejan_un_escalon(self, db, cargar):
        cargar([dict(CASCANUECES, **{"P2 Nombre": "Mayoreo", "P2 Min": 6, "P2 Precio": 200})])
        escalones = db.query(ProductPrice).all()
        assert len(escalones) == 1 and escalones[0].price_name == "Mayoreo"
        # Gana el ultimo Pn del renglon.
        assert Decimal(str(escalones[0].min_quantity)) == 6 and Decimal(str(escalones[0].unit_price)) == 200
