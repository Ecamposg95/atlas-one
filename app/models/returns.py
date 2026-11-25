from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.mixins import UUIDMixin, AuditMixin, TenantMixin
from app.models.sales import PaymentMethod

class SaleReturn(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "sale_returns"

    sale_id = Column(String(36), ForeignKey("sales_documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # User who processed the return
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    cash_session_id = Column(Integer, ForeignKey("cash_sessions.id"), nullable=True) 
    
    total_refunded = Column(Numeric(10, 2), nullable=False)
    refund_method = Column(Enum(PaymentMethod), default=PaymentMethod.CASH)
    reason = Column(String, nullable=False) # Ej: Defectuoso, Error de cliente
    status = Column(String, default="PENDING") # PENDING, APPROVED, REJECTED
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=True) # If authorized by supervisor
    # Motivo de catálogo (`app/services/devoluciones.py::MOTIVOS`); `reason` guarda
    # el texto que se imprime. NULL en devoluciones anteriores al 2026-11-24.
    reason_code = Column(String, nullable=True)
    # Cómo se autorizó: POLITICA (la caja, dentro del monto libre de la tienda),
    # PIN (un gerente tecleó su PIN en la caja) o SUPERVISOR (aprobada después).
    autorizacion = Column(String, nullable=True)
    
    # Relaciones
    sale = relationship("SalesDocument")
    user = relationship("User", foreign_keys=[user_id])
    supervisor = relationship("User", foreign_keys=[supervisor_id])
    branch = relationship("Branch")
    cash_session = relationship("CashSession")
    items = relationship("SaleReturnItem", back_populates="parent_return", cascade="all, delete-orphan")

class SaleReturnItem(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "sale_return_items"

    return_id = Column(String(36), ForeignKey("sale_returns.id"), nullable=False)
    variant_id = Column(String(36), ForeignKey("product_variants.id"), nullable=False)
    
    quantity = Column(Numeric(10, 2), nullable=False)
    refund_amount = Column(Numeric(10, 2), nullable=False)
    
    # Control de inventario
    is_inventory_reentry = Column(Boolean, default=True) # True = vuelve a stock, False = Merma/Garantía

    parent_return = relationship("SaleReturn", back_populates="items")
    variant = relationship("ProductVariant")