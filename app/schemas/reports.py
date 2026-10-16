from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import date
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
