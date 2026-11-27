"""Filtros avanzados del catálogo: género, talla, color, existencia y fecha de alta.

Los mismos ejes que la pantalla de Etiquetas, pero aplicados EN EL SERVIDOR:
la lista de Productos es paginada, así que filtrar en pantalla solo vería la
página cargada. Un solo lugar para que la lista (`GET /api/products/`), sus
cifras (`/stats/catalog-kpis`) y el Excel (`/export/excel`) cuenten lo mismo.

Todo va con subconsultas correlacionadas (EXISTS / SUM) sobre ALIAS de
`ProductVariant` y `StockOnHand`: la query de `query_visible_products` ya puede
traer `ProductVariant` unida (búsqueda, roles de sucursal) y un join más
multiplicaría filas o se confundiría con esa tabla. Cada subconsulta filtra
`organization_id` aunque el producto ya venga acotado a la org.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Query, Session, aliased

from app.models import Product, ProductVariant, StockOnHand
from app.modules.products.sale_name import normalizar_genero


def _texto(valor: Optional[str]) -> str:
    return (valor or "").strip()


def genero_valido(valor: Optional[str]) -> Optional[str]:
    """`gender` del query string a su clave (HOMBRE|MUJER|UNISEX|NINO); 422 si no es una."""
    try:
        return normalizar_genero(valor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"gender {exc}")


def en_utc(valor: Optional[datetime]) -> Optional[datetime]:
    """Fecha del filtro en UTC con zona. Sin zona se toma como UTC (así llega
    `created_at` de SQLite); con zona se convierte. Postgres compara con zona."""
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def aplicar_filtros_avanzados(
    q: Query,
    org_id: int,
    *,
    gender: Optional[str] = None,
    size: Optional[str] = None,
    color: Optional[str] = None,
    only_with_stock: bool = False,
    created_after: Optional[datetime] = None,
    stock_branch_id: Optional[int] = None,
) -> Query:
    """Añade los filtros avanzados a una `Query[Product]`.

    - `gender`: igualdad con `products.gender` (se normaliza: "niño" → NINO).
    - `size` / `color`: el producto tiene AL MENOS una variante viva con esa
      talla / ese color (sin distinguir mayúsculas ni espacios de los bordes).
      Con los dos puestos, la MISMA variante debe cumplir ambos: "M negra" no
      es "una M blanca y una G negra".
    - `only_with_stock`: la suma de existencias de sus variantes vivas en el
      alcance es > 0. Alcance = `stock_branch_id` (la sucursal cuya existencia
      pinta la lista); sin sucursal, la organización entera.
    - `created_after`: el producto o alguna de sus variantes vivas se dio de
      alta desde esa fecha (una talla nueva de una prenda vieja también es
      "alta", igual que en Etiquetas).
    """
    genero = genero_valido(gender)
    if genero:
        q = q.filter(Product.gender == genero)

    talla = _texto(size).lower()
    tono = _texto(color).lower()
    if talla or tono:
        v = aliased(ProductVariant)
        condiciones = [
            v.product_id == Product.id,
            v.organization_id == org_id,
            v.deleted_at.is_(None),
        ]
        if talla:
            condiciones.append(func.lower(func.trim(v.size)) == talla)
        if tono:
            condiciones.append(func.lower(func.trim(v.color)) == tono)
        q = q.filter(exists().where(and_(*condiciones)))

    if only_with_stock:
        v = aliased(ProductVariant)
        s = aliased(StockOnHand)
        suma = (
            select(func.coalesce(func.sum(s.qty_on_hand), 0))
            .join(v, v.id == s.variant_id)
            .where(
                v.product_id == Product.id,
                v.deleted_at.is_(None),
                s.organization_id == org_id,
            )
        )
        if stock_branch_id:
            suma = suma.where(s.branch_id == stock_branch_id)
        q = q.filter(suma.scalar_subquery() > 0)

    desde = en_utc(created_after)
    if desde is not None:
        v = aliased(ProductVariant)
        talla_nueva = exists().where(and_(
            v.product_id == Product.id,
            v.organization_id == org_id,
            v.deleted_at.is_(None),
            v.created_at >= desde,
        ))
        q = q.filter(or_(Product.created_at >= desde, talla_nueva))

    return q


# Escala de letras como la cuelga la tienda (la misma de Etiquetas, `lote.ts`).
_ESCALA_LETRAS = ["XXS", "XS", "CH", "S", "M", "G", "L", "XL", "XG", "2XL", "XXL", "3XL", "4XL", "5XL"]


def _orden_talla(talla: str):
    k = talla.strip().upper()
    if k in _ESCALA_LETRAS:
        return (0, _ESCALA_LETRAS.index(k), k)
    try:
        return (1, float(k.replace(",", ".")), k)
    except ValueError:
        return (2, 0, k)


def _unicos(valores) -> List[str]:
    """Cada valor una sola vez sin distinguir mayúsculas; gana la primera grafía."""
    vistos: Dict[str, str] = {}
    for crudo in valores:
        limpio = _texto(crudo)
        if limpio and limpio.lower() not in vistos:
            vistos[limpio.lower()] = limpio
    return list(vistos.values())


def facetas(db: Session, org_id: int, product_ids_subq) -> Dict[str, List[str]]:
    """Tallas y colores capturados en las variantes vivas de los productos dados.

    `product_ids_subq` es el `SELECT Product.id` visible para quien pregunta;
    además se filtra `organization_id` en la variante (multi-tenancy).
    """
    filas = (
        db.query(ProductVariant.size, ProductVariant.color)
        .filter(
            ProductVariant.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
            ProductVariant.product_id.in_(product_ids_subq),
        )
        .distinct()
        .all()
    )
    tallas = sorted(_unicos(f[0] for f in filas), key=_orden_talla)
    colores = sorted(_unicos(f[1] for f in filas), key=lambda c: c.lower())
    return {"sizes": tallas, "colors": colores}
