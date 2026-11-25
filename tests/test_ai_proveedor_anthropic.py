"""Proveedor Anthropic: nunca toca la red (SDK sustituido por dobles)."""
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi import HTTPException

from app.modules.ai.proveedores import (
    ProveedorAnthropic, ProveedorFalso, ProveedorNoDisponible, Respuesta,
)
from app.modules.ai.tareas import CAPTURA, CONSULTA, proveedor_para


def cliente_estructurado_por_defecto():
    """El proveedor de `captura` sin organización: lo que usaba Cargar mercancía."""
    return proveedor_para(None, None, CAPTURA).opciones[0]

ESQUEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}


def test_falso_devuelve_guion_y_registra_llamadas():
    falso = ProveedorFalso([{"a": 1}])
    r = falso.generar_json(sistema="s", contenido=[{"type": "text", "text": "x"}], esquema=ESQUEMA)
    assert r.datos == {"a": 1}
    assert len(falso.llamadas) == 1
    assert falso.llamadas[0]["esquema"] is ESQUEMA


def test_falso_propaga_excepcion_del_guion():
    falso = ProveedorFalso([ProveedorNoDisponible("x")])
    with pytest.raises(ProveedorNoDisponible):
        falso.generar_json(sistema="s", contenido=[], esquema=ESQUEMA)


@pytest.fixture(autouse=True)
def _sin_listas_de_modelos(monkeypatch):
    for v in ("AI_MODELOS_CONSULTA", "AI_MODELOS_CAPTURA", "AI_MODELOS_ANALISIS"):
        monkeypatch.delenv(v, raising=False)


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


def _sdk_falso(monkeypatch, mensaje=None, error=None, capturar=None, constructor=None, eventos=()):
    class Flujo:
        def __init__(self, kw):
            self.kw = kw

        def __enter__(self):
            if error:
                raise error
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            return iter(eventos)

        def get_final_message(self):
            return mensaje

    class Falso:
        def __init__(self, api_key=None, **kw):
            if constructor is not None:
                constructor.update(kw, api_key=api_key)
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream_beta))
            self.messages = SimpleNamespace(stream=self._stream)

        def _stream_beta(self, **kw):
            return self._stream(_beta=True, **kw)

        def _stream(self, **kw):
            if capturar is not None:
                capturar.clear()
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
    r = ProveedorAnthropic("k", "claude-opus-5-5").generar_json(
        sistema="s", contenido=[{"type": "text", "text": "x"}], esquema=ESQUEMA)
    assert (r.datos, r.tokens_entrada, r.tokens_salida) == ({"a": 2}, 11, 7)
    assert (r.proveedor, r.modelo) == ("anthropic", "claude-opus-5-5")
    assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default"
    assert kw["_beta"] is True and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["output_config"] == {"format": {"type": "json_schema", "schema": ESQUEMA}}
    assert "thinking" not in kw


def test_refusal_se_vuelve_proveedor_no_disponible(monkeypatch):
    _sdk_falso(monkeypatch, mensaje=_mensaje(stop="refusal"))
    with pytest.raises(ProveedorNoDisponible):
        ProveedorAnthropic("k", "m").generar_json(sistema="s", contenido=[], esquema=ESQUEMA)


def test_json_invalido_se_vuelve_proveedor_no_disponible(monkeypatch):
    _sdk_falso(monkeypatch, mensaje=_mensaje(texto="no es json"))
    with pytest.raises(ProveedorNoDisponible):
        ProveedorAnthropic("k", "m").generar_json(sistema="s", contenido=[], esquema=ESQUEMA)


@pytest.mark.parametrize("hacer", [
    lambda req: anthropic.APIConnectionError(request=req),
    lambda req: anthropic.RateLimitError("x", response=httpx.Response(429, request=req), body=None),
])
def test_error_de_api_se_vuelve_proveedor_no_disponible(monkeypatch, hacer):
    req = httpx.Request("POST", "https://invalido.local")
    _sdk_falso(monkeypatch, error=hacer(req))
    with pytest.raises(ProveedorNoDisponible):
        ProveedorAnthropic("k", "m").generar_json(sistema="s", contenido=[], esquema=ESQUEMA)


