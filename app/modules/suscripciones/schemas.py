"""Schemas del cobro de suscripciones. El dinero viaja como Decimal (texto en JSON)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ───────────── Entradas (plataforma) ─────────────

class SuscripcionEntrada(BaseModel):
    """Alta o edición: solo se aplica lo que viene."""
    plan: Optional[str] = None
    precio_mxn: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=2)
    periodicidad: Optional[str] = None
    dia_corte: Optional[int] = Field(None, ge=1, le=28)
    fecha_inicio: Optional[date] = None
    proxima_renovacion: Optional[date] = None
    estado: Optional[str] = None
    notas: Optional[str] = None
    rfc: Optional[str] = Field(None, max_length=13)
    razon_social: Optional[str] = Field(None, max_length=255)
    correo_facturacion: Optional[str] = Field(None, max_length=255)


class CargoEntrada(BaseModel):
    periodo_desde: Optional[date] = None
    importe: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
    vence_el: Optional[date] = None


class PagoEntrada(BaseModel):
    importe: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    metodo: str
    fecha_pago: Optional[date] = None
    referencia: Optional[str] = Field(None, max_length=120)
    notas: Optional[str] = None


class CancelarCargoEntrada(BaseModel):
    motivo: Optional[str] = Field(None, max_length=255)


# ───────────── Salidas ─────────────

class PagoRead(BaseModel):
    id: int
    importe: Decimal
    fecha_pago: date
    metodo: str
    referencia: Optional[str] = None
    # Solo plataforma: la tienda recibe estos dos en None.
    notas: Optional[str] = None
    registrado_por: Optional[str] = None
    created_at: Optional[datetime] = None


class CargoRead(BaseModel):
    id: int
    periodo_desde: date
    periodo_hasta: date
    importe: Decimal
    pagado: Decimal
    saldo: Decimal
    vence_el: date
    estado: str
    vencido: bool
    pagado_at: Optional[datetime] = None
    cancelado_at: Optional[datetime] = None
    motivo_cancelacion: Optional[str] = None
    pagos: List[PagoRead] = []


class SuscripcionRead(BaseModel):
    id: int
    organization_id: int
    plan: str
    plan_nombre: str
    precio_mxn: Decimal
    precio_lista_mxn: Decimal
    periodicidad: str
    dia_corte: int
    fecha_inicio: date
    proxima_renovacion: date
    estado: str            # calculado al momento de leer
    estado_manual: bool    # suspendida o cortesia: puesto a mano
    notas: Optional[str] = None
    rfc: Optional[str] = None
    razon_social: Optional[str] = None
    correo_facturacion: Optional[str] = None


class SuscripcionDetalle(BaseModel):
    organization_id: int
    organizacion: str
    plan_organizacion: Optional[str] = None
    suscripcion: Optional[SuscripcionRead] = None
    cargos: List[CargoRead] = []


class GenerarCargoRead(BaseModel):
    creado: bool
    cargo: CargoRead


class FilaSuscripcion(BaseModel):
    organization_id: int
    organizacion: str
    plan: str
    plan_nombre: str
    precio_mxn: Decimal
    periodicidad: str
    proxima_renovacion: date
    estado: str
    saldo_vencido: Decimal
    saldo_por_vencer: Decimal


class TotalesSuscripciones(BaseModel):
    cartera_vencida: Decimal
    por_vencer: Decimal
    ingreso_mensual_recurrente: Decimal
    por_estado: Dict[str, int]
    sin_suscripcion: int


class ListaSuscripciones(BaseModel):
    totales: TotalesSuscripciones
    items: List[FilaSuscripcion]


# ───────────── Tienda ─────────────

class PlanTienda(BaseModel):
    clave: str
    nombre: str
    precio_lista_mxn: Decimal
    max_usuarios: Optional[int] = None
    max_sucursales_venta: Optional[int] = None


class UsoTienda(BaseModel):
    usuarios_activos: int
    sucursales_venta: int


class MiSuscripcion(BaseModel):
    plan: PlanTienda
    uso: UsoTienda
    suscripcion: Optional[SuscripcionRead] = None
    cargos: List[CargoRead] = []
