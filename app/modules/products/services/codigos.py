"""SKU y código de barras: unicidad por organización y código interno.

Una sola regla de SKU para alta, edición, duplicado, variantes e importación:
se compara SIN distinguir mayúsculas y cuenta también los productos archivados
(soft-delete), para que restaurar un producto nunca choque con uno creado
después con el mismo SKU (mega plan 2026-10, §6.3). Antes había cuatro
consultas distintas: exacta (alta, upload), exacta con 400 (edición) y sin
mayúsculas pero solo vivas (variantes).

Toda consulta hace `join(Product)` y filtra `Product.organization_id`: las
filas viejas de `product_variants` pueden traer `organization_id` NULL.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Product, ProductVariant
from app.services.barcodes import AsignadorDeCodigos, barcode_en_uso, siguiente_codigo_interno


def _variante_con_sku(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None):
    """Primera variante de la org (viva o archivada) con ese SKU, o None."""
    q = (
        db.query(
            ProductVariant.id.label("id"),
            ProductVariant.deleted_at.label("variante_borrada"),
            Product.deleted_at.label("producto_borrado"),
        )
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            func.lower(ProductVariant.sku) == sku.strip().lower(),
        )
    )
    if excepto_id:
        q = q.filter(ProductVariant.id != excepto_id)
    return q.first()


def sku_en_uso(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None) -> bool:
    """¿Alguna variante de la org (viva o archivada) ya usa este SKU?"""
    return _variante_con_sku(db, org_id, sku, excepto_id) is not None


def validar_sku_unico(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None) -> str:
    """Devuelve el SKU recortado o levanta 422 (vacío) / 409 (repetido).

    El mensaje vivo es exactamente el que ya mostraba el alta; cuando el choque
    es con un producto archivado se agrega qué hacer, porque desde la pantalla
    ese producto no se ve y el usuario no entiende "ya existe".
    """
    limpio = (sku or "").strip()
    if not limpio:
        raise HTTPException(status_code=422, detail="El SKU no puede quedar vacío")
    fila = _variante_con_sku(db, org_id, limpio, excepto_id)
    if fila is None:
        return limpio
    archivado = fila.variante_borrada is not None or fila.producto_borrado is not None
    sufijo = " (está en un producto archivado: restáuralo o usa otro SKU)" if archivado else ""
    raise HTTPException(
        status_code=409,
        detail=f"El SKU '{limpio}' ya existe en esta organización.{sufijo}",
    )


def sku_de_copia(db: Session, org_id: int, base_sku: str) -> str:
    """`<base>-COPY-<n>` con el primer `n` libre en la org (archivados incluidos)."""
    base = (base_sku or "").strip() or "SKU"
    for n in range(1, 100):
        candidato = f"{base}-COPY-{n}"
        if not sku_en_uso(db, org_id, candidato):
            return candidato
    return f"{base}-COPY-{uuid.uuid4().hex[:6]}"


def validar_barcode_libre(
    db: Session, org_id: int, barcode: Optional[str], excepto_id: Optional[str] = None,
) -> Optional[str]:
    """Código recortado (o None si viene vacío); 409 si ya lo tiene otra variante viva."""
    limpio = (barcode or "").strip() or None
    if limpio and barcode_en_uso(db, org_id, limpio, excepto_id=excepto_id):
        raise HTTPException(
            status_code=409,
            detail=f"El código de barras '{limpio}' ya lo tiene otra variante.",
        )
    return limpio


def asignar_barcode_interno(
    db: Session, org_id: int, variante: ProductVariant,
    asignador: Optional[AsignadorDeCodigos] = None,
) -> str:
    """Si la variante no trae código, le genera el EAN-13 interno de la org.

    Un código NUNCA se sobrescribe. `asignador`: la importación pasa el suyo
    (uno por request) para no releer el MAX del catálogo en cada fila. Hace
    `flush` para que la siguiente variante del mismo request vea el código y
    no repita la secuencia.
    """
    if (variante.barcode or "").strip():
        return variante.barcode
    variante.barcode = asignador.siguiente() if asignador is not None else siguiente_codigo_interno(db, org_id)
    db.flush()
    return variante.barcode
