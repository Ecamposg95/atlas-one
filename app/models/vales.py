"""Vale de tienda (2026-11-24): saldo a favor que la tienda entrega en vez de
dinero al devolver, y que se cobra después en cualquier sucursal de la misma
organización. El saldo vive en `store_vouchers.balance`; cada emisión, uso,
restitución o cancelación deja una fila en `store_voucher_movements`."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.mixins import TenantMixin, UUIDMixin

VALE_ACTIVO = "ACTIVO"
VALE_AGOTADO = "AGOTADO"
VALE_CANCELADO = "CANCELADO"

MOV_EMISION = "EMISION"
MOV_USO = "USO"
MOV_RESTITUCION = "RESTITUCION"   # se canceló la venta que lo había usado
MOV_CANCELACION = "CANCELACION"


class StoreVoucher(Base, UUIDMixin, TenantMixin):
    __tablename__ = "store_vouchers"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_store_voucher_org_code"),)

    code = Column(String(16), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)      # sucursal que lo emitió
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    customer_name = Column(String(255), nullable=True)
    initial_amount = Column(Numeric(10, 2), nullable=False)
    balance = Column(Numeric(10, 2), nullable=False)
    status = Column(String(12), nullable=False, default=VALE_ACTIVO)
    return_id = Column(String(36), ForeignKey("sale_returns.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    movements = relationship("StoreVoucherMovement", back_populates="voucher",
                             order_by="StoreVoucherMovement.created_at")


class StoreVoucherMovement(Base, UUIDMixin, TenantMixin):
    __tablename__ = "store_voucher_movements"

    voucher_id = Column(String(36), ForeignKey("store_vouchers.id"), nullable=False, index=True)
    kind = Column(String(12), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)          # siempre positivo; `kind` da el signo
    sales_document_id = Column(String(36), ForeignKey("sales_documents.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    voucher = relationship("StoreVoucher", back_populates="movements")
