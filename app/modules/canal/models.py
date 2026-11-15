"""Modelos del canal «Tienda en línea».

Mínimo por ahora: las tareas siguientes agregan aquí sus tablas. La galería de
imágenes (`ProductImage`) vive en `app/modules/products/imagenes.py` y se
re-exporta para que `create_all` la vea al importar este paquete.
"""
from app.modules.products.imagenes import ProductImage  # noqa: F401

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String

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
