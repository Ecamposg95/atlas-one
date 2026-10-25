"""Sesiones de conteo físico y sus líneas.

Un conteo es UNA sucursal y, opcionalmente, UN departamento. Una línea por
variante por conteo (escanear la misma talla dos veces suma 1 a la misma
línea) y una línea por código desconocido. Nada de aquí toca `stock_on_hand`:
el conteo lee la existencia y la congela en `qty_sistema` al cerrar.

Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §2.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.mixins import TenantMixin

# Estado como String + constantes (CLAUDE.md §5: evitar enums de Postgres).
# ABIERTO se cuenta; CERRADO congeló su reporte; CANCELADO se descartó sin
# congelar nada (9 letras: cabe en String(10), sin migración).
ABIERTO = "ABIERTO"
CERRADO = "CERRADO"
CANCELADO = "CANCELADO"


class InventoryCount(Base, TenantMixin):
    __tablename__ = "inventory_counts"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    # NULL = toda la tienda. FK a UUID → String(36) (regla de oro #4).
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    status = Column(String(10), nullable=False, default=ABIERTO)
    notes = Column(String, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    # JSON del reporte congelado al cerrar (services.cerrar).
    resumen = Column(Text, nullable=True)
    # Fase 2: cuándo y quién aplicó por primera vez el reporte al kardex.
    aplicado_at = Column(DateTime(timezone=True), nullable=True)
    aplicado_por_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    lineas = relationship(
        "InventoryCountLine", back_populates="conteo",
        cascade="all, delete-orphan", order_by="InventoryCountLine.updated_at.desc()",
    )
    branch = relationship("Branch")
    department = relationship("Department")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    aplicado_por = relationship("User", foreign_keys=[aplicado_por_user_id])


class InventoryCountLine(Base, TenantMixin):
    __tablename__ = "inventory_count_lines"

    id = Column(Integer, primary_key=True, index=True)
    count_id = Column(Integer, ForeignKey("inventory_counts.id"), nullable=False, index=True)
    # NULL = código desconocido; entonces `codigo` trae lo escaneado.
    variant_id = Column(String(36), ForeignKey("product_variants.id"), nullable=True)
    codigo = Column(String, nullable=True)
    qty_contada = Column(Numeric(10, 2), nullable=False, default=0)
    # Existencia al CERRAR; NULL mientras el conteo está abierto.
    qty_sistema = Column(Numeric(10, 2), nullable=True)
    # La ficha del producto se corrigió desde el conteo (nombre/marca/modelo/
    # descripción): el reporte lo lista para saber qué se tocó.
    corregida = Column(Boolean, nullable=False, default=False, server_default="false")
    # Fase 2: la existencia se ajustó a esta línea (en piso o al aplicar el reporte).
    ajustada_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("count_id", "variant_id", name="uq_count_line_variant"),
        UniqueConstraint("count_id", "codigo", name="uq_count_line_codigo"),
    )

    conteo = relationship("InventoryCount", back_populates="lineas")
    variant = relationship("ProductVariant")
