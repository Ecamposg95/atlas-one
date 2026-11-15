"""Tipos compartidos de "Cargar mercancía con IA"."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class RenglonCrudo(BaseModel):
    descripcion_original: str
    marca: Optional[str] = None
    tipo: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    talla: Optional[str] = None
    cantidad: Decimal
    costo_unitario: Optional[Decimal] = None
    precio: Optional[Decimal] = None
    moneda: Optional[str] = None
    observacion: Optional[str] = None
    duda: Optional[str] = None
    origen: str  # p. ej. "Hoja1!R12" o "pág. 3"


class TablaCruda(BaseModel):
    pestana: str
    encabezados: list[str]
    filas: list[list[Any]]
    # Número de fila en el archivo de cada elemento de `filas` (1 = encabezado).
    filas_origen: list[int] = Field(default_factory=list)
