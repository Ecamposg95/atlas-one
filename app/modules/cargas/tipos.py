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


class RenglonNormalizado(RenglonCrudo):
    """Renglón con tallas, género, departamento y costo ya resueltos."""

    genero: Optional[str] = None
    departamento: Optional[str] = None
    costo_mxn: Optional[Decimal] = None
    llave_grupo: str = ""


class Grupo(BaseModel):
    """Renglones que serán un mismo producto (con una variante por talla)."""

    llave: str
    renglones: list[int]  # índices en la lista de entrada
    # talla -> precio de esa talla (None = sin precio). "" = renglón sin talla.
    tallas: dict[str, Optional[Decimal]] = Field(default_factory=dict)
    sufijo: str = ""
    # Datos del primer renglón, para el respaldo de SKU.
    marca: Optional[str] = None
    tipo: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    genero: Optional[str] = None
