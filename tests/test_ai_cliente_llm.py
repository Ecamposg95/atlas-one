"""Cliente del proveedor LLM (API compatible con OpenAI). La suite nunca sale
a la red: `httpx.MockTransport` hace de proveedor."""
import json

import httpx
import pytest
from fastapi import HTTPException

from app.modules.ai.cliente_llm import (
    BASE_URL_POR_DEFECTO, MODELO_POR_DEFECTO, NO_CONFIGURADO, ClienteFalso, ClienteOpenAICompatible,
    LlamadaHerramienta, ProveedorNoDisponible, RespuestaLLM, cliente_por_defecto, configuracion,
    limite_tokens_dia,
)

HERRAMIENTA = {"type": "function", "function": {
    "name": "listar_marcas", "description": "x", "parameters": {"type": "object", "properties": {}},
}}


def _respuesta(mensaje, uso=None):
    return {"choices": [{"message": mensaje}], "usage": uso or {"prompt_tokens": 120, "completion_tokens": 30}}


def _cliente(manejador, base="https://llm.prueba/v1beta/openai/"):
    return ClienteOpenAICompatible(base, "clave-secreta", "modelo-x", transport=httpx.MockTransport(manejador))


class TestPeticion:
    def test_manda_modelo_mensajes_herramientas_y_clave(self):
        vistas = []

        def manejador(req):
            vistas.append(req)
            return httpx.Response(200, json=_respuesta({"role": "assistant", "content": "hola"}))

        r = _cliente(manejador).completar([{"role": "user", "content": "hola"}], [HERRAMIENTA])
        req = vistas[0]
        assert str(req.url) == "https://llm.prueba/v1beta/openai/chat/completions"
        assert req.headers["authorization"] == "Bearer clave-secreta"
        cuerpo = json.loads(req.content)
        assert cuerpo["model"] == "modelo-x"
        assert cuerpo["messages"] == [{"role": "user", "content": "hola"}]
        assert cuerpo["tools"] == [HERRAMIENTA] and cuerpo["tool_choice"] == "auto"
        assert r.texto == "hola" and r.tool_calls == []
        assert (r.tokens_entrada, r.tokens_salida) == (120, 30)

    def test_sin_herramientas_no_manda_tools(self):
        vistos = []

        def manejador(req):
            vistos.append(json.loads(req.content))
            return httpx.Response(200, json=_respuesta({"role": "assistant", "content": "ok"}))

        _cliente(manejador, base="https://llm.prueba/v1").completar([{"role": "user", "content": "x"}], [])
        assert "tools" not in vistos[0] and "tool_choice" not in vistos[0]


class TestLecturaDeRespuesta:
    def test_tool_calls_con_argumentos_json(self):
        mensaje = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "buscar_producto", "arguments": '{"q": "versace"}'}},
        ]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).completar([], [HERRAMIENTA])
        assert r.texto is None
        ll = r.tool_calls[0]
        assert (ll.id, ll.nombre, ll.argumentos, ll.error_json) == ("call_1", "buscar_producto", {"q": "versace"}, None)
        assert ll.como_tool_call() == {"id": "call_1", "type": "function",
                                       "function": {"name": "buscar_producto", "arguments": '{"q": "versace"}'}}

    def test_argumentos_mal_formados_no_revientan(self):
        # Review Focus #2: el JSON roto no tumba el turno; queda marcado.
        mensaje = {"role": "assistant", "content": "", "tool_calls": [
            {"type": "function", "function": {"name": "listar_marcas", "arguments": '{"q": "ver'}},
        ]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).completar([], [HERRAMIENTA])
        ll = r.tool_calls[0]
        assert ll.id == "llamada_0"  # el proveedor no mandó id
        assert ll.argumentos == {}
        assert ll.error_json
        assert ll.argumentos_crudos == '{"q": "ver'

    def test_argumentos_que_no_son_objeto(self):
        ll = LlamadaHerramienta.desde_crudo("c1", "listar_marcas", "[1, 2]")
        assert ll.argumentos == {} and "objeto" in ll.error_json

    def test_argumentos_vacios_son_objeto_vacio(self):
        ll = LlamadaHerramienta.desde_crudo("c1", "listar_marcas", "")
        assert ll.argumentos == {} and ll.error_json is None

    def test_contenido_en_partes(self):
        mensaje = {"role": "assistant", "content": [{"type": "text", "text": "Hola "}, {"type": "text", "text": "Eleven"}]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).completar([], [])
        assert r.texto == "Hola Eleven"

    def test_cuerpo_sin_choices_es_proveedor_no_disponible(self):
        with pytest.raises(ProveedorNoDisponible, match="formato inesperado"):
            _cliente(lambda req: httpx.Response(200, json={"error": "x"})).completar([], [])


