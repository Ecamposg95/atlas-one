"""Proveedores de IA detrás de una sola interfaz (ver `base.py` y docs/ai/README.md)."""
from .base import (
    MAX_TOKENS_CONVERSAR, MAX_TOKENS_JSON, LlamadaHerramienta, Proveedor, ProveedorNoDisponible,
    Respuesta, RespuestaIncompleta, RespuestaJSON,
)
from .anthropic_nativo import ProveedorAnthropic
from .falso import ProveedorFalso
from .openai_compatible import ProveedorOpenAI
from .respaldo import ProveedorConRespaldo

__all__ = [
    "MAX_TOKENS_CONVERSAR", "MAX_TOKENS_JSON", "LlamadaHerramienta", "Proveedor",
    "ProveedorNoDisponible", "Respuesta", "RespuestaIncompleta", "RespuestaJSON",
    "ProveedorAnthropic", "ProveedorOpenAI", "ProveedorFalso", "ProveedorConRespaldo",
]
