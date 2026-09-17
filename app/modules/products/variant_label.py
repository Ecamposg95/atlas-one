"""Etiqueta y limpieza de los atributos color/talla de una variante.

Sin base de datos ni FastAPI a proposito: es la unica fuente de la etiqueta
que se guarda en `ProductVariant.variant_name` y que el ticket imprime entre
parentesis (`app/routers/sales.py::_line_description`).
"""
from __future__ import annotations

import re
from typing import Optional

COLOR_MAX = 60
SIZE_MAX = 30
DEFAULT_LABEL = "Estándar"

_ESPACIOS = re.compile(r"\s+")


def clean_attr(value: Optional[str], max_len: int) -> Optional[str]:
    """Recorta extremos, colapsa espacios internos y convierte vacio en None.

    Lanza ValueError si excede `max_len`: el caller lo convierte en 422 con el
    campo señalado, en vez de dejar que Postgres truncue o reviente.
    """
    if value is None:
        return None
    limpio = _ESPACIOS.sub(" ", value).strip()
    if not limpio:
        return None
    if len(limpio) > max_len:
        raise ValueError(f"máximo {max_len} caracteres")
    return limpio


def variant_label(color: Optional[str], size: Optional[str]) -> str:
    """"Rojo / M", "Rojo", "M" o "Estándar" cuando no hay atributos."""
    partes = [p for p in (clean_attr(color, COLOR_MAX), clean_attr(size, SIZE_MAX)) if p]
    return " / ".join(partes) if partes else DEFAULT_LABEL
