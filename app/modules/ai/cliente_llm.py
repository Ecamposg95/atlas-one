"""Cliente del proveedor LLM: cualquier API compatible con OpenAI
(`POST {base}/chat/completions` con `tools`).

Por defecto Gemini Flash en su capa compatible (nivel gratuito con tool
calling; ojo: en ese nivel Google usa el contenido para mejorar sus
productos). Cambiar a Groq, Mistral u OpenAI = cambiar `LLM_BASE_URL`,
`LLM_MODEL` y `LLM_API_KEY`. Sin SDK: httpx, que ya está en requirements.

La suite NUNCA llama al proveedor: usa `ClienteFalso` o `httpx.MockTransport`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

BASE_URL_POR_DEFECTO = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODELO_POR_DEFECTO = "gemini-3.8-flash"
TIMEOUT_SEGUNDOS = 45.0
TOKENS_DIA_POR_DEFECTO = 200_000
NO_CONFIGURADO = "Asistente no configurado: falta LLM_API_KEY en el servidor."

_FORMATO = "Respuesta del proveedor con formato inesperado."
_TARDO = "El proveedor del asistente tardó demasiado en responder. Intenta de nuevo."
_SIN_RED = "No se pudo contactar al proveedor del asistente. Intenta de nuevo."


class ProveedorNoDisponible(RuntimeError):
    """El proveedor no respondió o respondió algo inutilizable (→ HTTP 503)."""


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos: dict[str, Any]
    argumentos_crudos: str = "{}"
    # Texto del error cuando los argumentos no son un objeto JSON válido: la
    # herramienta no se ejecuta y el modelo recibe el error para corregirse.
    error_json: Optional[str] = None

    @classmethod
    def desde_crudo(cls, id: str, nombre: str, crudo: Any) -> "LlamadaHerramienta":
        if isinstance(crudo, dict):
            return cls(id=id, nombre=nombre, argumentos=crudo,
                       argumentos_crudos=json.dumps(crudo, ensure_ascii=False))
        texto = crudo if isinstance(crudo, str) else ""
        if not texto.strip():
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos="{}")
        try:
            valor = json.loads(texto)
        except json.JSONDecodeError as e:
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos=texto, error_json=str(e))
        if not isinstance(valor, dict):
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos=texto,
                       error_json="los argumentos no son un objeto JSON")
        return cls(id=id, nombre=nombre, argumentos=valor, argumentos_crudos=texto)

    def como_tool_call(self) -> dict:
        return {"id": self.id, "type": "function",
                "function": {"name": self.nombre, "arguments": self.argumentos_crudos}}


@dataclass
class RespuestaLLM:
    texto: Optional[str] = None
    tool_calls: list[LlamadaHerramienta] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0


class ClienteLLM(Protocol):
    def completar(self, mensajes: list[dict], herramientas: list[dict]) -> RespuestaLLM: ...


@dataclass(frozen=True)
class ConfiguracionLLM:
    base_url: str
    modelo: str
    api_key: Optional[str]


def configuracion() -> ConfiguracionLLM:
    return ConfiguracionLLM(
        base_url=(os.getenv("LLM_BASE_URL") or BASE_URL_POR_DEFECTO).strip(),
        modelo=(os.getenv("LLM_MODEL") or MODELO_POR_DEFECTO).strip(),
        api_key=(os.getenv("LLM_API_KEY") or "").strip() or None,
    )


def limite_tokens_dia() -> int:
    """`AI_TOKENS_DIA_ORG` (entrada + salida por organización y día)."""
    try:
        valor = int(os.getenv("AI_TOKENS_DIA_ORG") or TOKENS_DIA_POR_DEFECTO)
    except ValueError:
        return TOKENS_DIA_POR_DEFECTO
    return valor if valor > 0 else TOKENS_DIA_POR_DEFECTO


def _leer_respuesta(cuerpo: Any) -> RespuestaLLM:
    try:
        mensaje = cuerpo["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise ProveedorNoDisponible(_FORMATO)
    contenido = mensaje.get("content")
    if isinstance(contenido, list):  # algunos proveedores mandan partes
        contenido = "".join(p.get("text", "") for p in contenido if isinstance(p, dict))
    llamadas = []
    for i, tc in enumerate(mensaje.get("tool_calls") or []):
        funcion = (tc or {}).get("function") or {}
        llamadas.append(LlamadaHerramienta.desde_crudo(
            (tc or {}).get("id") or f"llamada_{i}", funcion.get("name") or "", funcion.get("arguments"),
        ))
    uso = cuerpo.get("usage") or {}
    return RespuestaLLM(
        texto=contenido if isinstance(contenido, str) else None,
        tool_calls=llamadas,
        tokens_entrada=int(uso.get("prompt_tokens") or 0),
        tokens_salida=int(uso.get("completion_tokens") or 0),
    )


class ClienteOpenAICompatible:
    def __init__(self, base_url: str, api_key: str, modelo: str, timeout: float = TIMEOUT_SEGUNDOS,
                 transport: Optional[httpx.BaseTransport] = None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.modelo = modelo
        self._http = httpx.Client(
            timeout=timeout, transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    def completar(self, mensajes: list[dict], herramientas: list[dict]) -> RespuestaLLM:
        cuerpo: dict[str, Any] = {"model": self.modelo, "messages": mensajes}
        if herramientas:
            cuerpo["tools"] = herramientas
            cuerpo["tool_choice"] = "auto"
        return _leer_respuesta(self._enviar(cuerpo))

    def _enviar(self, cuerpo: dict) -> Any:
        """A lo más un reintento, solo ante 5xx o timeout/red. Un 429 no se
        reintenta: el proveedor ya dijo que esperemos."""
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
                    "El proveedor del asistente alcanzó su límite de uso. Intenta en unos minutos."
                )
            if r.status_code >= 500:
                ultimo = f"El proveedor del asistente no responde (HTTP {r.status_code}). Intenta de nuevo."
                continue
            if r.status_code != 200:
                logger.warning("LLM respondió %s: %s", r.status_code, r.text[:300])
                raise ProveedorNoDisponible(
                    f"El proveedor rechazó la petición (HTTP {r.status_code}). Revisa LLM_API_KEY y LLM_MODEL."
                )
            try:
                return r.json()
            except ValueError:
                raise ProveedorNoDisponible(_FORMATO)
        raise ProveedorNoDisponible(ultimo)


class ClienteFalso:
    """Cliente de la suite: devuelve un guion fijo y anota cada llamada."""

    def __init__(self, guion: list[RespuestaLLM]):
        self.guion = list(guion)
        self.llamadas: list[dict] = []

    def completar(self, mensajes: list[dict], herramientas: list[dict]) -> RespuestaLLM:
        self.llamadas.append({"mensajes": [dict(m) for m in mensajes], "herramientas": list(herramientas or [])})
        if not self.guion:
            raise AssertionError("ClienteFalso sin guion: la prueba no esperaba otra llamada al modelo.")
        return self.guion.pop(0)


def cliente_por_defecto() -> ClienteOpenAICompatible:
    cfg = configuracion()
    if not cfg.api_key:
        raise HTTPException(status_code=503, detail=NO_CONFIGURADO)
    return ClienteOpenAICompatible(cfg.base_url, cfg.api_key, cfg.modelo)
