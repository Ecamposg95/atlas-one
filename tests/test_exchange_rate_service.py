"""Servicio puro del tipo de cambio USD: resolucion por modo y conversion.

Sin base de datos: `resolve_usd_rate` recibe la organizacion y la fila del FIX
duck-typed, asi que un SimpleNamespace basta (mismo patron que
tests/test_ticket_layout.py)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.exchange_rate import (
    MODO_AUTO,
    MODO_MANUAL,
    MODO_OFF,
    ResolvedRate,
    resolve_usd_rate,
    to_usd,
    validar_config_usd,
)


def _org(mode=MODO_OFF, manual=None, margin=0):
    return SimpleNamespace(usd_rate_mode=mode, usd_rate_manual=manual, usd_rate_margin=margin)


def _fix(rate="18.2000", dia=date(2026, 9, 17)):
    return SimpleNamespace(rate=Decimal(rate), rate_date=dia, currency="USD", source="banxico")


class TestResolveUsdRate:
    def test_modo_off_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(), _fix()) is None

    def test_organizacion_sin_las_columnas_es_off(self):
        # Organizacion legada leida antes del ALTER: no debe reventar.
        assert resolve_usd_rate(SimpleNamespace(), _fix()) is None

    def test_auto_suma_el_margen_al_fix(self):
        r = resolve_usd_rate(_org(MODO_AUTO, margin=Decimal("0.30")), _fix("18.2000"))
        assert r == ResolvedRate(
            rate=Decimal("18.5000"), source="banxico",
            fix_rate=Decimal("18.2000"), fix_date=date(2026, 9, 17),
        )

    def test_auto_sin_fix_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(MODO_AUTO, margin=Decimal("0.30")), None) is None

    def test_auto_con_margen_que_anula_el_tipo_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(MODO_AUTO, margin=Decimal("-20")), _fix("18.2000")) is None

    def test_manual_manda_sobre_el_fix(self):
        r = resolve_usd_rate(
            _org(MODO_MANUAL, manual=Decimal("19.5000"), margin=Decimal("0.30")), _fix()
        )
        assert r.rate == Decimal("19.5000")
        assert r.source == "manual"
        # El FIX viaja igual, informativo, para que el panel lo muestre.
        assert r.fix_rate == Decimal("18.2000")

    def test_manual_sin_tipo_capturado_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(MODO_MANUAL, manual=None), _fix()) is None
        assert resolve_usd_rate(_org(MODO_MANUAL, manual=Decimal("0")), _fix()) is None

    def test_el_float_de_sqlite_no_rompe_la_precision(self):
        r = resolve_usd_rate(_org(MODO_AUTO, margin=0.3), _fix("18.2"))
        assert r.rate == Decimal("18.5000")

    def test_el_modo_no_distingue_mayusculas(self):
        assert resolve_usd_rate(_org(" AUTO "), _fix()).rate == Decimal("18.2000")


class TestToUsd:
    @pytest.mark.parametrize("mxn,tasa,esperado", [
        ("185.00", "18.5000", "10.00"),
        ("100.00", "18.5000", "5.41"),    # 5.4054... -> HALF_UP
        ("0", "18.5000", "0.00"),
        ("18.50", "18.5", "1.00"),
    ])
    def test_convierte_y_redondea_a_centavos(self, mxn, tasa, esperado):
        assert to_usd(Decimal(mxn), Decimal(tasa)) == Decimal(esperado)

    def test_tasa_invalida_devuelve_cero(self):
        assert to_usd(Decimal("100"), Decimal("0")) == Decimal("0.00")
        assert to_usd(Decimal("100"), None) == Decimal("0.00")

    def test_acepta_float_y_none(self):
        assert to_usd(None, Decimal("18.5")) == Decimal("0.00")
        assert to_usd(185.0, 18.5) == Decimal("10.00")


class TestValidarConfig:
    def test_modo_desconocido(self):
        with pytest.raises(ValueError):
            validar_config_usd("dolares", None, 0)

    def test_manual_sin_tipo(self):
        with pytest.raises(ValueError):
            validar_config_usd(MODO_MANUAL, None, 0)
        with pytest.raises(ValueError):
            validar_config_usd(MODO_MANUAL, Decimal("0"), 0)

    def test_margen_absurdo(self):
        with pytest.raises(ValueError):
            validar_config_usd(MODO_AUTO, None, Decimal("80"))

    def test_configuraciones_validas(self):
        validar_config_usd(MODO_OFF, None, 0)
        validar_config_usd(MODO_AUTO, None, Decimal("0.30"))
        validar_config_usd(MODO_AUTO, None, Decimal("-0.10"))
        validar_config_usd(MODO_MANUAL, Decimal("19.5"), 0)
