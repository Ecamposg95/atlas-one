"""El ZPL de la etiqueta 51 x 25 mm, carácter por carácter.

La geometría está PORTADA del agente de impresión y la tienda ya la validó en
papel: si alguien mueve una coordenada, una altura o un margen, estas pruebas
tienen que ponerse rojas. Por eso las etiquetas esperadas van literales y no
calculadas.
"""
from decimal import Decimal

import pytest

from app.services.labels import (
    BARCODE_HEIGHT,
    LABEL_HEIGHT,
    LABEL_WIDTH,
    MARGIN,
    Bars,
    DatosEtiqueta,
    build_batch,
    build_label,
    build_test_label,
    detect,
    ean13_checksum_ok,
    fit_text,
    layout,
    zpl_safe,
)

CHAMARRA = DatosEtiqueta(
    sku="LV-CHAM-SLI-NEG-M",
    name="Chamarra mezclilla Slim",
    brand="Louis Vuitton",
    barcode="2017000000013",
    price=Decimal("1800.00"),
    size="M",
    color="Negro",
)

ETIQUETA_CHAMARRA = (
    "^XA\n"
    "^PW408\n"
    "^LL200\n"
    "^LH0,0\n"
    "^CI28\n"
    "^PQ1\n"
    "^FO12,8^A0N,22,22^FDLouis Vuitton^FS\n"
    "^FO12,34^A0N,18,18^FDChamarra mezclilla Slim^FS\n"
    "^FO12,56^A0N,15,15^FDM / Negro^FS\n"
    "^FO109,76^BY2,2,48\n"
    "^BEN,48,Y,N^FD2017000000013^FS\n"
    "^FO12,168^A0N,14,14^FDLV-CHAM-SLI-NEG-M^FS\n"
    "^FO246,162^A0N,22,22^FB150,1,0,R^FD$1,800.00^FS\n"
    "^XZ"
)


def test_geometria_de_la_etiqueta():
    """Lienzo, margen y alto del código: los dots que la Zebra ya imprimió."""
    assert (LABEL_WIDTH, LABEL_HEIGHT, MARGIN, BARCODE_HEIGHT) == (408, 200, 12, 48)


def test_etiqueta_conocida_caracter_por_caracter():
    assert build_label(CHAMARRA, 1) == ETIQUETA_CHAMARRA


def test_copias_van_en_pq():
    assert "^PQ7\n" in build_label(CHAMARRA, 7)
    # 0 o negativos nunca imprimen "cero etiquetas": la Zebra pide >= 1.
    assert "^PQ1\n" in build_label(CHAMARRA, 0)


def test_lote_concatena_bloques():
    lote = build_batch([(CHAMARRA, 2), (CHAMARRA, 1)])
    assert lote.count("^XA") == 2
    assert lote.count("^XZ") == 2
    assert lote == build_label(CHAMARRA, 2) + "\n" + build_label(CHAMARRA, 1) + "\n"


def test_etiqueta_de_prueba_es_la_del_agente():
    prueba = build_test_label()
    assert "^FDPRUEBA-51X25^FS" in prueba
    assert "^BEN,48,Y,N^FD2017000000013^FS" in prueba


# ── Código de barras ─────────────────────────────────────────────────────────
def test_ean13_valido_usa_be():
    assert ean13_checksum_ok("2017000000013")
    spec = detect("2017000000013")
    assert (spec.kind, spec.module_width) == ("EAN13", 2)
    assert len(spec.bits) == 95
    assert spec.width_dots == 190
    assert "^BEN,48,Y,N^FD2017000000013^FS" in build_label(CHAMARRA)


def test_checksum_malo_cae_en_code128():
    """Un "EAN" con dígito verificador equivocado NO se imprime como EAN-13:
    la Zebra lo rechazaría. Se respalda con Code 128."""
    assert not ean13_checksum_ok("2017000000014")
    spec = detect("2017000000014")
    assert spec.kind == "CODE128"
    datos = DatosEtiqueta(sku="X", name="X", barcode="2017000000014")
    assert "^BCN,48,Y,N,N,A^FD2017000000014^FS" in build_label(datos)


