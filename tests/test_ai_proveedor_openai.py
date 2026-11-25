"""Cliente del proveedor LLM (API compatible con OpenAI). La suite nunca sale
a la red: `httpx.MockTransport` hace de proveedor."""
import json

import httpx
import pytest
from fastapi import HTTPException

from app.modules.ai.proveedores import (
    LlamadaHerramienta, ProveedorFalso, ProveedorNoDisponible, ProveedorOpenAI, Respuesta,
    RespuestaIncompleta,
)
from app.modules.ai.tareas import (
    BASE_URL_COMPATIBLE, MODELO_COMPATIBLE, Opcion, construir, proveedor_para, reiniciar_proveedores,
)


def cliente_por_defecto():
    """El proveedor `compatible` con su modelo por omisión (`LLM_*`)."""
    return construir(Opcion("compatible", ""))

HERRAMIENTA = {"type": "function", "function": {
    "name": "listar_marcas", "description": "x", "parameters": {"type": "object", "properties": {}},
}}


def _respuesta(mensaje, uso=None):
    return {"choices": [{"message": mensaje}], "usage": uso or {"prompt_tokens": 120, "completion_tokens": 30}}


def _cliente(manejador, base="https://llm.prueba/v1beta/openai/"):
    return ProveedorOpenAI(base, "clave-secreta", "modelo-x", transport=httpx.MockTransport(manejador))


class TestPeticion:
    def test_manda_modelo_mensajes_herramientas_y_clave(self):
        vistas = []

        def manejador(req):
            vistas.append(req)
            return httpx.Response(200, json=_respuesta({"role": "assistant", "content": "hola"}))

        r = _cliente(manejador).conversar(mensajes=[{"role": "user", "content": "hola"}], herramientas=[HERRAMIENTA])
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

        _cliente(manejador, base="https://llm.prueba/v1").conversar(mensajes=[{"role": "user", "content": "x"}], herramientas=[])
        assert "tools" not in vistos[0] and "tool_choice" not in vistos[0]


class TestLecturaDeRespuesta:
    def test_tool_calls_con_argumentos_json(self):
        mensaje = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "buscar_producto", "arguments": '{"q": "versace"}'}},
        ]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).conversar(mensajes=[], herramientas=[HERRAMIENTA])
        assert r.texto is None
        ll = r.tool_calls[0]
        assert (ll.id, ll.nombre, ll.argumentos, ll.error_json) == ("call_1", "buscar_producto", {"q": "versace"}, None)
        assert ll.como_tool_call() == {"id": "call_1", "type": "function",
                                       "function": {"name": "buscar_producto", "arguments": '{"q": "versace"}'}}

    def test_argumentos_mal_formados_no_revientan(self):
        # El JSON roto no tumba el turno; queda marcado.
        mensaje = {"role": "assistant", "content": "", "tool_calls": [
            {"type": "function", "function": {"name": "listar_marcas", "arguments": '{"q": "ver'}},
        ]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).conversar(mensajes=[], herramientas=[HERRAMIENTA])
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
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).conversar(mensajes=[], herramientas=[])
        assert r.texto == "Hola Eleven"

    def test_cuerpo_sin_choices_es_proveedor_no_disponible(self):
        with pytest.raises(ProveedorNoDisponible, match="formato inesperado"):
            _cliente(lambda req: httpx.Response(200, json={"error": "x"})).conversar(mensajes=[], herramientas=[])


