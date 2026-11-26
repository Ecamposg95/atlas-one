"""Desglose fiscal de toda venta (app/services/desglose_fiscal.py).

Casos de centavo, descuentos, IVA incluido, mezcla de tasas, y que la suma de
los renglones sea exactamente lo cobrado.
"""
from decimal import Decimal

import pytest

from app.services.desglose_fiscal import (
    IVA_0,
    IVA_16,
    IVA_8,
    IVA_EXENTO,
    NO_OBJETO,
    desglosar_renglon,
    desglosar_venta,
    lugar_de_expedicion,
    normalizar_clave_prod_serv,
    normalizar_clave_unidad,
    normalizar_codigo_postal,
    normalizar_objeto_imp,
    normalizar_tratamiento_iva,
    repartir_a_centavos,
    tratamiento_de,
)

D = Decimal
T16 = tratamiento_de(IVA_16, None, None, None)
T8 = tratamiento_de(IVA_8, None, None, None)
T0 = tratamiento_de(IVA_0, None, None, None)
TEX = tratamiento_de(IVA_EXENTO, None, None, None)


# --- Tratamiento ---

def test_tratamiento_explicito_manda_sobre_banderas_de_la_variante():
    t = tratamiento_de(IVA_EXENTO, "02", True, 16)
    assert (t.clave, t.tipo_factor, t.tasa, t.inferido) == (IVA_EXENTO, "Exento", None, False)
    t = tratamiento_de(IVA_0, None, True, 16)
    assert (t.clave, t.tipo_factor, t.tasa, t.inferido) == (IVA_0, "Tasa", D("0.0000"), False)


def test_no_objeto_gana_sobre_todo():
    t = tratamiento_de(IVA_16, "01", True, 16)
    assert (t.clave, t.tipo_factor, t.tasa) == (NO_OBJETO, None, None)


@pytest.mark.parametrize("has_iva,tax_rate,esperada", [
    (True, 16, IVA_16),
    (True, D("8.00"), IVA_8),
    (False, 0, IVA_16),      # has_iva apagado no prueba tasa 0: se infiere la general
    (None, None, IVA_16),
    (False, 8, IVA_16),      # 8 sin IVA encendido no es frontera confiable
])
def test_inferencia_sin_tasa_capturada(has_iva, tax_rate, esperada):
    t = tratamiento_de(None, None, has_iva, tax_rate)
    assert t.clave == esperada
    assert t.inferido is True


# --- Renglón ---

@pytest.mark.parametrize("cobrado,base,iva", [
    ("116.00", "100.00", "16.00"),
    ("100.00", "86.21", "13.79"),   # precio con IVA incluido, sin factura
    ("0.01", "0.01", "0.00"),       # un centavo: todo es base
    ("0.02", "0.02", "0.00"),
    ("0.12", "0.10", "0.02"),
    ("11.59", "9.99", "1.60"),      # el caso del docstring de tax.py
    ("1.00", "0.86", "0.14"),
])
def test_renglon_16_base_mas_iva_igual_a_cobrado(cobrado, base, iva):
    r = desglosar_renglon(D(cobrado), T16)
    assert (r.base, r.iva) == (D(base), D(iva))
    assert r.base + r.iva == D(cobrado)


def test_renglon_8_frontera():
    r = desglosar_renglon(D("108.00"), T8)
    assert (r.base, r.iva) == (D("100.00"), D("8.00"))


@pytest.mark.parametrize("t", [T0, TEX])
def test_tasa_cero_y_exento_no_llevan_iva(t):
    r = desglosar_renglon(D("57.35"), t)
    assert (r.base, r.iva) == (D("57.35"), D("0.00"))


def test_iva_siempre_dentro_de_la_tolerancia_del_sat():
    """|iva - base*t| < 1 centavo para todo importe de 0.01 a 300.00."""
    for centavos in range(1, 30001):
        cobrado = D(centavos) / 100
        for t in (T16, T8):
            r = desglosar_renglon(cobrado, t)
            assert r.base + r.iva == cobrado
            assert abs(r.iva - r.base * t.tasa) < D("0.01"), (cobrado, t.clave)


def test_neto_con_factura_recupera_la_base_exacta():
    """Precio neto + IVA encima (venta con factura): derivar del cobrado
    devuelve la misma base y el mismo IVA que calculó el checkout."""
    for centavos in range(1, 20001):
        base = D(centavos) / 100
        iva = (base * D("0.16")).quantize(D("0.01"), rounding="ROUND_HALF_UP")
        r = desglosar_renglon(base + iva, T16)
        assert (r.base, r.iva) == (base, iva)


# --- Reparto de centavos ---

def test_reparto_sin_diferencia_solo_redondea():
    assert repartir_a_centavos([D("10.004"), D("5.006")], D("15.01")) == [D("10.00"), D("5.01")]