def test_alfanumerico_es_code128():
    spec = detect("ABC-123")
    assert (spec.kind, spec.data) == ("CODE128", "ABC-123")


def test_code128_largo_baja_a_un_dot_por_modulo():
    """Un código largo se imprime angosto antes que salirse de la etiqueta."""
    spec = detect("ABCDEFGHIJKLMNOPQR")
    assert spec.module_width == 1
    assert "angosto" in spec.warning
    assert spec.width_dots <= 358


def test_codigo_vacio_no_tiene_spec():
    assert detect("") is None
    assert detect(None) is None
    assert detect("   ") is None


def test_layout_sin_codigo_revienta():
    with pytest.raises(ValueError):
        layout(DatosEtiqueta(sku="SIN-CODIGO", name="Playera"))


# ── Texto ────────────────────────────────────────────────────────────────────
def test_texto_largo_se_recorta_con_dos_puntos():
    """El nombre que no cabe en 384 dots se recorta; nunca se desborda."""
    largo = "Chamarra de mezclilla premium con forro polar y capucha desmontable"
    datos = DatosEtiqueta(sku="X", name=largo, barcode="2017000000013")
    etiqueta = build_label(datos)
    recortado = fit_text(largo, 18, LABEL_WIDTH - 2 * MARGIN)
    assert recortado.endswith("..")
    assert len(recortado) < len(largo)
    assert f"^FD{recortado}^FS" in etiqueta
    assert largo not in etiqueta


def test_acento_y_ene_sobreviven():
    """`^CI28` (UTF-8) va en la cabecera: "Camisón" se imprime como se escribe."""
    datos = DatosEtiqueta(sku="X", name="Camisón niña", barcode="2017000000013")
    etiqueta = build_label(datos)
    assert "^CI28" in etiqueta
    assert "^FDCamisón niña^FS" in etiqueta


def test_acento_y_tilde_de_control_se_neutralizan():
    """`^` y `~` son los prefijos de comando de ZPL: dentro de un texto de la
    tienda partirían la etiqueta en dos. Se cambian por espacio."""
    assert zpl_safe("Blusa ^XA ~JA") == "Blusa  XA  JA"
    datos = DatosEtiqueta(sku="A^B", name="Blusa ^XA", brand="~JA", barcode="2017000000013")
    etiqueta = build_label(datos)
    cuerpo = etiqueta.split("^PQ1\n", 1)[1]
    # Los únicos comandos del cuerpo son los que genera el layout.
    assert "^XA" not in cuerpo
    assert "~" not in cuerpo
    assert "^FDBlusa  XA^FS" in etiqueta


def test_variante_sin_talla_ni_color_no_pinta_el_renglon():
    datos = DatosEtiqueta(sku="X", name="Refresco", barcode="2017000000013")
    assert "^FO12,56" not in build_label(datos)


def test_precio_vacio_no_pinta_el_renglon():
    datos = DatosEtiqueta(sku="X", name="Playera", barcode="2017000000013")
    assert "^FB150,1,0,R" not in build_label(datos)


def test_layout_es_la_misma_fuente_que_el_zpl():
    """La vista previa dibuja `layout()`; el ZPL sale de `layout()`. Si se
    separaran, la pantalla podría mentir sobre lo que sale del rollo."""
    elementos = layout(CHAMARRA)
    barras = [e for e in elementos if isinstance(e, Bars)]
    assert len(barras) == 1
    assert barras[0].y == 76
    assert barras[0].x == (LABEL_WIDTH - barras[0].module_width * len(barras[0].bits)) // 2
    for elemento in elementos:
        if not isinstance(elemento, Bars):
            assert f"^FO{elemento.x},{elemento.y}" in ETIQUETA_CHAMARRA
