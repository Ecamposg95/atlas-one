"""Schemas de la API de planes de plataforma."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class PlanRead(BaseModel):
    clave: str
    nombre: str
    lema: str
    precio_mxn: int
    precio_desde: bool
    max_usuarios: Optional[int]
    max_sucursales_venta: Optional[int]
    modulos_crecimiento: List[str]
    permite_todo: bool


class PlanUsoRead(BaseModel):
    plan: PlanRead
    usuarios_activos: int
    sucursales_venta: int
    modulos_fuera_de_plan: List[str]
