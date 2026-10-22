"""Contratos de `/api/inventory/counts` (Pydantic v2)."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, PlainSerializer, model_validator

# Cantidades en JSON sin ceros de relleno (Numeric(.,2) devuelve '3.00'): '3', '2.5'.
Cant = Annotated[Decimal, PlainSerializer(lambda d: format(d.normalize(), 'f'), return_type=str, when_used='json')]


class ProductoResumen(BaseModel):
    variant_id: str
    product_id: str
    nombre: str
    marca: Optional[str] = None
    marca_id: Optional[str] = None
    modelo: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[Cant] = None
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
    qty_contada: Cant
    qty_sistema: Optional[Cant] = None
    producto: Optional[ProductoResumen] = None
    corregida: bool = False
    updated_at: Optional[datetime] = None


class Avance(BaseModel):
    esperadas_variantes: int
    esperadas_piezas: Cant
    contadas_variantes: int
    contadas_piezas: Cant
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
    """Al menos uno de los dos: cantidad (0 borra) o la marca de ficha corregida."""
    qty_contada: Optional[Decimal] = Field(default=None, ge=0)
    corregida: Optional[bool] = None

    @model_validator(mode="after")
    def _algo_que_cambiar(self):
        if self.qty_contada is None and self.corregida is None:
            raise ValueError("Manda qty_contada o corregida")
        return self


class ScanRequest(BaseModel):
    code: str


class ScanResult(BaseModel):
    resultado: Literal["contado", "ambiguo", "desconocido"]
    linea: Optional[LineaRead] = None
    producto: Optional[ProductoResumen] = None
    qty_sistema: Optional[Cant] = None
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
    sistema: Cant
    contado: Cant
    diferencia: Cant
    corregida: bool = False


class FilaDesconocido(BaseModel):
    codigo: str
    contado: Cant


class Reporte(BaseModel):
    estado: str
    generado_en: datetime
    alcance: dict
    totales: dict
    faltantes: List[FilaReporte] = []
    sobrantes: List[FilaReporte] = []
    fuera_de_alcance: List[FilaReporte] = []
    desconocidos: List[FilaDesconocido] = []


EstadoFila = Literal["pendiente", "revisado", "diferencia"]


class FilaLista(BaseModel):
    producto: ProductoResumen
    sistema: Cant
    contado: Cant
    estado: EstadoFila
    corregida: bool = False
    line_id: Optional[int] = None


class Lista(BaseModel):
    filas: List[FilaLista]
    totales: dict
