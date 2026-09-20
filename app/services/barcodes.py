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

from sqlalchemy import func, text
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


class AsignadorDeCodigos:
    """Emite códigos internos consecutivos dentro de UNA transacción.

    El `MAX(barcode) LIKE '2xxx%'` es un recorrido de tabla (el índice btree no
    sirve para un LIKE con la colación del servidor), así que hacerlo por cada
    variante convierte una asignación masiva de 15 mil tallas en 15 mil
    recorridos. Este objeto lo lee UNA vez y luego lleva el contador en
    memoria; cada candidato se sigue verificando contra `barcode_en_uso` por si
    un EAN de fábrica ocupa justo ese número.

    Úsalo cuando un mismo request vaya a emitir varios códigos (asignación
    masiva, importación por lotes). Para un solo código está
    `siguiente_codigo_interno`.
    """

    def __init__(self, db: Session, org_id: int):
        self._db = db
        self._org_id = org_id
        self._prefijo = prefijo_org(org_id)
        self._secuencia: Optional[int] = None

    def _tomar_lock(self) -> None:
        """Advisory lock por organización (mismo patrón que `utils/folios.py`).

        Se vuelve a pedir en cada código y no una sola vez: es transaccional, y
        la importación hace `commit` cada 50 filas — tras ese commit el lock
        ya no es nuestro. Pedirlo de nuevo cuesta microsegundos (no toca la
        tabla) y es no-op si ya lo tenemos en esta transacción. En SQLite
        (tests) las escrituras ya están serializadas y se omite.
        """
        if self._db.bind is not None and self._db.bind.dialect.name == "postgresql":
            self._db.execute(
                text("SELECT pg_advisory_xact_lock(:org, hashtext('barcode'))"),
                {"org": self._org_id},
            )

    def siguiente(self) -> str:
        self._tomar_lock()
        if self._secuencia is None:
            self._secuencia = _max_secuencia(self._db, self._org_id)
        while self._secuencia < SECUENCIA_MAX:
            self._secuencia += 1
            base = f"{self._prefijo}{self._secuencia:0{LARGO_SECUENCIA}d}"
            codigo = base + ean13_check_digit(base)
            # El MAX solo mira códigos internos: un EAN de fábrica podría estar
            # ocupando justo este número. Se avanza hasta uno libre.
            if not barcode_en_uso(self._db, self._org_id, codigo):
                return codigo
        raise RuntimeError(
            f"La organización {self._org_id} agotó la secuencia de códigos internos."
        )


def siguiente_codigo_interno(db: Session, org_id: int) -> str:
    """Siguiente EAN-13 interno libre de la organización (un solo código)."""
    return AsignadorDeCodigos(db, org_id).siguiente()


def _sin_codigo():
    """Predicado "esta variante no tiene código".

    `TRIM(COALESCE(...))` y no `IS NULL OR = ''`: en producción hay códigos
    heredados que son solo espacios y no se veían como faltantes, así que
    nadie les generaba uno y la etiqueta salía en blanco.
    """
    return func.trim(func.coalesce(ProductVariant.barcode, "")) == ""


def _variantes_sin_codigo(db: Session, org_id: int,
                          product_id: Optional[str] = None) -> List[ProductVariant]:
    q = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
            _sin_codigo(),
        )
    )
    if product_id:
        q = q.filter(ProductVariant.product_id == product_id)
    return q.order_by(ProductVariant.created_at, ProductVariant.id).all()


def asignar_codigos_faltantes(db: Session, org_id: int,
                              product_id: Optional[str] = None) -> int:
    """Rellena el código de las variantes vivas que no tienen.

    Un solo `AsignadorDeCodigos` para todo el lote: el `MAX` se lee una vez y
    el contador avanza en memoria. Hace `flush` por variante (para que el
    chequeo de duplicados vea lo ya escrito) pero NO hace commit: lo confirma
    el caller.
    """
    asignador = AsignadorDeCodigos(db, org_id)
    asignadas = 0
    for v in _variantes_sin_codigo(db, org_id, product_id):
        v.barcode = asignador.siguiente()
        db.flush()
        asignadas += 1
    return asignadas


def contar_codigos_faltantes(db: Session, org_id: int, product_ids=None) -> int:
    """Cuántas variantes vivas siguen sin código.

    `product_ids` acota a los productos visibles del usuario: acepta una lista
    o —preferible— un `SELECT` de ids para que el filtro viaje como subconsulta
    en vez de materializar un `IN (…)` con el catálogo entero.
    """
    q = (
        db.query(func.count(ProductVariant.id))
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
            _sin_codigo(),
        )
    )
    if product_ids is not None:
        if isinstance(product_ids, (list, tuple, set)):
            if not product_ids:
                return 0
            product_ids = list(product_ids)
        q = q.filter(ProductVariant.product_id.in_(product_ids))
    return q.scalar() or 0
