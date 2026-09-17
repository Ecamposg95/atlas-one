from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from decimal import Decimal
from datetime import datetime

# Replicamos el Enum de métodos de pago
class PaymentMethodSchema(str, Enum):
    CASH = "CASH"
    CARD = "CARD"
    TRANSFER = "TRANSFER"
    OTHER = "OTHER"

# --- Models for Creation ---

class SaleItemCreate(BaseModel):
    sku: str
    # Variante exacta (boutique: la talla/color elegida). Si viene, manda sobre
    # `sku`, que se conserva como respaldo y para los mensajes de error.
    variant_id: Optional[str] = None
    quantity: float = 1.0
    unit_price: Optional[Decimal] = None
    discount: Optional[float] = Field(default=0.0, ge=0.0, le=100.0)   # porcentaje 0-100
    notes: Optional[str] = None

class PaymentCreate(BaseModel):
    method: PaymentMethodSchema
    amount: Decimal
    reference: Optional[str] = None

class SaleCreate(BaseModel):
    id: Optional[str] = None # permite que el cliente móvil envíe su UUID (DRAFT)
    # Idempotencia del checkout: el POS lo genera una vez por intento de cobro
    # y lo reenvía igual en cada reintento. Ver app/routers/sales.py.
    client_uuid: Optional[str] = None
    doc_type: Optional[str] = "QUOTE" # QUOTE or ORDER
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None # Nuevo campo libre
    requires_invoice: bool = False
    items: List[SaleItemCreate]
    payments: List[PaymentCreate]
    # H-2: descuento global aplicado por el cajero (auditoría). El frontend ya
    # multiplica el factor en cada unit_price; aquí guardamos el % para reportes.
    global_discount_pct: Optional[Decimal] = Decimal("0")
    # Gastro — propina cobrada al cliente (se suma al total; los pagos deben cubrirla).
    tip_amount: Optional[Decimal] = Decimal("0")
    # M-3: si la venta proviene de un ticket pausado, lo marcamos CONVERTED al
    # crear (o lo soft-deleteamos) para evitar doble cobro por reanudar dos veces.
    parked_ticket_id: Optional[str] = None
    # Notas libres del documento (cotizaciones: observaciones del vendedor).
    notes: Optional[str] = None

# --- Models for Reading (History) ---

class SaleLineRead(BaseModel):
    id: str # UUID
    variant_id: str # UUID
    sku: Optional[str] = None # Added SKU for POS handling
    description: Optional[str] = "Item"
    quantity: float
    unit_price: Decimal
    total_line: Decimal
    has_iva: bool = False
    tax_rate: float = 0.0

    class Config:
        from_attributes = True

class EnrichedSaleLineRead(SaleLineRead):
    product_id: Optional[str] = None
    stock: float = 0.0
    packaging_units: Optional[List[dict]] = None
    
    class Config:
        from_attributes = True

class PaymentRead(BaseModel):
    id: str # UUID
    amount: Decimal
    method: PaymentMethodSchema
    created_at: datetime

    class Config:
        from_attributes = True

class SaleRead(BaseModel):
    id: str # UUID
    doc_type: str
    status: str
    branch_id: int
    branch_name: Optional[str] = None
    seller_id: int
    customer_id: Optional[int]
    customer_name: Optional[str]

    series: Optional[str]
    folio: Optional[int]

    subtotal: Optional[Decimal] = Decimal(0)
    tax_amount: Optional[Decimal] = Decimal(0)
    total_amount: Decimal
    requires_invoice: Optional[bool] = False
    created_at: datetime
    
    # We can include details if needed, but for list view usually lightweight is better.
    # We will include them for now for simplicity of the "View Details" modal
    lines: List[SaleLineRead] = []
    payments: List[PaymentRead] = []
    returns: List["SaleReturn"] = []

    class Config:
        from_attributes = True

# Import at the end to avoid circularity if any
from app.schemas.returns import SaleReturn
SaleRead.model_rebuild()

class QuoteDetailRead(SaleRead):
    lines: List[EnrichedSaleLineRead] = []
    
    class Config:
        from_attributes = True


# ── Track 2 (POS bug-fix): tickets pausados ──────────────────────────────────
class ParkedTicketCreate(BaseModel):
    """Snapshot del carrito + customer para guardar como pausado."""
    cart_json: dict
    customer_id: Optional[int] = None
    notes: Optional[str] = None
    expires_in_hours: Optional[int] = 24


class ParkedTicketUpdate(BaseModel):
    """Reemplaza el cart_json de una cuenta abierta (mesa). El merge de
    'ítems existentes + comanda nueva' lo hace el cliente antes de mandar."""
    cart_json: dict
    notes: Optional[str] = None


class ParkedTicketRead(BaseModel):
    id: str
    branch_id: int
    user_id: int
    customer_id: Optional[int] = None
    cart_json: dict
    notes: Optional[str] = None
    parked_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True
