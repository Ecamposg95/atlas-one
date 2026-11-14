"""Galería de imágenes del producto (tienda web) y su relleno inicial.

`products.image_url` queda como está (es lo que usan POS y listados); la
galería nace de ahí: cada producto con `image_url` y sin galería recibe una
imagen primaria.
"""
import uuid
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Index, text
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models.mixins import UUIDMixin, AuditMixin, TenantMixin


class ProductImage(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "product_images"
    __table_args__ = (
        Index("ix_product_images_product", "product_id", "position"),
        {'extend_existing': True},
    )

    # products.id es UUID -> String(36) (regla de oro 4).
    product_id = Column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    url = Column(String, nullable=False)
    alt = Column(String, nullable=True)
    position = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)


# Mismo SQL en Postgres y SQLite. El id lo genera Python (no hay uuid en SQLite),
# por eso se inserta fila a fila los candidatos; son pocos y corre una vez.
_CANDIDATOS = """
SELECT p.id, p.organization_id, p.image_url
FROM products p
WHERE p.image_url IS NOT NULL AND p.image_url <> ''
  AND NOT EXISTS (SELECT 1 FROM product_images i WHERE i.product_id = p.id)
"""


def backfill_imagenes(db: Session) -> int:
    """Crea la imagen primaria (position 0) de cada producto con `image_url`
    y sin galería. Idempotente. Sin commit: lo hace el caller. Devuelve cuántas
    creó."""
    filas = db.execute(text(_CANDIDATOS)).fetchall()
    for pid, org_id, url in filas:
        db.add(ProductImage(
            id=str(uuid.uuid4()), organization_id=org_id, product_id=pid,
            url=url, position=0, is_primary=True,
        ))
    db.flush()
    return len(filas)
