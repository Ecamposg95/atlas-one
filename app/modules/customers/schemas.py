"""Atlas BOS modules/customers/schemas — Pydantic v2.

Phase 2 / S2: moved from app/schemas/customers.py.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

# --- CLASES BASE ---

class CustomerBase(BaseModel):
    name: str
    tax_id: Optional[str] = None       # RFC / RUT / NIT
    tax_system: Optional[str] = None   # Régimen Fiscal (Ej. "601 - General")
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None     # Código Postal (Vital para facturar)
    
    # Configuración de Crédito
    has_credit: bool = False
    credit_limit: Decimal = Decimal("0.00")
    credit_days: int = 0               # Días de crédito (Ej. 15, 30)
    
    is_active: bool = True
    notes: Optional[str] = None

# --- CREACIÓN ---
class CustomerCreate(CustomerBase):
    enable_portal: bool = False
    password: Optional[str] = None

class CustomerPaymentCreate(BaseModel):
    amount: Decimal
    method: str = "CASH"
    reference: Optional[str] = None
    sales_document_id: Optional[str] = None  # NEW: Link payment to specific document

# --- ACTUALIZACIÓN ---
class CustomerUpdate(CustomerBase):
    name: Optional[str] = None
    enable_portal: Optional[bool] = None
    password: Optional[str] = None
    # Permitimos editar todo de forma opcional
    has_credit: Optional[bool] = None
    credit_limit: Optional[Decimal] = None
    is_active: Optional[bool] = None

# --- ESTADO DE CUENTA (Movimientos) ---
class LedgerEntryResponse(BaseModel):
    id: int
    created_at: datetime
    amount: Decimal          # Positivo = Cargo (Deuda), Negativo = Abono (Pago)
    description: Optional[str] = None
    sales_document_id: Optional[str] = None # ID Venta o Folio Pago
    
    class Config:
        from_attributes = True


class AbonoAplicado(BaseModel):
    sales_document_id: str
    folio: str
    amount: Decimal
    paid_in_full: bool


class AbonoResponse(BaseModel):
    """Respuesta de POST /customers/{id}/pay (spec 2026-10-29 §4.2): qué
    tickets cubrió el abono y cómo quedó el saldo, para que el POS lo diga y
    el recibo lo imprima."""
    entries: List[LedgerEntryResponse]
    customer_balance_before: Decimal
    customer_balance_after: Decimal
    applied: List[AbonoAplicado]
    unapplied: Decimal          # saldo a favor que quedó sin ticket
    payment_id: str             # UUID del Payment
    method: str
    reference: Optional[str] = None
    received_at: datetime

# --- LECTURA (RESPONSE) ---
class CustomerRead(CustomerBase):
    id: int
    current_balance: Decimal = Decimal("0.00") # Saldo actual calculado
    created_at: Optional[datetime] = None
    portal_active: bool = False # Campo calculado (no en DB de Customer)

    class Config:
        from_attributes = True