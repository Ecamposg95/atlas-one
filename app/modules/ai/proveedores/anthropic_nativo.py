"""Proveedor Anthropic sobre su SDK oficial (Messages API, con streaming).

Clave en `ANTHROPIC_API_KEY`; el modelo lo decide la tarea (`app/modules/ai/tareas.py`).
En los modelos que lo admiten se pide el respaldo del lado del servidor ante un
rechazo de política (beta `server-side-fallback-2026-07-01`, `fallbacks="default"`).

La suite NUNCA llama al proveedor: sustituye `anthropic.Anthropic` o usa `ProveedorFalso`.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Callable, Optional

from .base import (
    MAX_TOKENS_CONVERSAR, MAX_TOKENS_JSON, LlamadaHerramienta, ProveedorNoDisponible,
    Respuesta, RespuestaIncompleta, RespuestaJSON,
)

logger = logging.getLogger(__name__)

NOMBRE = "anthropic"
BETA_FALLBACK = "server-side-fallback-2026-07-01"
# Familias con respaldo del servidor ante rechazos. Haiku no lo tiene.
_CON_FALLBACK = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")
# Tope por llamada (spec de cargas §7): sin él el SDK espera 10 min y reintenta 2 veces.
TIMEOUT_POR_DEFECTO = 300.0
REINTENTOS = 1
# Cada cuánto, como mucho, se late mientras llegan eventos del streaming. Muy por
# debajo de MINUTOS_COLGADA (10) de cargas: un bloque largo de PDF sigue vivo.
SEGUNDOS_ENTRE_LATIDOS = 60.0

_SIN_RED = "No se pudo contactar al proveedor de IA. Intenta de nuevo."
_FORMATO = "Respuesta del proveedor con formato inesperado."


def _ahora() -> float:
    return time.monotonic()


def timeout_configurado() -> float:
    """`AI_TIMEOUT_SEG` (segundos por llamada); vacío o inválido → 300."""
    try:
        valor = float((os.getenv("AI_TIMEOUT_SEG") or "").strip())
    except ValueError:
        return TIMEOUT_POR_DEFECTO
    return valor if math.isfinite(valor) and valor > 0 else TIMEOUT_POR_DEFECTO


def _herramienta(h: dict) -> dict:
    f = h.get("function") or {}
    return {"name": f.get("name") or "", "description": f.get("description") or "",
            "input_schema": f.get("parameters") or {"type": "object", "properties": {}}}


def _a_mensajes(mensajes: list[dict]) -> tuple[str, list[dict]]:
    """Historial canónico → (`system`, `messages`) de la Messages API.

    Los `system` van juntos arriba; los resultados de herramientas consecutivos
    se funden en UN mensaje de usuario (partirlos enseña al modelo a no pedir
    herramientas en paralelo)."""
    sistema: list[str] = []
    salida: list[dict] = []
    for m in mensajes:
        rol = m.get("role")
        contenido = m.get("content")
        if rol == "system":
            if contenido:
                sistema.append(str(contenido))
        elif rol == "tool":
            bloque = {"type": "tool_result", "tool_use_id": m.get("tool_call_id") or "",
                      "content": contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False)}
            previo = salida[-1] if salida else None
            if (previo and previo["role"] == "user" and isinstance(previo["content"], list)
                    and all(b.get("type") == "tool_result" for b in previo["content"])):
                previo["content"].append(bloque)
            else:
                salida.append({"role": "user", "content": [bloque]})
        elif rol == "assistant":
            nativo = m.get("nativo")
            if isinstance(nativo, dict) and nativo.get("proveedor") == NOMBRE and nativo.get("contenido"):
                # Tal cual: los bloques de razonamiento no se pueden quitar ni editar.
                salida.append({"role": "assistant", "content": nativo["contenido"]})
                continue
            bloques: list[dict] = []
            if contenido:
                bloques.append({"type": "text", "text": str(contenido)})
            for tc in m.get("tool_calls") or []:
                f = tc.get("function") or {}
                ll = LlamadaHerramienta.desde_crudo(tc.get("id") or "", f.get("name") or "", f.get("arguments"))
                bloques.append({"type": "tool_use", "id": ll.id, "name": ll.nombre, "input": ll.argumentos})
            if bloques:
                salida.append({"role": "assistant", "content": bloques})
        else:
            salida.append({"role": "user", "content": contenido if contenido is not None else ""})
    return "\n\n".join(sistema), salida


def _bloque_a_dict(b: Any) -> dict:
    if isinstance(b, dict):
        return b
    volcar = getattr(b, "to_dict", None) or getattr(b, "model_dump", None)
    return volcar() if callable(volcar) else dict(getattr(b, "__dict__", {}))


class ProveedorAnthropic:
    nombre = NOMBRE

    def __init__(self, api_key: str, modelo: str, timeout: float = TIMEOUT_POR_DEFECTO):
        self.api_key = api_key
        self.modelo = modelo
        self.timeout = timeout

    # ── llamada común ────────────────────────────────────────────────────

    def _pedir(self, parametros: dict, latido: Optional[Callable[[], None]] = None) -> Any:
        import anthropic

        try:
            client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout,
                                         max_retries=REINTENTOS)
            if self.modelo.startswith(_CON_FALLBACK):
                abrir = client.beta.messages.stream(
                    model=self.modelo, betas=[BETA_FALLBACK], fallbacks="default", **parametros)
            else:
                abrir = client.messages.stream(model=self.modelo, **parametros)
            with abrir as flujo:
                if latido is not None:
                    ultimo = _ahora()
                    for _evento in flujo:
                        t = _ahora()
                        if t - ultimo >= SEGUNDOS_ENTRE_LATIDOS:
                            ultimo = t
                            try:
                                latido()
                            except Exception:  # noqa: BLE001 - el latido nunca corta la lectura
                                logger.warning("Falló el latido durante el streaming", exc_info=True)
                mensaje = flujo.get_final_message()
        except anthropic.RateLimitError as e:
            logger.warning("Anthropic sin cuota: %s", e)
            raise ProveedorNoDisponible(
                "El proveedor de IA alcanzó su límite de uso. Intenta en unos minutos.",
                recuperable=True) from e
        except anthropic.APIStatusError as e:
            logger.warning("Error de la API de Anthropic: %s", e)
            raise ProveedorNoDisponible(_SIN_RED, recuperable=e.status_code >= 500) from e
        except anthropic.APIConnectionError as e:  # incluye el timeout
            logger.warning("Anthropic sin red: %s", e)
            raise ProveedorNoDisponible(_SIN_RED, recuperable=True) from e
        except anthropic.APIError as e:
            logger.warning("Error de la API de Anthropic: %s", e)
            raise ProveedorNoDisponible(_SIN_RED) from e

        parada = getattr(mensaje, "stop_reason", None)
        if parada == "refusal":
            raise ProveedorNoDisponible("El modelo rechazó procesar esta petición.")
        if parada == "max_tokens":
            raise RespuestaIncompleta("La respuesta del modelo quedó incompleta (demasiado larga).")
        return mensaje

    @staticmethod
    def _tokens(mensaje: Any) -> tuple[int, int]:
        uso = getattr(mensaje, "usage", None)
        return (int(getattr(uso, "input_tokens", 0) or 0), int(getattr(uso, "output_tokens", 0) or 0))

    # ── interfaz ─────────────────────────────────────────────────────────

    def conversar(self, *, mensajes: list[dict], herramientas: Optional[list[dict]] = None,
                  max_tokens: int = MAX_TOKENS_CONVERSAR) -> Respuesta:
        sistema, historial = _a_mensajes(mensajes)
        parametros: dict[str, Any] = {"max_tokens": max_tokens, "messages": historial}
        if sistema:
            parametros["system"] = sistema
        if herramientas:
            parametros["tools"] = [_herramienta(h) for h in herramientas]
        mensaje = self._pedir(parametros)

        textos: list[str] = []
        llamadas: list[LlamadaHerramienta] = []
        for b in mensaje.content or []:
            tipo = getattr(b, "type", None)
            if tipo == "text":
                textos.append(b.text)
            elif tipo == "tool_use":
                llamadas.append(LlamadaHerramienta.desde_crudo(b.id, b.name, getattr(b, "input", None) or {}))
        entrada, salida = self._tokens(mensaje)
        modelo = getattr(mensaje, "model", None) or self.modelo
        return Respuesta(
            texto="".join(textos) or None, tool_calls=llamadas,
            tokens_entrada=entrada, tokens_salida=salida, proveedor=NOMBRE, modelo=modelo,
            nativo={"proveedor": NOMBRE, "modelo": modelo,
                    "contenido": [_bloque_a_dict(b) for b in (mensaje.content or [])]},
        )

    def generar_json(self, *, sistema: str, contenido: list[dict], esquema: dict,
                     max_tokens: int = MAX_TOKENS_JSON,
                     latido: Optional[Callable[[], None]] = None) -> RespuestaJSON:
        """`latido`, si viene, se llama mientras llegan eventos del streaming (como
        mucho uno cada SEGUNDOS_ENTRE_LATIDOS): una respuesta larga no deja a la
        carga sin señal de vida. Un latido que falla no corta la lectura."""
        mensaje = self._pedir({
            "max_tokens": max_tokens,
            "system": sistema,
            "messages": [{"role": "user", "content": contenido}],
            "output_config": {"format": {"type": "json_schema", "schema": esquema}},
        }, latido)

        texto = next((b.text for b in (mensaje.content or []) if getattr(b, "type", None) == "text"), None)
        if texto is None:
            raise ProveedorNoDisponible("Respuesta del proveedor sin contenido de texto.")
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ProveedorNoDisponible(_FORMATO) from e
        if not isinstance(datos, dict):
            raise ProveedorNoDisponible(_FORMATO)
        entrada, salida = self._tokens(mensaje)
        return RespuestaJSON(datos=datos, tokens_entrada=entrada, tokens_salida=salida,
                             proveedor=NOMBRE, modelo=getattr(mensaje, "model", None) or self.modelo)
