from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import date, datetime
from decimal import Decimal

# ... Tus clases TopProduct y DailySummary se mantienen igual ...

class CustomerAging(BaseModel):
    customer_id: int
    customer_name: str
    total_balance: Decimal
    # Cubetas de antigüedad
    current_0_30: Decimal
    overdue_31_60: Decimal
    overdue_61_90: Decimal
    overdue_91_plus: Decimal

class AgingReportResponse(BaseModel):
    report_date: date
    total_receivable: Decimal  # Suma total de lo que deben todos los clientes
    customers: List[CustomerAging]

    class Config:
        from_attributes = True


# --- Valor de la tienda (valuacion de inventario) ---------------------------
# Dinero y piezas viajan como float (JSON numerico, como /dashboard); Decimal se
# serializaria como cadena en Pydantic v2 y la tarjeta tendria que parsear.

class ValuacionTotales(BaseModel):
    piezas: float
    skus: int
    valor_venta: float
    valor_costo: Optional[float]  # None cuando el rol no ve costos (gerente)
    piezas_sin_costo: float
    skus_sin_costo: int


class ValuacionGrupo(BaseModel):
    clave: str   # id de sucursal/departamento/marca; "" = sin asignar
    nombre: str
    piezas: float
    skus: int
    valor_venta: float
    valor_costo: Optional[float]
    piezas_sin_costo: float


class ValuacionInventarioResponse(BaseModel):
    agrupar: str
    branch_id: Optional[int]
    ve_costo: bool
    totales: ValuacionTotales
    grupos: List[ValuacionGrupo]


# --- Inicio básico (GET /api/reports/inicio-basico, modo básico 2026-10) ----
# Floats y no Decimal: igual que la valuación, la pantalla no tiene que parsear.

class PeriodoVentas(BaseModel):
    desde: date
    hasta: date
    total: float
    tickets: int


class ProductoTop(BaseModel):
    nombre: str
    cantidad: float
    total: float


class ProductoPocaExistencia(BaseModel):
    variant_id: str
    nombre: str
    sku: str
    existencia: float


class PocaExistencia(BaseModel):
    umbral: int
    productos: List[ProductoPocaExistencia]


class CorteInicio(BaseModel):
    estado: str  # 'abierto' | 'cerrado' | 'sin_turno'
    cajera: Optional[str] = None
    abierto_en: Optional[datetime] = None
    cerrado_en: Optional[datetime] = None
    efectivo_esperado: Optional[float] = None  # solo con turno abierto
    efectivo_contado: Optional[float] = None   # solo con turno cerrado


class InicioBasicoResponse(BaseModel):
    branch_id: Optional[int]  # None = todas las sucursales de la org
    hoy: PeriodoVentas
    ayer: PeriodoVentas
    semana: PeriodoVentas
    por_metodo_hoy: Dict[str, float]
    top_semana: List[ProductoTop]
    poca_existencia: PocaExistencia
    corte: CorteInicio