class TestErroresDelProveedor:
    def test_429_no_se_reintenta(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            return httpx.Response(429, json={"error": "rate"})

        with pytest.raises(ProveedorNoDisponible, match="límite de uso"):
            _cliente(manejador).conversar(mensajes=[], herramientas=[])
        assert len(llamadas) == 1

    def test_500_se_reintenta_una_vez(self):
        respuestas = [httpx.Response(500), httpx.Response(200, json=_respuesta({"role": "assistant", "content": "ya"}))]
        r = _cliente(lambda req: respuestas.pop(0)).conversar(mensajes=[], herramientas=[])
        assert r.texto == "ya" and respuestas == []

    def test_dos_5xx_seguidos_son_error(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            return httpx.Response(503)

        with pytest.raises(ProveedorNoDisponible, match="HTTP 503"):
            _cliente(manejador).conversar(mensajes=[], herramientas=[])
        assert len(llamadas) == 2

    def test_timeout_dos_veces_es_error(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            raise httpx.ReadTimeout("lento", request=req)

        with pytest.raises(ProveedorNoDisponible, match="tardó demasiado"):
            _cliente(manejador).conversar(mensajes=[], herramientas=[])
        assert len(llamadas) == 2

    def test_401_dice_que_revisen_la_clave(self):
        with pytest.raises(ProveedorNoDisponible, match="Revisa la llave"):
            _cliente(lambda req: httpx.Response(401, json={"error": "bad key"})).conversar(mensajes=[], herramientas=[])


class TestConfiguracion:
    def test_sin_clave_no_hay_proveedor_y_la_tarea_da_503(self, monkeypatch):
        for v in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        assert cliente_por_defecto() is None
        monkeypatch.setenv("AI_MODELOS_CONSULTA", "compatible")
        with pytest.raises(HTTPException) as exc:
            proveedor_para(None, None, "consulta")
        assert exc.value.status_code == 503
        assert exc.value.detail == "IA no configurada: falta LLM_API_KEY en el servidor."

    def test_defaults_apuntan_a_gemini(self, monkeypatch):
        for v in ("LLM_BASE_URL", "LLM_MODEL"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setenv("LLM_API_KEY", "k")
        reiniciar_proveedores()
        try:
            c = cliente_por_defecto()
            assert BASE_URL_COMPATIBLE == "https://generativelanguage.googleapis.com/v1beta/openai/"
            assert c.url == BASE_URL_COMPATIBLE + "chat/completions"
            assert c.modelo == MODELO_COMPATIBLE == "gemini-3.8-flash"
        finally:
            reiniciar_proveedores()

    def test_con_clave_arma_el_cliente(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("LLM_MODEL", "llama-x")
        reiniciar_proveedores()
        try:
            c = cliente_por_defecto()
            assert c.url == "https://api.groq.com/openai/v1/chat/completions"
            assert c.modelo == "llama-x" and c.nombre == "compatible"
        finally:
            reiniciar_proveedores()

    def test_proveedor_con_nombre_propio(self, monkeypatch):
        """Varios compatibles a la vez: cada nombre trae sus dos variables."""
        monkeypatch.setenv("AI_PROVEEDOR_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("AI_PROVEEDOR_GROQ_API_KEY", "g")
        reiniciar_proveedores()
        try:
            c = construir(Opcion("groq", "llama-x"))
            assert (c.nombre, c.modelo) == ("groq", "llama-x")
            assert construir(Opcion("groq", "")) is None       # sin modelo no hay cliente
            assert construir(Opcion("mistral", "m")) is None   # sin variables no hay cliente
        finally:
            reiniciar_proveedores()


class TestProveedorFalso:
    def test_devuelve_el_guion_y_anota(self):
        falso = ProveedorFalso([Respuesta(texto="uno"), Respuesta(texto="dos")])
        assert falso.conversar(mensajes=[{"role": "user", "content": "a"}], herramientas=[HERRAMIENTA]).texto == "uno"
        assert falso.conversar(mensajes=[], herramientas=[]).texto == "dos"
        assert falso.llamadas[0]["herramientas"] == [HERRAMIENTA]
        with pytest.raises(AssertionError):
            falso.conversar(mensajes=[], herramientas=[])


class TestFormatoInesperado:
    def test_message_nulo(self):
        with pytest.raises(ProveedorNoDisponible, match="formato inesperado"):
            _cliente(lambda req: httpx.Response(200, json={"choices": [{"message": None}]})).conversar(mensajes=[], herramientas=[])

    def test_usage_no_numerico(self):
        cuerpo = _respuesta({"role": "assistant", "content": "x"}, uso={"prompt_tokens": "mucho"})
        with pytest.raises(ProveedorNoDisponible, match="formato inesperado"):
            _cliente(lambda req: httpx.Response(200, json=cuerpo)).conversar(mensajes=[], herramientas=[])


class TestCicloDeVida:
    def test_cliente_por_defecto_se_reutiliza(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        monkeypatch.setenv("LLM_MODEL", "m1")
        reiniciar_proveedores()
        try:
            a = cliente_por_defecto()
            assert cliente_por_defecto() is a
            monkeypatch.setenv("LLM_MODEL", "m2")
            b = cliente_por_defecto()
            assert b is not a and b.modelo == "m2"
            # Los dos siguen abiertos: una lista puede usar varios modelos a la vez.
            assert not a._http.is_closed
            reiniciar_proveedores()
            assert a._http.is_closed and b._http.is_closed
        finally:
            reiniciar_proveedores()

    def test_cerrar_y_contexto(self):
        c = _cliente(lambda req: httpx.Response(200))
        c.cerrar()
        assert c._http.is_closed
        with _cliente(lambda req: httpx.Response(200)) as c2:
            assert not c2._http.is_closed
        assert c2._http.is_closed

    def test_hilos_simultaneos_comparten_un_cliente_abierto(self, monkeypatch):
        from concurrent.futures import ThreadPoolExecutor
        monkeypatch.setenv("LLM_API_KEY", "k")
        reiniciar_proveedores()
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                clientes = list(pool.map(lambda _: cliente_por_defecto(), range(8)))
            assert all(c is clientes[0] for c in clientes)
            assert not clientes[0]._http.is_closed
        finally:
            reiniciar_proveedores()


class TestSalidaJSON:
    ESQUEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}

    def test_manda_esquema_y_documento_y_lee_el_objeto(self):
        vistos = []

        def manejador(req):
            vistos.append(json.loads(req.content))
            return httpx.Response(200, json=_respuesta({"role": "assistant", "content": '{"a": 3}'}))

        latidos = []
        r = _cliente(manejador).generar_json(
            sistema="Extrae.", esquema=self.ESQUEMA, latido=lambda: latidos.append(1),
            contenido=[{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "QUJD"}},
                       {"type": "text", "text": "páginas 1-2"}])
        cuerpo = vistos[0]
        assert cuerpo["response_format"] == {"type": "json_schema",
                                             "json_schema": {"name": "salida", "schema": self.ESQUEMA}}
        assert cuerpo["messages"][0] == {"role": "system", "content": "Extrae."}
        partes = cuerpo["messages"][1]["content"]
        assert partes[0]["type"] == "file" and partes[0]["file"]["file_data"] == "data:application/pdf;base64,QUJD"
        assert partes[1] == {"type": "text", "text": "páginas 1-2"}
        assert (r.datos, r.tokens_entrada, r.tokens_salida) == ({"a": 3}, 120, 30)
        assert (r.proveedor, r.modelo) == ("compatible", "modelo-x")
        assert latidos == [1]

    def test_json_invalido_o_que_no_es_objeto(self):
        for contenido in ("no es json", "[1, 2]"):
            with pytest.raises(ProveedorNoDisponible, match="formato inesperado"):
                _cliente(lambda req, c=contenido: httpx.Response(
                    200, json=_respuesta({"role": "assistant", "content": c}))
                ).generar_json(sistema="s", contenido=[], esquema=self.ESQUEMA)

    def test_cortada_por_longitud_es_respuesta_incompleta(self):
        cuerpo = {"choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": '{"a"'}}],
                  "usage": {}}
        with pytest.raises(RespuestaIncompleta):
            _cliente(lambda req: httpx.Response(200, json=cuerpo)).generar_json(
                sistema="s", contenido=[], esquema=self.ESQUEMA)


class TestRecuperable:
    """Qué fallas dejan que el respaldo pruebe el siguiente modelo."""

    @pytest.mark.parametrize("codigo, recuperable", [(429, True), (503, True), (401, False), (400, False)])
    def test_por_codigo(self, codigo, recuperable):
        with pytest.raises(ProveedorNoDisponible) as e:
            _cliente(lambda req: httpx.Response(codigo, json={})).conversar(mensajes=[], herramientas=[])
        assert e.value.recuperable is recuperable

    def test_no_manda_el_contenido_nativo_de_otro_proveedor(self):
        vistos = []

        def manejador(req):
            vistos.append(json.loads(req.content))
            return httpx.Response(200, json=_respuesta({"role": "assistant", "content": "ok"}))

        _cliente(manejador).conversar(mensajes=[
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "y", "nativo": {"proveedor": "anthropic", "contenido": [{"type": "thinking"}]}},
        ])
        assert vistos[0]["messages"][1] == {"role": "assistant", "content": "y"}
