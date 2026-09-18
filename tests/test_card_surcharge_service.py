"""Servicio puro de la comision por pago con tarjeta.

Sin base de datos: `calcular_comision` recibe los pagos duck-typed, asi que un
SimpleNamespace basta (mismo patron que tests/test_exchange_rate_service.py).

La invariante que sostiene todo el diseño: `total_a_pagar = total + monto` y
`pago_tarjeta = base + monto`. Si alguna de las dos deja de valer, el cajero
cobra de mas o de menos."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.card_surcharge import (
    CERO,
    PCT_MAXIMO,
    ComisionTarjeta,
    calcular_comision,
    hay_pago_con_tarjeta,
    pct_de_organizacion,
    validar_pct,
)


def _pago(method, amount):
    return SimpleNamespace(method=method, amount=Decimal(str(amount)))


class TestPctDeOrganizacion:
    def test_organizacion_sin_la_columna_es_cero(self):
        # Organizacion legada leida antes del ALTER: no debe reventar.
        assert pct_de_organizacion(SimpleNamespace()) == CERO

    def test_none_es_cero(self):
        assert pct_de_organizacion(None) == CERO
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=None)) == CERO

    def test_lee_el_porcentaje(self):
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=Decimal("3.5"))) == Decimal("3.50")

    def test_el_float_de_sqlite_no_rompe_la_precision(self):
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=3.5)) == Decimal("3.50")

    def test_un_porcentaje_negativo_se_trata_como_apagado(self):
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=Decimal("-1"))) == CERO


class TestHayPagoConTarjeta:
    def test_reconoce_el_enum_y_el_string(self):
        from app.models.sales import PaymentMethod

        assert hay_pago_con_tarjeta([_pago(PaymentMethod.CARD, "10")]) is True
        assert hay_pago_con_tarjeta([_pago("card", "10")]) is True
        assert hay_pago_con_tarjeta([_pago("CASH", "10")]) is False

    def test_lista_vacia_o_none(self):
        assert hay_pago_con_tarjeta([]) is False
        assert hay_pago_con_tarjeta(None) is False


class TestCalcularComision:
    def test_sin_porcentaje_no_hay_comision(self):
        # Neutralidad: es el estado de TODA organizacion existente.
        c = calcular_comision(Decimal("1000.00"), [_pago("CARD", "1000")], Decimal("0"))
        assert c == ComisionTarjeta(
            base=CERO, pct=CERO, monto=CERO,
            pago_tarjeta=CERO, total_a_pagar=Decimal("1000.00"),
        )

    def test_sin_pago_con_tarjeta_no_hay_comision(self):
        c = calcular_comision(Decimal("1000.00"), [_pago("CASH", "1000")], Decimal("3.5"))
        assert c.monto == CERO
        assert c.pct == CERO
        assert c.total_a_pagar == Decimal("1000.00")

    def test_sin_pagos_no_hay_comision(self):
        # Venta a credito puro: no hay nada que cobrar todavia.
        assert calcular_comision(Decimal("1000.00"), [], Decimal("3.5")).monto == CERO

    def test_cien_por_ciento_tarjeta(self):
        c = calcular_comision(Decimal("1000.00"), [_pago("CARD", "1035")], Decimal("3.5"))
        assert c.base == Decimal("1000.00")
        assert c.pct == Decimal("3.50")
        assert c.monto == Decimal("35.00")
        assert c.pago_tarjeta == Decimal("1035.00")
        assert c.total_a_pagar == Decimal("1035.00")

    def test_mixto_solo_cobra_la_parte_de_tarjeta(self):
        # Ejemplo B del diseño: $1,000 de mercancia, $400 en efectivo.
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("CASH", "400"), _pago("CARD", "621")],
            Decimal("3.5"),
        )
        assert c.base == Decimal("600.00")
        assert c.monto == Decimal("21.00")
        assert c.pago_tarjeta == Decimal("621.00")
        assert c.total_a_pagar == Decimal("1021.00")

    def test_el_efectivo_que_cubre_todo_deja_la_base_en_cero(self):
        # El cajero teclea un billete grande: la base no puede irse a negativo.
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("CASH", "1200"), _pago("CARD", "50")],
            Decimal("3.5"),
        )
        assert c.base == CERO
        assert c.monto == CERO
        assert c.pct == CERO
        assert c.total_a_pagar == Decimal("1000.00")

    def test_la_transferencia_tambien_es_base_sin_comision(self):
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("TRANSFER", "700"), _pago("CARD", "310.50")],
            Decimal("3.5"),
        )
        assert c.base == Decimal("300.00")
        assert c.monto == Decimal("10.50")

    def test_dos_renglones_de_tarjeta_suman_una_sola_base(self):
        # Dos terminales distintas en la misma venta: la comision se calcula
        # sobre lo que NO es tarjeta, no sobre cada renglon.
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("CARD", "500"), _pago("CARD", "535")],
            Decimal("3.5"),
        )
        assert c.base == Decimal("1000.00")
        assert c.monto == Decimal("35.00")

    def test_redondea_medio_centavo_hacia_arriba(self):
        # Ejemplo F del diseño: 333.33 x 3.5% = 11.66655 -> 11.67 (HALF_UP).
        c = calcular_comision(Decimal("333.33"), [_pago("CARD", "345")], Decimal("3.5"))
        assert c.monto == Decimal("11.67")
        assert c.total_a_pagar == Decimal("345.00")

    def test_acepta_strings_y_floats(self):
        c = calcular_comision("1000.00", [SimpleNamespace(method="CARD", amount=1035.0)], "3.5")
        assert c.monto == Decimal("35.00")

    def test_acepta_pagos_como_diccionarios(self):
        # `payments_detail` del router de impresion viaja como lista de dicts.
        c = calcular_comision(
            Decimal("1000.00"),
            [{"method": "CASH", "amount": "400"}, {"method": "CARD", "amount": "621"}],
            Decimal("3.5"),
        )
        assert c.monto == Decimal("21.00")

    def test_porcentaje_negativo_se_trata_como_cero(self):
        assert calcular_comision(Decimal("100"), [_pago("CARD", "100")], Decimal("-3")).monto == CERO

    @pytest.mark.parametrize("total,efectivo,pct", [
        ("1000.00", "0", "3.5"),
        ("1000.00", "400", "3.5"),
        ("333.33", "0", "2.9"),
        ("19.99", "5", "20"),
    ])
    def test_las_dos_invariantes_siempre_valen(self, total, efectivo, pct):
        pagos = [_pago("CARD", "0")]
        if Decimal(efectivo) > 0:
            pagos.append(_pago("CASH", efectivo))
        c = calcular_comision(Decimal(total), pagos, Decimal(pct))
        assert c.total_a_pagar == Decimal(total) + c.monto
        assert c.pago_tarjeta == c.base + c.monto


class TestValidarPct:
    def test_valores_validos(self):
        validar_pct(0)
        validar_pct(Decimal("3.5"))
        validar_pct(PCT_MAXIMO)

    def test_negativo(self):
        with pytest.raises(ValueError):
            validar_pct(Decimal("-0.01"))

    def test_por_encima_del_tope(self):
        # Guardarail contra el dedo gordo: 35 en vez de 3.5.
        with pytest.raises(ValueError):
            validar_pct(Decimal("35"))

    def test_no_numerico(self):
        with pytest.raises(ValueError):
            validar_pct("tres y medio")
