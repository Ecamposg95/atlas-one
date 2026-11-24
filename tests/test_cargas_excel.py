import io
import json
from decimal import Decimal

from openpyxl import Workbook

from app.modules.ai.proveedores import ProveedorFalso
from app.modules.cargas.lectura_excel import (
    ESQUEMA_MAPA, MapaColumnas, leer_tablas, mapear_columnas, renglones_desde_excel,
)
from app.modules.cargas.tipos import TablaCruda


def _tabla(filas, enc=("Descripción", "Cant", "Precio", "Costo")):
    return TablaCruda(pestana="Hoja1", encabezados=list(enc), filas=filas)


MAPA = MapaColumnas(campos={"descripcion_original": 0, "cantidad": 1}, columnas_dinero=[2, 3], texto_libre=[])


def test_lee_xlsx_con_dos_pestanas():
    wb = Workbook()
    a = wb.active
    a.title = "Uno"
    a.append(["Desc", "Cant"]); a.append([]); a.append(["Marca Uno bolsa", 3])
    b = wb.create_sheet("Dos")
    b.append(["Desc", "Cant"]); b.append(["Casa Dos cinto", 1]); b.append([None, None])
    buf = io.BytesIO(); wb.save(buf)
    t = leer_tablas(buf.getvalue(), "xlsx")
    assert [x.pestana for x in t] == ["Uno", "Dos"]
    assert t[0].encabezados == ["Desc", "Cant"]
    assert len(t[0].filas) == 1 and len(t[1].filas) == 1
    assert t[0].filas_origen == [3]


def test_lee_csv_punto_y_coma_latin1():
    raw = "Descripción;Cant;Precio\nCamión azul;2;10,5\nOtro;1;3\n".encode("latin-1")
    t = leer_tablas(raw, "csv")
    assert len(t) == 1
    assert t[0].encabezados == ["Descripción", "Cant", "Precio"]
    assert t[0].filas[0][0] == "Camión azul"


def test_mapear_usa_solo_20_filas_de_muestra():
    filas = [[f"Art {i}", i, 1, 1] for i in range(50)]
    falso = ProveedorFalso([{
        "campos": {"descripcion_original": 0, "cantidad": 1}, "columnas_dinero": [2, 3], "texto_libre": []}])
    mapa, _, _ = mapear_columnas(_tabla(filas), falso, "Tienda de bolsos")
    enviado = json.loads(falso.llamadas[0]["contenido"][0]["text"])
    assert len(enviado["filas_muestra"]) == 20
    assert "Tienda de bolsos" in falso.llamadas[0]["sistema"]
    assert mapa.campos["marca"] is None and mapa.columnas_dinero == [2, 3]


def test_mapear_descarta_indices_fuera_de_rango():
    falso = ProveedorFalso([{
        "campos": {"descripcion_original": 0, "cantidad": 9, "marca": -1}, "columnas_dinero": [2, 7], "texto_libre": [4]}])
    mapa, _, _ = mapear_columnas(_tabla([["a", 1, 1, 1]]), falso, "")
    assert mapa.campos["cantidad"] is None and mapa.campos["marca"] is None
    assert mapa.columnas_dinero == [2] and mapa.texto_libre == []


def test_esquema_estricto():
    def revisa(n):
        if n.get("type") == "object":
            assert n["additionalProperties"] is False
            assert set(n["required"]) == set(n["properties"])
            for v in n["properties"].values():
                revisa(v)
    revisa(ESQUEMA_MAPA)


def test_renglones_toman_valores_de_celdas_no_del_modelo():
    r = renglones_desde_excel(_tabla([["Bolsa", "3", "$1,250.50", 400]]), MAPA, {2: "precio", 3: "costo"})[0]
    assert r.cantidad == Decimal(3)
    assert r.precio == Decimal("1250.50") and r.costo_unitario == Decimal(400)
    assert r.origen == "Hoja1!R2"


def test_columna_dinero_sin_rol_no_llena_precio_ni_costo():
    r = renglones_desde_excel(_tabla([["Bolsa", 2, 100, 50]]), MAPA, {})[0]
    assert r.precio is None and r.costo_unitario is None


def test_dinero_vacio_o_basura_es_none_no_cero():
    r = renglones_desde_excel(_tabla([["Bolsa", 2, "", "n/d"]]), MAPA, {2: "precio", 3: "costo"})[0]
    assert r.precio is None and r.costo_unitario is None


def test_cantidad_vacia_o_cero_marca_duda():
    rs = renglones_desde_excel(_tabla([["A", None, 1, 1], ["B", 0, 1, 1], ["C", 2, 1, 1]]), MAPA, {})
    assert rs[0].duda == "Cantidad vacía" and rs[1].duda == "Cantidad vacía"
    assert rs[0].cantidad == 0 and rs[2].duda is None


def test_separadores_decimales_y_de_miles():
    from app.modules.cargas.lectura_excel import _importe
    casos = {"10,5": "10.5", "1,500": "1500", "1,500.50": "1500.50", "1.500,50": "1500.50",
             "$1,250,000": "1250000", "7": "7"}
    for texto, esperado in casos.items():
        assert _importe(texto) == Decimal(esperado), texto


def test_csv_coma_decimal_conserva_el_valor():
    t = leer_tablas("Desc;Cant;Precio\nBolsa;2;10,5\n".encode("latin-1"), "csv")[0]
    m = MapaColumnas(campos={"descripcion_original": 0, "cantidad": 1}, columnas_dinero=[2])
    assert renglones_desde_excel(t, m, {2: "precio"})[0].precio == Decimal("10.5")
