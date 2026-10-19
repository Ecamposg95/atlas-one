"""Schemas del asistente IA: lo que entra y sale del router y los datos de
las propuestas `agregar_variantes` / `ajustar_existencias`.

`crear_producto` no tiene schema propio: sus datos son exactamente
`ProductCreate` de SP1 (`app/modules/products/schemas.py`).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

TOPE_TEXTO = 4000


class ConversacionCrear(BaseModel):
    titulo: Optional[str] = Field(default=None, max_length=120)


class MensajeCrear(BaseModel):
    texto: str = Field(min_length=1, max_length=TOPE_TEXTO)


class AplicadaManual(BaseModel):
    """La persona guardó la propuesta desde el formulario (Ajustar en formulario)."""
    producto_id: Optional[str] = Field(default=None, max_length=36)


class MensajeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rol: str
    contenido: Optional[str] = None
    created_at: datetime


class PropuestaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tipo: str
    datos: dict[str, Any]
    estado: str
    resumen: str
    avisos: List[str] = Field(default_factory=list)
    resultado: Optional[dict[str, Any]] = None
    created_at: datetime

    @field_validator("avisos", mode="before")
    @classmethod
    def _sin_avisos_es_lista(cls, v):
        return v or []


class ConversacionResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    titulo: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversacionDetalle(ConversacionResumen):
    mensajes: List[MensajeRead] = Field(default_factory=list)
    propuestas: List[PropuestaRead] = Field(default_factory=list)


class RespuestaTurno(BaseModel):
    mensaje: MensajeRead
    propuestas_pendientes: List[PropuestaRead] = Field(default_factory=list)


# ── Datos de las propuestas ──────────────────────────────────────────────────

class VarianteNueva(BaseModel):
    color: Optional[str] = None
    # El spec usa "talla" en el texto y "size" en el ejemplo: se aceptan los dos.
    size: Optional[str] = Field(default=None, validation_alias=AliasChoices("size", "talla"))
    sku: Optional[str] = None
    precio: Optional[Decimal] = None
    existencia: Decimal = Field(default=Decimal(0), ge=0)


class DatosAgregarVariantes(BaseModel):
    product_id: str
    sucursal_id: Optional[int] = None
    variantes: List[VarianteNueva] = Field(min_length=1, max_length=60)


class AjusteExistencia(BaseModel):
    variant_id: str
    sucursal_id: int
    existencia_nueva: Decimal = Field(ge=0)


class DatosAjustarExistencias(BaseModel):
    ajustes: List[AjusteExistencia] = Field(min_length=1, max_length=50)
