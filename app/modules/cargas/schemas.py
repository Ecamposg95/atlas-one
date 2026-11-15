"""Esquemas de petición/respuesta de "Cargar mercancía con IA"."""
from __future__ import annotations

from pydantic import BaseModel, constr

LIMITE_RESPUESTA = 4000


class RespuestaTexto(BaseModel):
    """Respuesta escrita del dueño a las dudas del plan (tope: 4,000 caracteres)."""

    texto: constr(min_length=1, max_length=LIMITE_RESPUESTA)  # type: ignore[valid-type]
