"""Cliente de salida estructurada (JSON con esquema) sobre el SDK de Anthropic.

Lo usa "Cargar mercancía con IA". Modelo por `AI_MODELO` (por omisión
`claude-opus-5-5`), clave en `ANTHROPIC_API_KEY`, fallback server-side con la
beta `server-side-fallback-2026-07-01`.

La suite NUNCA llama al proveedor: usa `ClienteEstructuradoFalso`.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from fastapi import HTTPException

from app.modules.ai.cliente_llm import ProveedorNoDisponible

logger = logging.getLogger(__name__)

MODELO_POR_DEFECTO = "claude-opus-5-5"
BETA_FALLBACK = "server-side-fallback-2026-07-01"
NO_CONFIGURADO = "IA no configurada: falta ANTHROPIC_API_KEY en el servidor."
# Tope por llamada (spec §7): sin él el SDK espera 10 min y reintenta 2 veces.
TIMEOUT_POR_DEFECTO = 300.0
REINTENTOS = 1

__all__ = [
    "ProveedorNoDisponible", "RespuestaEstructurada", "ClienteEstructurado",
    "ClienteAnthropic", "ClienteEstructuradoFalso", "cliente_estructurado_por_defecto",
]


@dataclass
class RespuestaEstructurada:
    datos: dict
    tokens_entrada: int
    tokens_salida: int


class ClienteEstructurado(Protocol):
    def generar(self, *, sistema: str, contenido: list[dict], esquema: dict,
                max_tokens: int = 64000) -> RespuestaEstructurada: ...


class ClienteAnthropic:
    def __init__(self, api_key: str, modelo: str, timeout: float = TIMEOUT_POR_DEFECTO):
        self.api_key = api_key
        self.modelo = modelo
        self.timeout = timeout

    def generar(self, *, sistema: str, contenido: list[dict], esquema: dict,
                max_tokens: int = 64000) -> RespuestaEstructurada:
        import anthropic

        try:
            client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout,
                                         max_retries=REINTENTOS)
            with client.beta.messages.stream(
                model=self.modelo,
                max_tokens=max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": contenido}],
                output_config={"format": {"type": "json_schema", "schema": esquema}},
                betas=[BETA_FALLBACK],
                fallbacks="default",
            ) as flujo:
                mensaje = flujo.get_final_message()
        except anthropic.APIError as e:
            logger.warning("Error de la API de Anthropic: %s", e)
            raise ProveedorNoDisponible("No se pudo contactar al proveedor de IA. Intenta de nuevo.") from e

        if getattr(mensaje, "stop_reason", None) == "refusal":
            raise ProveedorNoDisponible("El modelo rechazó procesar este documento.")
        if getattr(mensaje, "stop_reason", None) == "max_tokens":
            raise ProveedorNoDisponible("La respuesta del modelo quedó incompleta (documento demasiado grande).")

        texto = next((b.text for b in (mensaje.content or []) if getattr(b, "type", None) == "text"), None)
        if texto is None:
            raise ProveedorNoDisponible("Respuesta del proveedor sin contenido de texto.")
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ProveedorNoDisponible("Respuesta del proveedor con formato inesperado.") from e
        if not isinstance(datos, dict):
            raise ProveedorNoDisponible("Respuesta del proveedor con formato inesperado.")

        uso = getattr(mensaje, "usage", None)
        return RespuestaEstructurada(
            datos=datos,
            tokens_entrada=int(getattr(uso, "input_tokens", 0) or 0),
            tokens_salida=int(getattr(uso, "output_tokens", 0) or 0),
        )


@dataclass
class ClienteEstructuradoFalso:
    """Doble de pruebas: devuelve (o lanza) los elementos del guion en orden."""
    guion: list = field(default_factory=list)
    llamadas: list = field(default_factory=list)

    def generar(self, *, sistema: str, contenido: list[dict], esquema: dict,
                max_tokens: int = 64000) -> RespuestaEstructurada:
        self.llamadas.append({"sistema": sistema, "contenido": contenido,
                              "esquema": esquema, "max_tokens": max_tokens})
        if not self.guion:
            raise AssertionError("ClienteEstructuradoFalso: guion agotado")
        paso = self.guion.pop(0)
        if isinstance(paso, Exception):
            raise paso
        return RespuestaEstructurada(datos=paso, tokens_entrada=0, tokens_salida=0)


def cliente_estructurado_por_defecto() -> ClienteAnthropic:
    clave = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not clave:
        raise HTTPException(status_code=503, detail=NO_CONFIGURADO)
    modelo = (os.getenv("AI_MODELO") or "").strip() or MODELO_POR_DEFECTO
    return ClienteAnthropic(api_key=clave, modelo=modelo, timeout=_timeout())


def _timeout() -> float:
    """`AI_TIMEOUT_SEG` (segundos por llamada); vacío o inválido → 300."""
    try:
        valor = float((os.getenv("AI_TIMEOUT_SEG") or "").strip())
    except ValueError:
        return TIMEOUT_POR_DEFECTO
    return valor if math.isfinite(valor) and valor > 0 else TIMEOUT_POR_DEFECTO
