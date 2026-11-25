"""Atlas BOS modules/customers/models — Customer + CustomerLedgerEntry.

DOMAIN: Customer Relationship Management
STATUS: Stable

Phase 2 / S2: moved from app/models/crm.py. The legacy path is now a
reverse-shim that re-exports from here.
"""
from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey, DateTime, Date, Enum, JSON
import enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.mixins import TenantMixin

class Customer(Base, TenantMixin):
    __tablename__ = "customers"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    
    # Datos Fiscales (Agregados para que init_db funcione)
    tax_id = Column(String, index=True, nullable=True) # RFC
    tax_system = Column(String, nullable=True)         # Régimen Fiscal
    zip_code = Column(String, nullable=True)           # CP
    
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    
    is_active = Column(Boolean, default=True)

    # --- CRM (2026-11-24) ---
    # MENUDEO (cliente de mostrador) | MAYOREO (compra por volumen / a crédito).
    tipo = Column(String, nullable=False, default="MENUDEO", server_default="MENUDEO")
    birthday = Column(Date, nullable=True)
    company = Column(String, nullable=True)      # negocio o razón social (mayoreo)
    # Valores de los campos propios de la tienda: {clave del campo: valor}.
    campos = Column(JSON, nullable=True)

    # --- Campos de Crédito ---
    has_credit = Column(Boolean, default=False)
    credit_limit = Column(Numeric(10, 2), default=0.00)
    credit_days = Column(Integer, default=0)
    current_balance = Column(Numeric(10, 2), default=0.00) # Cuánto nos debe
    
    # Blockchain / Loyalty / Gamification
    blockchain_id = Column(String, nullable=True, index=True) # Wallet Address
    cashback_balance = Column(Numeric(10, 2), default=0.00)
    loyalty_tier = Column(String, default="STANDARD") # STANDARD, GOLD, PLATINUM (Using String for flexibility or Enum if strict)
    referral_code = Column(String, unique=True, nullable=True)
    profile_picture = Column(String, nullable=True) # URL
    preferences = Column(JSON, nullable=True) # { "theme": "dark", "notifications": true }
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relación con sus movimientos financieros
    ledger_entries = relationship("CustomerLedgerEntry", back_populates="customer")

class CustomerLedgerEntry(Base, TenantMixin):
    """
    Bitácora financiera del cliente (Kardex de dinero).
    Positivo (+) = Deuda aumenta (Venta a crédito)
    Negativo (-) = Deuda baja (Pago/Abono)
    """
    __tablename__ = "customer_ledger_entries"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    sales_document_id = Column(String(36), ForeignKey("sales_documents.id"), nullable=True)
    
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    customer = relationship("Customer", back_populates="ledger_entries")


class CustomerFieldDef(Base, TenantMixin):
    """Campo propio de la tienda para la ficha del cliente (tope
    `MAX_CAMPOS_PROPIOS` activos). El valor vive en `customers.campos[key]`."""
    __tablename__ = "customer_field_defs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(40), nullable=False)
    label = Column(String(60), nullable=False)
    tipo = Column(String(12), nullable=False, default="TEXTO")   # TEXTO | NUMERO | FECHA | LISTA | SI_NO
    opciones = Column(JSON, nullable=True)                       # solo LISTA
    orden = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomerFollowUp(Base, TenantMixin):
    """Seguimiento de un cliente: una tarea con fecha (llamar, avisar que llegó
    mercancía, cobrar) que alguien del equipo marca como hecha."""
    __tablename__ = "customer_followups"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    tipo = Column(String(12), nullable=False, default="LLAMADA")  # LLAMADA | WHATSAPP | VISITA | COBRANZA | OTRO
    nota = Column(String(300), nullable=True)
    due_date = Column(Date, nullable=False, index=True)
    status = Column(String(12), nullable=False, default="PENDIENTE")  # PENDIENTE | HECHO
    resultado = Column(String(300), nullable=True)
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    done_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    done_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer")
