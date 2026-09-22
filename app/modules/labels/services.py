"""Lógica del módulo de etiquetas: qué se puede imprimir y con qué datos.

Todo lo que toca catálogo pasa por `query_visible_products`, así una cajera
solo etiqueta lo de su sucursal. La existencia se calcula con la MISMA regla
que el CSV de etiquetas (`app/modules/products/router/barcodes.py`): un
admin/dueño suma la organización entera, el resto solo su sucursal.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.crud.products import _is_admin, query_visible_products
from app.models import Product, ProductVariant, StockOnHand, User
from app.modules.labels.schemas import MAX_COPIAS
from app.modules.products.sale_name import sale_name, variant_sale_name
from app.services.labels import DatosEtiqueta, detect

# Motivos por los que una variante no se puede imprimir. Viajan tal cual a la
# tabla y al resumen de confirmación, así que están en español y son accionables.
SIN_CODIGO = "Sin código de barras"
CODIGO_INVALIDO = "El código de barras no se puede imprimir"
NO_VISIBLE = "No disponible para tu sucursal"

Par = Tuple[Product, ProductVariant]


def _texto(valor: Optional[str]) -> str:
    return (valor or "").strip()


def datos_de_variante(producto: Product, variante: ProductVariant) -> DatosEtiqueta:
    """Lo que va impreso en la etiqueta de esta variante.

    El renglón del nombre lleva prenda + modelo SIN la marca: la marca ya tiene
    su propio renglón arriba y repetirla se come el ancho útil (384 dots).
    """
    marca = producto.brand.name if producto.brand else ""
    return DatosEtiqueta(
        sku=_texto(variante.sku),
        name=sale_name(None, _texto(producto.name), producto.model),
        brand=_texto(marca),
        barcode=_texto(variante.barcode),
        price=Decimal(str(variante.price or 0)),
        size=_texto(variante.size),
        color=_texto(variante.color),
    )


def motivo_no_imprimible(datos: DatosEtiqueta) -> Optional[str]:
    """`None` si la etiqueta se puede componer; si no, el motivo en español."""
    if not datos.barcode:
        return SIN_CODIGO
    return None if detect(datos.barcode) is not None else CODIGO_INVALIDO


def existencias(
    db: Session, current_user: User, org_id: int, variant_ids: Sequence[str]
) -> Dict[str, Decimal]:
    """Existencia por variante con el alcance del usuario.

    Copiado de `exportar_etiquetas_csv`: un admin no tiene tienda propia (su
    `branch_id` es el HQ, que nunca guarda mercancía), así que para él se suma
    la organización entera — si no, todas las etiquetas saldrían en 0.
    """
    stock: Dict[str, Decimal] = {}
    ids = list(variant_ids)
    if not ids:
        return stock
    q = (
        db.query(StockOnHand.variant_id, func.sum(StockOnHand.qty_on_hand))
        .filter(
            StockOnHand.variant_id.in_(ids),
            StockOnHand.organization_id == org_id,
        )
    )
    if not _is_admin(current_user) and current_user.branch_id:
        q = q.filter(StockOnHand.branch_id == current_user.branch_id)
    for vid, total in q.group_by(StockOnHand.variant_id).all():
        stock[vid] = Decimal(str(total or 0))
    return stock


def copias_por_omision(existencia: Decimal) -> int:
    """Existencia redondeada al entero de abajo, entre 0 y `MAX_COPIAS`.

    El tope es el mismo que acepta `POST /jobs` por renglón: sugerir 150 copias
    cuando el máximo es 99 solo produciría un 422 al confirmar.
    """
    if existencia <= 0:
        return 0
    return min(int(existencia), MAX_COPIAS)


def variantes_visibles(
    db: Session,
    current_user: User,
    org_id: int,
    *,
    search: Optional[str] = None,
    product_id: Optional[str] = None,
    department_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    gender: Optional[str] = None,
) -> List[Par]:
    """Pares (producto, variante) vivos y visibles, ordenados por nombre.

    Mismo alcance que el CSV de etiquetas: el filtro de sucursal es a nivel
    PRODUCTO (`query_visible_products`), así que si un producto está activo en
    la sucursal, se listan todas sus tallas.
    """
    q = (
        query_visible_products(db, current_user, org_id, search=search)
        .options(
            joinedload(Product.variants),
            joinedload(Product.brand),
            joinedload(Product.department),
        )
        .filter(Product.deleted_at == None)  # noqa: E711
    )
    if product_id:
        q = q.filter(Product.id == product_id)
    if department_id:
        q = q.filter(Product.department_id == department_id)
    if brand_id:
        q = q.filter(Product.brand_id == brand_id)
    if gender:
        q = q.filter(Product.gender == gender)

    productos = q.order_by(Product.name).all()
    return [
        (p, v)
        for p in productos
        for v in sorted(p.variants, key=lambda x: (x.sku or ""))
        if v.deleted_at is None
    ]


def candidatos(
    db: Session,
    current_user: User,
    org_id: int,
    *,
    only_with_stock: bool = False,
    **filtros,
) -> List[dict]:
    """Filas de la tabla de etiquetas. Las no imprimibles NO se esconden: van
    marcadas con su motivo para que se note el dato a medias."""
    pares = variantes_visibles(db, current_user, org_id, **filtros)
    stock = existencias(db, current_user, org_id, [v.id for _, v in pares])

    filas: List[dict] = []
    for producto, variante in pares:
        existencia = stock.get(variante.id, Decimal(0))
        if only_with_stock and existencia <= 0:
            continue
        datos = datos_de_variante(producto, variante)
        motivo = motivo_no_imprimible(datos)
        filas.append({
            "variant_id": variante.id,
            "product_id": producto.id,
            "sku": datos.sku,
            "barcode": datos.barcode,
            "product_name": _texto(producto.name),
            "sale_name": variant_sale_name(
                producto.brand.name if producto.brand else None,
                _texto(producto.name), producto.model,
                variante.color, variante.size, variante.variant_name,
            ),
            "brand": datos.brand,
            "department": _texto(producto.department.name) if producto.department else "",
            "gender": _texto(producto.gender),
            "size": datos.size,
            "color": datos.color,
            "price": float(variante.price or 0),
            "stock": float(existencia),
            "copies_default": copias_por_omision(existencia),
            "printable": motivo is None,
            "reason": motivo,
        })
    return filas


def resolver_variantes(
    db: Session, current_user: User, org_id: int, variant_ids: Sequence[str]
) -> Dict[str, Par]:
    """Las variantes de `variant_ids` que este usuario puede ver, por id.

    Lo que no salga del diccionario es de otra organización, de otra sucursal o
    ya no existe: el caller lo reporta en `skipped`, nunca lo imprime.
    """
    ids = [v for v in variant_ids if v]
    if not ids:
        return {}
    visibles = (
        query_visible_products(db, current_user, org_id)
        .with_entities(Product.id)
        .scalar_subquery()
    )
    filas = (
        db.query(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .options(joinedload(Product.brand))
        .filter(
            ProductVariant.id.in_(ids),
            ProductVariant.organization_id == org_id,
            ProductVariant.deleted_at == None,  # noqa: E711
            Product.deleted_at == None,  # noqa: E711
            Product.id.in_(visibles),
        )
        .all()
    )
    return {variante.id: (producto, variante) for variante, producto in filas}