def test_timeout_y_reintentos_explicitos(monkeypatch):
    """Tope de tiempo de la lectura (spec §7): 300 s y un solo reintento por omisión."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("AI_TIMEOUT_SEG", raising=False)
    construido = {}
    _sdk_falso(monkeypatch, mensaje=_mensaje(), constructor=construido)
    cliente_estructurado_por_defecto().generar_json(sistema="s", contenido=[], esquema=ESQUEMA)
    assert construido["timeout"] == 300.0 and construido["max_retries"] == 1

    monkeypatch.setenv("AI_TIMEOUT_SEG", "90")
    cliente_estructurado_por_defecto().generar_json(sistema="s", contenido=[], esquema=ESQUEMA)
    assert construido["timeout"] == 90.0


@pytest.mark.parametrize("valor", ["", "abc", "0", "-5", "inf", "nan"])
def test_timeout_invalido_usa_el_de_omision(monkeypatch, valor):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AI_TIMEOUT_SEG", valor)
    assert cliente_estructurado_por_defecto().timeout == 300.0


def test_corte_por_max_tokens_es_respuesta_incompleta(monkeypatch):
    from app.modules.ai.proveedores import RespuestaIncompleta
    _sdk_falso(monkeypatch, mensaje=_mensaje(stop="max_tokens"))
    with pytest.raises(RespuestaIncompleta):
        ProveedorAnthropic("k", "m").generar_json(sistema="s", contenido=[], esquema=ESQUEMA)


def test_latido_durante_el_streaming_espaciado(monkeypatch):
    """Un solo bloque largo no debe dejar la carga sin latir 10 min: el cliente
    late mientras llegan eventos, como mucho uno por intervalo."""
    import app.modules.ai.proveedores.anthropic_nativo as mod
    reloj = iter([0, 10, 70, 80, 140, 200])
    monkeypatch.setattr(mod, "_ahora", lambda: next(reloj))
    _sdk_falso(monkeypatch, mensaje=_mensaje(), eventos=["e"] * 5)
    latidos = []
    r = ProveedorAnthropic("k", "m").generar_json(sistema="s", contenido=[], esquema=ESQUEMA,
                                            latido=lambda: latidos.append(1))
    assert r.datos == {"a": 2}
    # inicio t=0; eventos en 10 (no), 70 (sí), 80 (no), 140 (sí), 200 (sí)
    assert len(latidos) == 3


def test_latido_que_falla_no_corta_la_lectura(monkeypatch):
    import app.modules.ai.proveedores.anthropic_nativo as mod
    reloj = iter([0, 100])
    monkeypatch.setattr(mod, "_ahora", lambda: next(reloj))
    _sdk_falso(monkeypatch, mensaje=_mensaje(), eventos=["e"])

    def roto():
        raise RuntimeError("base caída")
    assert ProveedorAnthropic("k", "m").generar_json(sistema="s", contenido=[], esquema=ESQUEMA,
                                              latido=roto).datos == {"a": 2}


def test_falso_acepta_y_registra_latido():
    def latido():
        pass
    falso = ProveedorFalso([{"a": 1}])
    falso.generar_json(sistema="s", contenido=[], esquema=ESQUEMA, latido=latido)
    assert falso.llamadas[0]["latido"] is latido


# ── fase A0: interfaz única ──────────────────────────────────────────────

def test_haiku_no_pide_respaldo_del_servidor(monkeypatch):
    """Haiku no tiene respaldo del lado del servidor: va por el endpoint normal, sin betas."""
    kw = {}
    _sdk_falso(monkeypatch, mensaje=_mensaje(), capturar=kw)
    ProveedorAnthropic("k", "claude-haiku-5-5").generar_json(sistema="s", contenido=[], esquema=ESQUEMA)
    assert "_beta" not in kw and "betas" not in kw and "fallbacks" not in kw


def test_modelos_por_omision_de_cada_tarea(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("AI_MODELO", raising=False)
    assert proveedor_para(None, None, CONSULTA).modelo == "claude-haiku-5-5"
    assert proveedor_para(None, None, CAPTURA).modelo == "claude-opus-5-5"
    assert proveedor_para(None, None, "analisis").modelo == "claude-opus-5-5"


@pytest.mark.parametrize("hacer, recuperable", [
    (lambda req: anthropic.APIConnectionError(request=req), True),
    (lambda req: anthropic.RateLimitError("x", response=httpx.Response(429, request=req), body=None), True),
    (lambda req: anthropic.InternalServerError("x", response=httpx.Response(500, request=req), body=None), True),
    (lambda req: anthropic.BadRequestError("x", response=httpx.Response(400, request=req), body=None), False),
])
def test_que_errores_dejan_probar_otro_modelo(monkeypatch, hacer, recuperable):
    req = httpx.Request("POST", "https://invalido.local")
    _sdk_falso(monkeypatch, error=hacer(req))
    with pytest.raises(ProveedorNoDisponible) as e:
        ProveedorAnthropic("k", "m").generar_json(sistema="s", contenido=[], esquema=ESQUEMA)
    assert e.value.recuperable is recuperable


HERRAMIENTA = {"type": "function", "function": {
    "name": "buscar_producto", "description": "Busca",
    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
}}


def _bloque(**campos):
    return SimpleNamespace(to_dict=lambda: dict(campos), **campos)


def test_conversar_traduce_historial_y_herramientas(monkeypatch):
    kw = {}
    mensaje = SimpleNamespace(
        stop_reason="tool_use", model="claude-haiku-5-5",
        content=[
            _bloque(type="thinking", thinking="", signature="firma"),
            _bloque(type="text", text="Busco."),
            _bloque(type="tool_use", id="tu_1", name="buscar_producto", input={"q": "versace"}),
        ],
        usage=SimpleNamespace(input_tokens=40, output_tokens=9),
    )
    _sdk_falso(monkeypatch, mensaje=mensaje, capturar=kw)
    historial = [
        {"role": "system", "content": "Eres el asistente."},
        {"role": "user", "content": "¿hay versace?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "listar_marcas", "arguments": "{}"}},
            {"id": "b", "type": "function", "function": {"name": "buscar_producto", "arguments": '{"q": "x"}'}},
        ]},
        {"role": "tool", "tool_call_id": "a", "content": '{"marcas": []}'},
        {"role": "tool", "tool_call_id": "b", "content": '{"productos": []}'},
    ]
    r = ProveedorAnthropic("k", "claude-haiku-5-5").conversar(mensajes=historial, herramientas=[HERRAMIENTA])

    assert kw["system"] == "Eres el asistente."
    assert kw["tools"] == [{"name": "buscar_producto", "description": "Busca",
                            "input_schema": HERRAMIENTA["function"]["parameters"]}]
    assert kw["messages"] == [
        {"role": "user", "content": "¿hay versace?"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "a", "name": "listar_marcas", "input": {}},
            {"type": "tool_use", "id": "b", "name": "buscar_producto", "input": {"q": "x"}},
        ]},
        # Los dos resultados van en UN solo mensaje de usuario.
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "a", "content": '{"marcas": []}'},
            {"type": "tool_result", "tool_use_id": "b", "content": '{"productos": []}'},
        ]},
    ]
    assert isinstance(r, Respuesta) and r.texto == "Busco."
    assert (r.tokens_entrada, r.tokens_salida, r.proveedor, r.modelo) == (40, 9, "anthropic", "claude-haiku-5-5")
    ll = r.tool_calls[0]
    assert (ll.id, ll.nombre, ll.argumentos) == ("tu_1", "buscar_producto", {"q": "versace"})
    # El contenido nativo (con el bloque de razonamiento) viaja de vuelta intacto.
    siguiente = r.mensaje_asistente()
    assert siguiente["tool_calls"][0]["function"]["name"] == "buscar_producto"
    kw2 = {}
    _sdk_falso(monkeypatch, mensaje=_mensaje(texto="hecho"), capturar=kw2)
    ProveedorAnthropic("k", "claude-haiku-5-5").conversar(
        mensajes=[{"role": "user", "content": "x"}, siguiente,
                  {"role": "tool", "tool_call_id": "tu_1", "content": "{}"}])
    assert kw2["messages"][1] == {"role": "assistant", "content": r.nativo["contenido"]}
    assert kw2["messages"][1]["content"][0]["type"] == "thinking"
    assert "tools" not in kw2 and "system" not in kw2
