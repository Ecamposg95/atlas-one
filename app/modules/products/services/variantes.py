"""Variantes de color/talla (preset boutique): creación de hermanas.

`crear_producto` delega aquí para `extra_variants`, `POST /{id}/variants` para
la matriz y la importación para las filas con Color/Talla de un producto ya
creado en la misma carga. Sin commit: lo hace el caller.
"""
from __future__ import annotations

import logging
import unicodedata
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Product, ProductBranchStatus, ProductVariant
from app.modules.products.schemas import ProductVariantCreate
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr, variant_label
from app.services.barcodes import AsignadorDeCodigos

from .codigos import asignar_barcode_interno, validar_barcode_libre, validar_sku_unico
from .sucursales import registrar_stock_inicial

logger = logging.getLogger(__name__)


def _slug(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sin_acentos.upper() if c.isalnum())


def sku_generado(base: str, color: Optional[str], size: Optional[str]) -> str:
    """`PLY` + Rojo + M -> `PLY-ROJO-M`."""
    partes = [base] + [_slug(x) for x in (color, size) if x]
    return "-".join(partes)


def atributos(color: Optional[str], size: Optional[str], contexto: str) -> tuple[Optional[str], Optional[str]]:
    """Limpia/valida color+talla o levanta 422 con `contexto` en el detalle
    (p. ej. "variants[0]" en el alta, "variante <id>" en la edición)."""
    try:
        return clean_attr(color, COLOR_MAX), clean_attr(size, SIZE_MAX)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"{contexto}: color/talla {e}")


def pareja_repetida(producto: Product, color: Optional[str], size: Optional[str],
                    excepto_id: Optional[str] = None) -> bool:
    clave = ((color or "").lower(), (size or "").lower())
    for v in producto.variants:
        if v.deleted_at is not None or v.id == excepto_id:
            continue
        if ((v.color or "").lower(), (v.size or "").lower()) == clave:
            return True
    return False


def crear_variantes(
    db: Session, org_id: int, producto: Product, entradas: List[ProductVariantCreate],
    principal_id: Optional[str] = None,
    stock_branch_id: Optional[int] = None,
    user_id: Optional[int] = None,
    asignador: Optional[AsignadorDeCodigos] = None,
) -> List[ProductVariant]:
    """Crea variantes hermanas de la principal. Sin commit: lo hace el caller.

    Cada variante nueva hereda precio/costo/IVA de la principal si no los trae,
    y se habilita (PBS) con existencia 0 en las mismas sucursales donde ya está
    la principal, para que aparezca en el POS de inmediato.

    `principal_id`: fija cuál variante es la principal en vez de tomar la
    primera de `producto.variants` (orden no garantizado una vez que el
    producto ya tiene más de una variante — p. ej. la carga masiva por fila).

    `initial_stock` de cada entrada aterriza en `stock_branch_id` (o en la
    única sucursal habilitada, si solo hay una) con su movimiento de apertura,
    igual que hace `crear_producto` con la principal. Sin `initial_stock` todo
    sigue como antes: existencia 0 y sin kardex.
    """
    if principal_id is not None:
        principal = next(v for v in producto.variants if v.id == principal_id and v.deleted_at is None)
    else:
        principal = next(v for v in producto.variants if v.deleted_at is None)
    pbs_base = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == principal.id).all()
    if not pbs_base:
        # No es un caso fatal (p. ej. un producto HQ sin PBS explícito vive
        # "visible en todas las sucursales" por el OUTER JOIN de ATS-11), pero
        # si ocurre dentro de `crear_producto` es casi siempre porque el PBS
        # de la principal todavía no se aplicó (falta un flush aguas arriba).
        logger.warning(
            "crear_variantes: la variante principal %s no tiene ProductBranchStatus; "
            "las variantes hermanas nacen sin PBS/stock por sucursal.",
            principal.id,
        )
    # Sucursal destino de la existencia inicial: la pedida, o la única
    # habilitada. Con varias sucursales y sin `branch_id` no se adivina
    # (mismo criterio que `crear_producto`, que rechaza el stock ambiguo).
    sucursales = [pbs.branch_id for pbs in pbs_base]
    destino_stock: Optional[int] = None
    if stock_branch_id is not None and stock_branch_id in sucursales:
        destino_stock = stock_branch_id
    elif stock_branch_id is None and len(sucursales) == 1:
        destino_stock = sucursales[0]

    nuevas: List[ProductVariant] = []
    vistos: set[tuple[str, str]] = set()
    for i, e in enumerate(entradas):
        color, size = atributos(e.color, e.size, f"variants[{i}]")
        if not color and not size:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: indica color o talla")
        clave = ((color or "").lower(), (size or "").lower())
        if clave in vistos or pareja_repetida(producto, color, size):
            raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
        vistos.add(clave)

        if e.price is not None and e.price <= 0:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: el precio debe ser mayor a cero.")

        qty_inicial = Decimal(e.initial_stock or 0)
        if qty_inicial < 0:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: la existencia inicial no puede ser negativa.")
        if qty_inicial > 0 and destino_stock is None:
            raise HTTPException(
                status_code=422,
                detail="Indica en qué sucursal entra la existencia inicial de las variantes.",
            )

        # Misma regla de SKU que el alta: sin mayúsculas e incluyendo archivados.
        sku = validar_sku_unico(db, org_id, (e.sku or "").strip() or sku_generado(principal.sku, color, size))
        barcode = validar_barcode_libre(db, org_id, e.barcode)

        v = ProductVariant(
            product_id=producto.id,
            sku=sku,
            barcode=barcode,
            color=color,
            size=size,
            variant_name=variant_label(color, size),
            price=e.price if e.price is not None else principal.price,
            cost=e.cost if e.cost is not None else principal.cost,
            has_iva=principal.has_iva,
            tax_rate=principal.tax_rate,
            organization_id=org_id,
        )
        db.add(v)
        db.flush()
        # Cada talla necesita su propio código o la etiquetadora no distingue
        # las piezas en el anaquel; el flush de arriba lo deja visible para la
        # siguiente vuelta, así que no se repiten entre hermanas.
        asignar_barcode_interno(db, org_id, v, asignador)
        # Hereda solo las tres banderas por sucursal de la principal (no los
        # defaults ni los precios por sucursal).
        for pbs in pbs_base:
            db.add(ProductBranchStatus(
                variant_id=v.id, branch_id=pbs.branch_id, organization_id=org_id,
                is_active_pos=pbs.is_active_pos, is_active_hq=pbs.is_active_hq, is_visible=pbs.is_visible,
            ))
        registrar_stock_inicial(db, org_id, v, sucursales, destino_stock, qty_inicial, user_id,
                                notas="Creación de variante")
        nuevas.append(v)
    producto.has_variants = True
    db.flush()
    return nuevas