class TestErroresDelProveedor:
    def test_429_no_se_reintenta(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            return httpx.Response(429, json={"error": "rate"})

        with pytest.raises(ProveedorNoDisponible, match="límite de uso"):
            _cliente(manejador).completar([], [])
        assert len(llamadas) == 1

    def test_500_se_reintenta_una_vez(self):
        respuestas = [httpx.Response(500), httpx.Response(200, json=_respuesta({"role": "assistant", "content": "ya"}))]
        r = _cliente(lambda req: respuestas.pop(0)).completar([], [])
        assert r.texto == "ya" and respuestas == []

    def test_dos_5xx_seguidos_son_error(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            return httpx.Response(503)

        with pytest.raises(ProveedorNoDisponible, match="HTTP 503"):
            _cliente(manejador).completar([], [])
        assert len(llamadas) == 2

    def test_timeout_dos_veces_es_error(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            raise httpx.ReadTimeout("lento", request=req)

        with pytest.raises(ProveedorNoDisponible, match="tardó demasiado"):
            _cliente(manejador).completar([], [])
        assert len(llamadas) == 2

    def test_401_dice_que_revisen_la_clave(self):
        with pytest.raises(ProveedorNoDisponible, match="LLM_API_KEY"):
            _cliente(lambda req: httpx.Response(401, json={"error": "bad key"})).completar([], [])


class TestConfiguracion:
    def test_defaults(self, monkeypatch):
        for v in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        cfg = configuracion()
        assert cfg.base_url == BASE_URL_POR_DEFECTO == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert cfg.modelo == MODELO_POR_DEFECTO == "gemini-3.8-flash"
        assert cfg.api_key is None

    def test_sin_clave_es_503(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(HTTPException) as exc:
            cliente_por_defecto()
        assert exc.value.status_code == 503
        assert exc.value.detail == NO_CONFIGURADO == "Asistente no configurado: falta LLM_API_KEY en el servidor."

    def test_con_clave_arma_el_cliente(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("LLM_MODEL", "llama-x")
        c = cliente_por_defecto()
        assert c.url == "https://api.groq.com/openai/v1/chat/completions"
        assert c.modelo == "llama-x"

    def test_limite_tokens_dia(self, monkeypatch):
        monkeypatch.delenv("AI_TOKENS_DIA_ORG", raising=False)
        assert limite_tokens_dia() == 200000
        monkeypatch.setenv("AI_TOKENS_DIA_ORG", "5000")
        assert limite_tokens_dia() == 5000
        monkeypatch.setenv("AI_TOKENS_DIA_ORG", "mucho")
        assert limite_tokens_dia() == 200000


class TestClienteFalso:
    def test_devuelve_el_guion_y_anota(self):
        falso = ClienteFalso([RespuestaLLM(texto="uno"), RespuestaLLM(texto="dos")])
        assert falso.completar([{"role": "user", "content": "a"}], [HERRAMIENTA]).texto == "uno"
        assert falso.completar([], []).texto == "dos"
        assert falso.llamadas[0]["herramientas"] == [HERRAMIENTA]
        with pytest.raises(AssertionError):
            falso.completar([], [])