def test_reparto_absorbe_el_centavo_del_documento_en_el_renglon_mayor():
    # Tres renglones de 3.335 suman 10.005 → el documento redondea a 10.01,
    # cada renglón a 3.34 (=10.02): sobra un centavo y lo pierde el mayor (el primero).
    assert repartir_a_centavos([D("3.335")] * 3, D("10.01")) == [D("3.33"), D("3.34"), D("3.34")]


def test_reparto_falta_un_centavo():
    assert repartir_a_centavos([D("0.333")] * 3, D("1.00")) == [D("0.34"), D("0.33"), D("0.33")]


def test_reparto_no_deja_negativos():
    assert repartir_a_centavos([D("0"), D("0.004")], D("0.00")) == [D("0.00"), D("0.00")]


def test_reparto_vacio():
    assert repartir_a_centavos([], D("0")) == []


# --- Documento ---

def test_documento_con_mezcla_de_tasas_cuadra_con_lo_cobrado():
    renglones = [
        (D("116.00"), T16),
        (D("54.00"), T8),
        (D("23.50"), T0),
        (D("12.30"), TEX),
        (D("50.00"), tratamiento_de(None, "01", None, None)),
    ]
    d = desglosar_venta(renglones, D("255.80"))
    assert (d.base_16, d.iva_16) == (D("100.00"), D("16.00"))
    assert (d.base_8, d.iva_8) == (D("50.00"), D("4.00"))
    assert d.base_0 == D("23.50")
    assert d.base_exenta == D("12.30")
    assert d.base_no_objeto == D("50.00")
    assert d.total == D("255.80")


def test_documento_con_descuentos_por_renglon():
    """El checkout manda el importe ya descontado: 3 × 19.99 al 15 % = 50.9745."""
    bruto = D("19.99") * 3 * (1 - D("0.15"))
    d = desglosar_venta([(bruto, T16), (D("7.50") * (1 - D("0.5")), T16)], D("54.72"))
    assert d.total == D("54.72")
    assert [r.cobrado for r in d.renglones] == [D("50.97"), D("3.75")]
    assert d.base_16 + d.iva_16 == D("54.72")


def test_documento_iva_incluido_muchos_renglones_de_centavos():
    """Cien renglones de $0.05 con IVA incluido: cada uno queda en base pura
    (0.04 + 0.01) y la suma cuadra con los $5.00 cobrados."""
    d = desglosar_venta([(D("0.05"), T16)] * 100, D("5.00"))
    assert d.total == D("5.00")
    assert d.base_16 + d.iva_16 == D("5.00")
    for r in d.renglones:
        assert r.base + r.iva == D("0.05")


def test_documento_sin_redondeos_intermedios_cuadra_con_el_total_redondeado():
    """Como lo hace create_sale: acumula sin redondear y redondea el total una vez."""
    importes = [D("33.333") * D("1.16"), D("0.125") * D("1.16"), D("10.005") * D("1.16")]
    total = sum(importes).quantize(D("0.01"), rounding="ROUND_HALF_UP")
    d = desglosar_venta([(i, T16) for i in importes], total)
    assert d.total == total
    assert sum(r.cobrado for r in d.renglones) == total


def test_documento_vacio():
    d = desglosar_venta([], D("0"))
    assert d.total == D("0")


# --- Validaciones de formato ---

def test_formatos_validos_se_normalizan():
    assert normalizar_clave_prod_serv(" 01010101 ") == "01010101"
    assert normalizar_clave_unidad("h87") == "H87"
    assert normalizar_objeto_imp("02") == "02"
    assert normalizar_tratamiento_iva("16%") == "16"
    assert normalizar_tratamiento_iva("exento") == "EXENTO"
    assert normalizar_tratamiento_iva("8.00") == "8"
    assert normalizar_codigo_postal("06600") == "06600"
    for f in (normalizar_clave_prod_serv, normalizar_clave_unidad, normalizar_objeto_imp,
              normalizar_tratamiento_iva, normalizar_codigo_postal):
        assert f("") is None
        assert f(None) is None


@pytest.mark.parametrize("f,valor", [
    (normalizar_clave_prod_serv, "1010101"),
    (normalizar_clave_prod_serv, "0101010A"),
    (normalizar_clave_unidad, "H877"),
    (normalizar_clave_unidad, "H-8"),
    (normalizar_objeto_imp, "09"),
    (normalizar_objeto_imp, "2"),
    (normalizar_tratamiento_iva, "11"),
    (normalizar_codigo_postal, "6600"),
    (normalizar_codigo_postal, "06600-1"),
])
def test_formatos_invalidos(f, valor):
    with pytest.raises(ValueError):
        f(valor)


def test_lugar_de_expedicion_prefiere_la_sucursal():
    class S:
        postal_code = "64000"

    class Org:
        codigo_postal_fiscal = "06600"

    class SinCp:
        postal_code = "  "

    assert lugar_de_expedicion(S, Org) == "64000"
    assert lugar_de_expedicion(SinCp, Org) == "06600"
    assert lugar_de_expedicion(None, None) is None
