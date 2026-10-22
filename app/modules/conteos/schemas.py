"""Contratos de `/api/inventory/counts` (Pydantic v2)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProductoResumen(BaseModel):
    variant_id: str
    nombre: str
    marca: Optional[str] = None
    talla: Optional[str] = None
    color: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    foto: Optional[str] = None
    departamento: Optional[str] = None


class LineaRead(BaseModel):
    id: int
    variant_id: Optional[str] = None
    codigo: Optional[str] = None
    qty_contada: Decimal
    qty_sistema: Optional[Decimal] = None
    producto: Optional[ProductoResumen] = None
    updated_at: Optional[datetime] = None


class Avance(BaseModel):
    esperadas_variantes: int
    esperadas_piezas: Decimal
    contadas_variantes: int
    contadas_piezas: Decimal
    desconocidos: int


class ConteoCreate(BaseModel):
    branch_id: Optional[int] = None
    department_id: Optional[str] = None
    notes: Optional[str] = None


class ConteoRead(BaseModel):
    id: int
    branch_id: int
    branch_name: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    avance: Avance


class ConteoDetalle(ConteoRead):
    lineas: List[LineaRead] = []


class LineaCreate(BaseModel):
    variant_id: str
    qty: Decimal = Field(default=Decimal("1"), gt=0)


class LineaPatch(BaseModel):
    qty_contada: Decimal = Field(ge=0)


class ScanRequest(BaseModel):
    code: str


class ScanResult(BaseModel):
    resultado: Literal["contado", "ambiguo", "desconocido"]
    linea: Optional[LineaRead] = None
    producto: Optional[ProductoResumen] = None
    qty_sistema: Optional[Decimal] = None
    fuera_de_alcance: bool = False
    candidatos: List[ProductoResumen] = []


class FilaReporte(BaseModel):
    variant_id: str
    sku: Optional[str] = None
    nombre: str
    marca: Optional[str] = None
    talla: Optional[str] = None
    color: Optional[str] = None
    departamento: Optional[str] = None
    sistema: Decimal
    contado: Decimal
    diferencia: Decimal


class FilaDesconocido(BaseModel):
    codigo: str
    contado: Decimal


class Reporte(BaseModel):
    estado: str
    generado_en: datetime
    alcance: dict
    totales: dict
    faltantes: List[FilaReporte] = []
    sobrantes: List[FilaReporte] = []
    fuera_de_alcance: List[FilaReporte] = []
    desconocidos: List[FilaDesconocido] = []
