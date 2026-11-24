"""Proveedor para cualquier API compatible con OpenAI
(`POST {base}/chat/completions` con `tools` y `response_format`).

Sirve para Gemini en su capa compatible (ojo: en el nivel gratuito Google usa
el contenido para mejorar sus productos), Groq, Mistral, OpenAI… Sin SDK:
httpx, que ya está en requirements.

La suite NUNCA llama al proveedor: usa `ProveedorFalso` o `httpx.MockTransport`.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

import httpx

from .base import (
    MAX_TOKENS_CONVERSAR, MAX_TOKENS_JSON, LlamadaHerramienta, ProveedorNoDisponible,
    Respuesta, RespuestaIncompleta, RespuestaJSON,
)

logger = logging.getLogger(__name__)

NOMBRE = "compatible"
TIMEOUT_SEGUNDOS = 45.0

_FORMATO = "Respuesta del proveedor con formato inesperado."
_TARDO = "El proveedor del asistente tardó demasiado en responder. Intenta de nuevo."
_SIN_RED = "No se pudo contactar al proveedor del asistente. Intenta de nuevo."


def _mensaje(cuerpo: Any) -> dict:
    try:
        opcion = cuerpo["choices"][0]
        mensaje = opcion["message"]
    except (KeyError, IndexError, TypeError):
        raise ProveedorNoDisponible(_FORMATO)
    if not isinstance(mensaje, dict):
        raise ProveedorNoDisponible(_FORMATO)
    return mensaje


def _texto(mensaje: dict) -> Optional[str]:
    contenido = mensaje.get("content")
    if isinstance(contenido, list):  # algunos proveedores mandan partes
        contenido = "".join(p.get("text", "") for p in contenido if isinstance(p, dict))
    return contenido if isinstance(contenido, str) else None


def _tokens(cuerpo: Any) -> tuple[int, int]:
    uso = cuerpo.get("usage") or {}
    try:
        return int(uso.get("prompt_tokens") or 0), int(uso.get("completion_tokens") or 0)
    except (ValueError, TypeError, AttributeError):
        raise ProveedorNoDisponible(_FORMATO)


def _parte(bloque: dict) -> dict:
    """Bloque canónico de `generar_json` → parte de contenido de OpenAI."""
    if bloque.get("type") == "document":
        fuente = bloque.get("source") or {}
        tipo = fuente.get("media_type") or "application/pdf"
        return {"type": "file", "file": {
            "filename": "documento.pdf",
            "file_data": f"data:{tipo};base64,{fuente.get('data') or ''}",
        }}
    return {"type": "text", "text": bloque.get("text") or ""}


class ProveedorOpenAI:
    def __init__(self, base_url: str, api_key: str, modelo: str, timeout: float = TIMEOUT_SEGUNDOS,
                 transport: Optional[httpx.BaseTransport] = None, nombre: str = NOMBRE):
        self.nombre = nombre
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.modelo = modelo
        self._http = httpx.Client(
            timeout=timeout, transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    def cerrar(self) -> None:
        self._http.close()

    def __enter__(self) -> "ProveedorOpenAI":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cerrar()

    def conversar(self, *, mensajes: list[dict], herramientas: Optional[list[dict]] = None,
                  max_tokens: int = MAX_TOKENS_CONVERSAR) -> Respuesta:
        # `nativo` es de otro proveedor (bloques de Anthropic): aquí no viaja.
        limpios = [{k: v for k, v in m.items() if k != "nativo"} for m in mensajes]
        cuerpo: dict[str, Any] = {"model": self.modelo, "messages": limpios}
        if herramientas:
            cuerpo["tools"] = herramientas
            cuerpo["tool_choice"] = "auto"
        respuesta = self._enviar(cuerpo)
        mensaje = _mensaje(respuesta)
        llamadas = []
        for i, tc in enumerate(mensaje.get("tool_calls") or []):
            funcion = (tc or {}).get("function") or {}
            llamadas.append(LlamadaHerramienta.desde_crudo(
                (tc or {}).get("id") or f"llamada_{i}", funcion.get("name") or "", funcion.get("arguments"),
            ))
        entrada, salida = _tokens(respuesta)
        return Respuesta(texto=_texto(mensaje), tool_calls=llamadas, tokens_entrada=entrada,
                         tokens_salida=salida, proveedor=self.nombre, modelo=self.modelo)

    def generar_json(self, *, sistema: str, contenido: list[dict], esquema: dict,
                     max_tokens: int = MAX_TOKENS_JSON,
                     latido: Optional[Callable[[], None]] = None) -> RespuestaJSON:
        """Sin streaming: `latido` se llama una vez, al terminar la llamada."""
        cuerpo = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": [_parte(b) for b in contenido]}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "salida", "schema": esquema}},
        }
        respuesta = self._enviar(cuerpo)
        if latido is not None:
            try:
                latido()
            except Exception:  # noqa: BLE001 - el latido nunca corta la lectura
                logger.warning("Falló el latido tras la respuesta", exc_info=True)
        try:
            cortada = respuesta["choices"][0].get("finish_reason") == "length"
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProveedorNoDisponible(_FORMATO)
        if cortada:
            raise RespuestaIncompleta("La respuesta del modelo quedó incompleta (demasiado larga).")
        texto = _texto(_mensaje(respuesta))
        try:
            datos = json.loads(texto or "")
        except json.JSONDecodeError as e:
            raise ProveedorNoDisponible(_FORMATO) from e
        if not isinstance(datos, dict):
            raise ProveedorNoDisponible(_FORMATO)
        entrada, salida = _tokens(respuesta)
        return RespuestaJSON(datos=datos, tokens_entrada=entrada, tokens_salida=salida,
                             proveedor=self.nombre, modelo=self.modelo)

    def _enviar(self, cuerpo: dict) -> Any:
        """A lo más un reintento, solo ante 5xx o timeout/red. Un 429 no se
        reintenta: el proveedor ya dijo que esperemos (pero sí es recuperable:
        el respaldo prueba el siguiente modelo de la lista)."""
        ultimo = _SIN_RED
        for _ in range(2):
            try:
                r = self._http.post(self.url, json=cuerpo)
            except httpx.TimeoutException:
                ultimo = _TARDO
                continue
            except httpx.HTTPError as e:
                logger.warning("LLM sin red: %s", e)
                ultimo = _SIN_RED
                continue
            if r.status_code == 429:
                raise ProveedorNoDisponible(
                    "El proveedor del asistente alcanzó su límite de uso. Intenta en unos minutos.",
                    recuperable=True,
                )
            if r.status_code >= 500:
                ultimo = f"El proveedor del asistente no responde (HTTP {r.status_code}). Intenta de nuevo."
                continue
            if r.status_code != 200:
                logger.warning("LLM respondió %s: %s", r.status_code, r.text[:300])
                raise ProveedorNoDisponible(
                    f"El proveedor rechazó la petición (HTTP {r.status_code}). Revisa la llave y el modelo."
                )
            try:
                return r.json()
            except ValueError:
                raise ProveedorNoDisponible(_FORMATO)
        raise ProveedorNoDisponible(ultimo, recuperable=True)
