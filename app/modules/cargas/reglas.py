"""Reglas de carga por organización (`organization.reglas_carga`, JSON)."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TipoPrenda(BaseModel):
    codigo_sku: str
    departamento: str


class RangoPrecio(BaseModel):
    tipo: str
    marca: Optional[str] = None
    precios: list[Decimal] = Field(default_factory=list)


class ReglasCarga(BaseModel):
    costo_si_falta: Literal["preguntar", "fraccion_precio"] = "preguntar"
    # Costo = precio × fracción: más de 0 y a lo más el precio completo.
    fraccion: Decimal = Field(Decimal("0.5"), gt=0, le=1)
    iva: bool = False
    sucursal_recibe: Optional[int] = None
    activar_en: Literal["todas_las_que_venden", "sucursal_recibe"] = "todas_las_que_venden"
    mapa_tallas: dict[str, str] = Field(default_factory=dict)
    escala_ropa: list[str] = Field(default_factory=list)
    tipos: dict[str, TipoPrenda] = Field(default_factory=dict)
    materiales_aparte: list[str] = Field(default_factory=list)
    material_normal: Optional[str] = None
    genero_por_marca: dict[str, str] = Field(default_factory=dict)
    genero_por_omision: Optional[str] = None
    sufijo_dama: Optional[str] = None
    matriz_por_omision: Literal["completa", "solo_lo_que_hay"] = "solo_lo_que_hay"
    precios_familia: list[RangoPrecio] = Field(default_factory=list)
    ventana_ya_cargado_dias: int = Field(14, ge=0, le=90)


def reglas_de_la_org(org) -> ReglasCarga:
    """Reglas de la organización; `None` o vacío dan todos los defaults."""
    return ReglasCarga.model_validate(getattr(org, "reglas_carga", None) or {})
