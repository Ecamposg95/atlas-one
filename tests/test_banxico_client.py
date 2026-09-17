"""Cliente del SIE de Banxico. NUNCA sale a la red: `httpx.get` va parcheado."""
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services import banxico
from app.services.banxico import BanxicoError, fetch_fix, token_configurado


class _Respuesta:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _payload(fecha="17/09/2026", dato="18.2345"):
    return {"bmx": {"series": [{
        "idSerie": "SF43718",
        "titulo": "Tipo de cambio pesos por dólar E.U.A.",
        "datos": [{"fecha": fecha, "dato": dato}],
    }]}}


def _parchear(monkeypatch, respuesta):
    """Sustituye httpx.get y devuelve un dict con lo que se llamo."""
    llamada = {}

    def _fake_get(url, params=None, headers=None, timeout=None):
        llamada["url"] = url
        llamada["params"] = params
        llamada["timeout"] = timeout
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(banxico.httpx, "get", _fake_get)
    return llamada


def test_devuelve_fecha_y_tipo(monkeypatch):
    llamada = _parchear(monkeypatch, _Respuesta(_payload()))
    dia, tipo = fetch_fix("tok")
    assert dia == date(2026, 9, 17)
    assert tipo == Decimal("18.2345")
    assert "SF43718" in llamada["url"]
    assert llamada["params"] == {"token": "tok"}
    assert llamada["timeout"] == 10.0


def test_dia_inhabil_devuelve_ne_y_es_error(monkeypatch):
    # Banxico responde 'N/E' en sabados, domingos y feriados.
    _parchear(monkeypatch, _Respuesta(_payload(dato="N/E")))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_http_distinto_de_200(monkeypatch):
    _parchear(monkeypatch, _Respuesta(_payload(), status_code=401))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_json_con_otra_forma(monkeypatch):
    _parchear(monkeypatch, _Respuesta({"bmx": {"series": []}}))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_fecha_con_otro_formato(monkeypatch):
    _parchear(monkeypatch, _Respuesta(_payload(fecha="2026-09-17")))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_error_de_red(monkeypatch):
    _parchear(monkeypatch, httpx.ConnectError("sin red"))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_sin_token_no_toca_la_red(monkeypatch):
    def _explota(*a, **k):
        raise AssertionError("no debe llamar a Banxico sin token")

    monkeypatch.setattr(banxico.httpx, "get", _explota)
    with pytest.raises(BanxicoError):
        fetch_fix("")


def test_token_configurado_lee_el_entorno(monkeypatch):
    monkeypatch.delenv("BANXICO_TOKEN", raising=False)
    assert token_configurado() is None
    monkeypatch.setenv("BANXICO_TOKEN", "   ")
    assert token_configurado() is None
    monkeypatch.setenv("BANXICO_TOKEN", "abc123")
    assert token_configurado() == "abc123"
