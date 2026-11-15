"""Cliente estructurado de Anthropic: nunca toca la red (SDK sustituido por dobles)."""
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi import HTTPException

from app.modules.ai.cliente_anthropic import (
    ClienteAnthropic, ClienteEstructuradoFalso, ProveedorNoDisponible,
    cliente_estructurado_por_defecto,
)

ESQUEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}


def test_falso_devuelve_guion_y_registra_llamadas():
    falso = ClienteEstructuradoFalso([{"a": 1}])
    r = falso.generar(sistema="s", contenido=[{"type": "text", "text": "x"}], esquema=ESQUEMA)
    assert r.datos == {"a": 1}
    assert len(falso.llamadas) == 1
    assert falso.llamadas[0]["esquema"] is ESQUEMA


def test_falso_propaga_excepcion_del_guion():
    falso = ClienteEstructuradoFalso([ProveedorNoDisponible("x")])
    with pytest.raises(ProveedorNoDisponible):
        falso.generar(sistema="s", contenido=[], esquema=ESQUEMA)


def test_sin_clave_da_503(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(HTTPException) as e:
        cliente_estructurado_por_defecto()
    assert e.value.status_code == 503
    assert "ANTHROPIC_API_KEY" in e.value.detail


def test_modelo_por_omision_y_por_variable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("AI_MODELO", raising=False)
    assert cliente_estructurado_por_defecto().modelo == "claude-opus-5-5"
    monkeypatch.setenv("AI_MODELO", "otro-modelo")
    assert cliente_estructurado_por_defecto().modelo == "otro-modelo"


def _sdk_falso(monkeypatch, mensaje=None, error=None, capturar=None, constructor=None):
    class Flujo:
        def __init__(self, kw):
            self.kw = kw

        def __enter__(self):
            if error:
                raise error
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return mensaje

    class Falso:
        def __init__(self, api_key=None, **kw):
            if constructor is not None:
                constructor.update(kw, api_key=api_key)
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

        def _stream(self, **kw):
            if capturar is not None:
                capturar.update(kw)
            return Flujo(kw)

    monkeypatch.setattr(anthropic, "Anthropic", Falso)


def _mensaje(texto='{"a": 2}', stop="end_turn"):
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="text", text=texto)],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
    )


def test_respuesta_valida_y_argumentos_del_sdk(monkeypatch):
    kw = {}
    _sdk_falso(monkeypatch, mensaje=_mensaje(), capturar=kw)
    r = ClienteAnthropic("k", "m").generar(sistema="s", contenido=[{"type": "text", "text": "x"}], esquema=ESQUEMA)
    assert (r.datos, r.tokens_entrada, r.tokens_salida) == ({"a": 2}, 11, 7)
    assert kw["model"] == "m" and kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["output_config"] == {"format": {"type": "json_schema", "schema": ESQUEMA}}
    assert "thinking" not in kw


def test_refusal_se_vuelve_proveedor_no_disponible(monkeypatch):
    _sdk_falso(monkeypatch, mensaje=_mensaje(stop="refusal"))
    with pytest.raises(ProveedorNoDisponible):
        ClienteAnthropic("k", "m").generar(sistema="s", contenido=[], esquema=ESQUEMA)


def test_json_invalido_se_vuelve_proveedor_no_disponible(monkeypatch):
    _sdk_falso(monkeypatch, mensaje=_mensaje(texto="no es json"))
    with pytest.raises(ProveedorNoDisponible):
        ClienteAnthropic("k", "m").generar(sistema="s", contenido=[], esquema=ESQUEMA)


@pytest.mark.parametrize("hacer", [
    lambda req: anthropic.APIConnectionError(request=req),
    lambda req: anthropic.RateLimitError("x", response=httpx.Response(429, request=req), body=None),
])
def test_error_de_api_se_vuelve_proveedor_no_disponible(monkeypatch, hacer):
    req = httpx.Request("POST", "https://invalido.local")
    _sdk_falso(monkeypatch, error=hacer(req))
    with pytest.raises(ProveedorNoDisponible):
        ClienteAnthropic("k", "m").generar(sistema="s", contenido=[], esquema=ESQUEMA)


def test_timeout_y_reintentos_explicitos(monkeypatch):
    """Tope de tiempo de la lectura (spec §7): 300 s y un solo reintento por omisión."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("AI_TIMEOUT_SEG", raising=False)
    construido = {}
    _sdk_falso(monkeypatch, mensaje=_mensaje(), constructor=construido)
    cliente_estructurado_por_defecto().generar(sistema="s", contenido=[], esquema=ESQUEMA)
    assert construido["timeout"] == 300.0 and construido["max_retries"] == 1

    monkeypatch.setenv("AI_TIMEOUT_SEG", "90")
    cliente_estructurado_por_defecto().generar(sistema="s", contenido=[], esquema=ESQUEMA)
    assert construido["timeout"] == 90.0


@pytest.mark.parametrize("valor", ["", "abc", "0", "-5", "inf", "nan"])
def test_timeout_invalido_usa_el_de_omision(monkeypatch, valor):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AI_TIMEOUT_SEG", valor)
    assert cliente_estructurado_por_defecto().timeout == 300.0


def test_corte_por_max_tokens_es_respuesta_incompleta(monkeypatch):
    from app.modules.ai.cliente_anthropic import RespuestaIncompleta
    _sdk_falso(monkeypatch, mensaje=_mensaje(stop="max_tokens"))
    with pytest.raises(RespuestaIncompleta):
        ClienteAnthropic("k", "m").generar(sistema="s", contenido=[], esquema=ESQUEMA)
