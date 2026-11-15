"""Modelos del canal «Tienda en línea».

Mínimo por ahora: las tareas siguientes agregan aquí sus tablas. La galería de
imágenes (`ProductImage`) vive en `app/modules/products/imagenes.py` y se
re-exporta para que `create_all` la vea al importar este paquete.
"""
from app.modules.products.imagenes import ProductImage  # noqa: F401

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Index, Integer, String, Text

from app.core.database import Base


class ChannelAvailability(Base):
    """¿La variante se puede vender en la tienda web? Una fila por variante;
    sin fila = no disponible. Solo se escribe cuando el booleano cambia
    (`app/services/canal_disponibilidad.py`), así `changed_at` sirve de cursor
    para `/availability`.

    Sin llaves foráneas a propósito: el borrado duro de variantes/productos y
    el borrado forzado de una org (cascade manual) no deben tropezar con esta
    tabla derivada; una fila huérfana es inofensiva y `recalcular` la apaga.
    """
    __tablename__ = "channel_availability"
    __table_args__ = (
        Index("ix_channel_availability_org_changed", "organization_id", "changed_at"),
        {'extend_existing': True},
    )

    organization_id = Column(Integer, primary_key=True)
    # product_variants.id / products.id son UUID -> String(36) (regla de oro 4).
    variant_id = Column(String(36), primary_key=True)
    product_id = Column(String(36), nullable=False)
    available = Column(Boolean, nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False)


class ChannelProductMetric(Base):
    """Consultas anónimas por pieza y día (clics de WhatsApp, selecciones).
    No guarda datos personales. Sin FK (igual que `ChannelAvailability`)."""
    __tablename__ = "channel_product_metrics"
    __table_args__ = {'extend_existing': True}

    organization_id = Column(Integer, primary_key=True)
    product_id = Column(String(36), primary_key=True)
    day = Column(Date, primary_key=True)          # día de México de occurred_at
    source = Column(String(30), primary_key=True)
    count = Column(Integer, nullable=False, default=0)


class ChannelLead(Base):
    """Prospecto de la tienda web: solo existe si dejó teléfono."""
    __tablename__ = "channel_leads"
    __table_args__ = (
        Index("ix_channel_leads_org_occurred", "organization_id", "occurred_at"),
        {'extend_existing': True},
    )

    id = Column(String(36), primary_key=True)
    organization_id = Column(Integer, nullable=False)
    source = Column(String(30), nullable=False)
    line = Column(String(20), nullable=True)
    name = Column(String, nullable=True)
    phone = Column(String(10), nullable=False)    # normalizado a 10 dígitos
    email = Column(String, nullable=True)
    utm = Column(JSON, nullable=True)
    product_ids = Column(JSON, nullable=True)
    customer_id = Column(Integer, nullable=True)  # customers.id (Integer)
    status = Column(String(20), nullable=False, default="nuevo")
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class ChannelIdempotency(Base):
    """Respuesta guardada por `Idempotency-Key` (se purga a los 7 días)."""
    __tablename__ = "channel_idempotency"
    __table_args__ = {'extend_existing': True}

    organization_id = Column(Integer, primary_key=True)
    key = Column(String(200), primary_key=True)
    response_json = Column(Text, nullable=False)  # {"status": int, "body": {...}}
    created_at = Column(DateTime(timezone=True), nullable=False)
