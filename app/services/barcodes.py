"""Códigos de barras internos por variante (talla/color).

Formato EAN-13 de uso interno: ``2`` + organización (3 dígitos) + secuencia
(8 dígitos) + dígito verificador. El prefijo GS1 "20–29" está reservado para
códigos de tienda, así que ningún fabricante emite uno igual y cualquier
escáner lo lee como un EAN-13 normal (el POS ya busca por código exacto).

Reglas duras:
  * Un código NUNCA se sobrescribe: solo se asigna cuando está vacío. Los EAN
    reales importados se conservan.
  * La unicidad es POR ORGANIZACIÓN, no global: dos tiendas distintas pueden
    vender el mismo producto de fábrica. Toda consulta hace `join(Product)`
    para acotar por `organization_id`.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.models import Product, ProductVariant

LARGO_TOTAL = 13
LARGO_SECUENCIA = 8
SECUENCIA_MAX = 10 ** LARGO_SECUENCIA - 1


def ean13_check_digit(d12: str) -> str:
    """Dígito verificador de un EAN-13 a partir de sus 12 primeros dígitos.

    Pesos 1-3 alternados de derecha a izquierda (el último dígito de `d12`
    pesa 3) y complemento a la decena superior.
    """
    if len(d12) != 12 or not d12.isdigit():
        raise ValueError("ean13_check_digit espera exactamente 12 dígitos")
    suma = 0
    for i, ch in enumerate(reversed(d12)):
        suma += int(ch) * (3 if i % 2 == 0 else 1)
    return str((10 - suma % 10) % 10)


def prefijo_org(org_id: int) -> str:
    """``2`` + los 3 dígitos de la organización.

    Con más de 999 organizaciones el prefijo se recicla (módulo 1000): no
    rompe nada porque la unicidad se valida dentro de la org, no entre orgs.
    """
    return f"2{org_id % 1000:03d}"


def es_codigo_interno(org_id: int, code: Optional[str]) -> bool:
    """¿`code` es un código generado por nosotros para esta organización?"""
    if not code or len(code) != LARGO_TOTAL or not code.isdigit():
        return False
    return code.startswith(prefijo_org(org_id))


def barcode_en_uso(db: Session, org_id: int, barcode: str,
                   excepto_id: Optional[str] = None) -> bool:
    """¿Alguna variante VIVA de la org ya tiene este código?"""
    q = (
        db.query(ProductVariant.id)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            ProductVariant.barcode == barcode,
            ProductVariant.deleted_at.is_(None),
        )
    )
    if excepto_id:
        q = q.filter(ProductVariant.id != excepto_id)
    return db.query(q.exists()).scalar()


def _max_secuencia(db: Session, org_id: int) -> int:
    """Mayor secuencia ya emitida para la org (0 si no hay ninguna).

    Cuenta también las variantes retiradas (soft-delete): la secuencia debe
    ser monótona o se reemitiría un código que sigue impreso en una etiqueta.
    """
    prefijo = prefijo_org(org_id)
    q = (
        db.query(func.max(ProductVariant.barcode))
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            ProductVariant.barcode.like(f"{prefijo}%"),
            func.length(ProductVariant.barcode) == LARGO_TOTAL,
        )
    )
    # "Todo dígitos": Postgres con regex, SQLite (tests) con GLOB — junto al
    # filtro de longitud, 13 clases [0-9] es una comparación exacta.
    dialecto = db.bind.dialect.name if db.bind is not None else ""
    if dialecto == "postgresql":
        q = q.filter(ProductVariant.barcode.op("~")("^[0-9]+$"))
    else:
        q = q.filter(ProductVariant.barcode.op("GLOB")("[0-9]" * LARGO_TOTAL))

    maximo = q.scalar()
    if not maximo:
        return 0
    try:
        return int(maximo[len(prefijo):len(prefijo) + LARGO_SECUENCIA])
    except ValueError:   # pragma: no cover — el filtro de arriba ya lo impide
        return 0


def siguiente_codigo_interno(db: Session, org_id: int) -> str:
    """Siguiente EAN-13 interno libre de la organización.

    Mismo patrón que `app/utils/folios.py`: `MAX(...)+1` es un read-then-write
    y dos altas simultáneas leerían el mismo máximo, así que en Postgres se
    serializa con un advisory lock transaccional por organización. En SQLite
    (tests) las escrituras ya están serializadas y se omite.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:org, hashtext('barcode'))"),
            {"org": org_id},
        )

    prefijo = prefijo_org(org_id)
    secuencia = _max_secuencia(db, org_id) + 1
    while secuencia <= SECUENCIA_MAX:
        base = f"{prefijo}{secuencia:0{LARGO_SECUENCIA}d}"
        codigo = base + ean13_check_digit(base)
        # El MAX solo mira códigos internos: un EAN de fábrica podría estar
        # ocupando justo este número. Se avanza hasta uno libre.
        if not barcode_en_uso(db, org_id, codigo):
            return codigo
        secuencia += 1
    raise RuntimeError(
        f"La organización {org_id} agotó la secuencia de códigos internos."
    )


def _variantes_sin_codigo(db: Session, org_id: int,
                          product_id: Optional[str] = None) -> List[ProductVariant]:
    q = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
            or_(ProductVariant.barcode.is_(None), ProductVariant.barcode == ""),
        )
    )
    if product_id:
        q = q.filter(ProductVariant.product_id == product_id)
    return q.order_by(ProductVariant.created_at, ProductVariant.id).all()


def asignar_codigos_faltantes(db: Session, org_id: int,
                              product_id: Optional[str] = None) -> int:
    """Rellena el código de las variantes vivas que no tienen.

    Hace `flush` por variante (para que el `MAX` de la siguiente vea a la
    anterior) pero NO hace commit: lo confirma el caller.
    """
    asignadas = 0
    for v in _variantes_sin_codigo(db, org_id, product_id):
        v.barcode = siguiente_codigo_interno(db, org_id)
        db.flush()
        asignadas += 1
    return asignadas


def contar_codigos_faltantes(db: Session, org_id: int,
                             product_ids: Optional[List[str]] = None) -> int:
    """Cuántas variantes vivas siguen sin código (opcionalmente acotado a
    una lista de productos — los visibles para el usuario)."""
    q = (
        db.query(func.count(ProductVariant.id))
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
            or_(ProductVariant.barcode.is_(None), ProductVariant.barcode == ""),
        )
    )
    if product_ids is not None:
        if not product_ids:
            return 0
        q = q.filter(ProductVariant.product_id.in_(product_ids))
    return q.scalar() or 0
