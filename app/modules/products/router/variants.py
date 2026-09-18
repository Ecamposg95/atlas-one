"""Variantes de color/talla (preset boutique).

Las tiendas ATLAS_POS siguen con una variante "Estándar" por producto y nunca
llaman estos endpoints. Aqui vive todo lo que crea, edita o retira variantes;
`create_product` (core.py) delega en `crear_variantes` para `extra_variants`.
"""
from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import Product, ProductBranchStatus, ProductVariant, StockOnHand, User
from app.models.sales import SalesLineItem
from app.modules.products.schemas import (
    ProductRead, ProductVariantCreate, ProductVariantUpdate, VariantBatchCreate,
)
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr, variant_label

from ._shared import _PRODUCT_ADVANCED_ROLES, _compute_product_read

logger = logging.getLogger(__name__)

router = APIRouter()


def _exigir_rol_avanzado(current_user: User, accion: str) -> None:
    """`require_module("variants")` solo comprueba que la org tenga el modulo.
    El CRUD de variantes toca precio, SKU y disponibilidad, asi que ademas pide
    el mismo rol que `delete_product` (ADMINISTRADOR/GERENTE/DUENO/CAJERO)."""
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail=f"No autorizado para {accion}")


def _slug(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sin_acentos.upper() if c.isalnum())


def _sku_generado(base: str, color: Optional[str], size: Optional[str]) -> str:
    partes = [base] + [_slug(x) for x in (color, size) if x]
    return "-".join(partes)


def _producto_de_la_org(db: Session, org_id: int, product_id: str) -> Product:
    p = (
        db.query(Product)
        .filter(Product.id == product_id, Product.organization_id == org_id)
        .first()
    )
    if p is None or not any(v.deleted_at is None for v in p.variants):
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return p


def _variante_de_la_org(db: Session, org_id: int, variant_id: str) -> ProductVariant:
    v = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(ProductVariant.id == variant_id, Product.organization_id == org_id,
                ProductVariant.deleted_at.is_(None))
        .first()
    )
    if v is None:
        raise HTTPException(status_code=404, detail="Variante no encontrada")
    return v


def _sku_en_uso(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None) -> bool:
    q = db.query(ProductVariant).filter(
        ProductVariant.organization_id == org_id,
        func.lower(ProductVariant.sku) == sku.lower(),
        ProductVariant.deleted_at.is_(None),
    )
    if excepto_id:
        q = q.filter(ProductVariant.id != excepto_id)
    return db.query(q.exists()).scalar()


def _barcode_en_uso(db: Session, org_id: int, barcode: str, excepto_id: Optional[str] = None) -> bool:
    q = db.query(ProductVariant).filter(
        ProductVariant.organization_id == org_id,
        ProductVariant.barcode == barcode,
        ProductVariant.deleted_at.is_(None),
    )
    if excepto_id:
        q = q.filter(ProductVariant.id != excepto_id)
    return db.query(q.exists()).scalar()


def _atributos(color: Optional[str], size: Optional[str], contexto: str) -> tuple[Optional[str], Optional[str]]:
    """Limpia/valida color+talla o levanta 422 con `contexto` en el detalle
    (p. ej. "variants[0]" en el alta, "variante <id>" en la edición)."""
    try:
        return clean_attr(color, COLOR_MAX), clean_attr(size, SIZE_MAX)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"{contexto}: color/talla {e}")


def _pareja_repetida(producto: Product, color: Optional[str], size: Optional[str], excepto_id: Optional[str] = None) -> bool:
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
) -> List[ProductVariant]:
    """Crea variantes hermanas de la principal. Sin commit: lo hace el caller.

    Cada variante nueva hereda precio/costo/IVA de la principal si no los trae,
    y se habilita (PBS) con existencia 0 en las mismas sucursales donde ya esta
    la principal, para que aparezca en el POS de inmediato.

    `principal_id`: fija cual variante es la principal en vez de tomar la
    primera de `producto.variants` (orden no garantizado una vez que el
    producto ya tiene mas de una variante — p. ej. cuando el caller invoca
    esta funcion varias veces para el mismo producto, como en la carga
    masiva por fila).
    """
    if principal_id is not None:
        principal = next(v for v in producto.variants if v.id == principal_id and v.deleted_at is None)
    else:
        principal = next(v for v in producto.variants if v.deleted_at is None)
    pbs_base = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == principal.id).all()
    if not pbs_base:
        # No es un caso fatal (p. ej. un producto HQ sin PBS explicito vive
        # "visible en todas las sucursales" por el OUTER JOIN de ATS-11), pero
        # si ocurre dentro de `create_product` es casi siempre porque el PBS
        # de la principal todavia no se aplico (falta un flush aguas arriba).
        logger.warning(
            "crear_variantes: la variante principal %s no tiene ProductBranchStatus; "
            "las variantes hermanas nacen sin PBS/stock por sucursal.",
            principal.id,
        )
    nuevas: List[ProductVariant] = []
    vistos: set[tuple[str, str]] = set()
    for i, e in enumerate(entradas):
        color, size = _atributos(e.color, e.size, f"variants[{i}]")
        if not color and not size:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: indica color o talla")
        clave = ((color or "").lower(), (size or "").lower())
        if clave in vistos or _pareja_repetida(producto, color, size):
            raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
        vistos.add(clave)

        if e.price is not None and e.price <= 0:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: el precio debe ser mayor a cero.")

        sku = (e.sku or "").strip() or _sku_generado(principal.sku, color, size)
        if _sku_en_uso(db, org_id, sku):
            raise HTTPException(status_code=409, detail=f"El SKU '{sku}' ya existe en esta organización.")
        barcode = (e.barcode or "").strip() or None
        if barcode and _barcode_en_uso(db, org_id, barcode):
            raise HTTPException(status_code=409, detail=f"El código de barras '{barcode}' ya lo tiene otra variante.")

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
        for pbs in pbs_base:
            db.add(ProductBranchStatus(
                variant_id=v.id, branch_id=pbs.branch_id, organization_id=org_id,
                is_active_pos=pbs.is_active_pos, is_active_hq=pbs.is_active_hq, is_visible=pbs.is_visible,
            ))
            db.add(StockOnHand(variant_id=v.id, branch_id=pbs.branch_id, organization_id=org_id,
                               qty_on_hand=Decimal(0), is_active=True))
        nuevas.append(v)
    producto.has_variants = True
    db.flush()
    return nuevas


def _leer(db: Session, current_user: User, org_id: int, producto_id: str) -> ProductRead:
    # Multi-tenancy: el producto se relee acotado a la org (regla de oro #5),
    # no solo por su UUID.
    p = (
        db.query(Product)
        .filter(Product.id == producto_id, Product.organization_id == org_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    db.refresh(p)
    return _compute_product_read(p, db, current_user)


@router.post("/{product_id}/variants", response_model=ProductRead, status_code=201,
             dependencies=[Depends(require_module("variants"))])
def crear_variantes_endpoint(
    product_id: str,
    body: VariantBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    _exigir_rol_avanzado(current_user, "crear variantes")
    if not body.variants:
        raise HTTPException(status_code=422, detail="Manda al menos una variante")
    producto = _producto_de_la_org(db, org_id, product_id)
    # Si `crear_variantes` revienta a medio lote, no hacemos rollback explicito
    # aqui: no hubo commit todavia, asi que no hay nada que confirmar, y el
    # teardown de `get_db` (finally: db.close()) descarta lo pendiente al
    # cerrar la sesion de la request.
    crear_variantes(db, org_id, producto, body.variants)
    db.commit()
    return _leer(db, current_user, org_id, product_id)


@router.put("/variants/{variant_id}", response_model=ProductRead,
            dependencies=[Depends(require_module("variants"))])
def editar_variante(
    variant_id: str,
    body: ProductVariantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    _exigir_rol_avanzado(current_user, "editar variantes")
    v = _variante_de_la_org(db, org_id, variant_id)
    enviados = body.model_dump(exclude_unset=True)
    color_in = body.color if "color" in enviados else v.color
    size_in = body.size if "size" in enviados else v.size
    color, size = _atributos(color_in, size_in, f"variante {v.id}")
    if ("color" in enviados or "size" in enviados) and _pareja_repetida(v.product, color, size, excepto_id=v.id):
        raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
    if "sku" in enviados:
        sku = (body.sku or "").strip()
        if not sku:
            raise HTTPException(status_code=422, detail="El SKU no puede quedar vacío")
        if _sku_en_uso(db, org_id, sku, excepto_id=v.id):
            raise HTTPException(status_code=409, detail=f"El SKU '{sku}' ya existe en esta organización.")
        v.sku = sku
    if "barcode" in enviados:
        barcode = (body.barcode or "").strip() or None
        if barcode and _barcode_en_uso(db, org_id, barcode, excepto_id=v.id):
            raise HTTPException(status_code=409, detail=f"El código de barras '{barcode}' ya lo tiene otra variante.")
        v.barcode = barcode
    if body.price is not None:
        if body.price <= 0:
            raise HTTPException(status_code=422, detail="El precio debe ser mayor a cero.")
        v.price = body.price
    if body.cost is not None:
        v.cost = body.cost
    v.color, v.size = color, size
    v.variant_name = variant_label(color, size)
    db.commit()
    return _leer(db, current_user, org_id, v.product_id)


@router.delete("/variants/{variant_id}", status_code=204,
               dependencies=[Depends(require_module("variants"))])
def retirar_variante(
    variant_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    _exigir_rol_avanzado(current_user, "retirar variantes")
    v = _variante_de_la_org(db, org_id, variant_id)
    vivas = [x for x in v.product.variants if x.deleted_at is None]
    if len(vivas) <= 1:
        raise HTTPException(status_code=409, detail="Es la única variante del producto; desactiva el producto en su lugar.")
    con_stock = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id, StockOnHand.qty_on_hand > 0).first()
    if con_stock is not None:
        raise HTTPException(status_code=409, detail="La variante tiene existencia; ajústala a cero antes de retirarla.")
    if db.query(SalesLineItem).filter(SalesLineItem.variant_id == v.id).first() is not None:
        raise HTTPException(status_code=409, detail="La variante tiene ventas; no se puede retirar, solo desactivar el producto.")
    v.deleted_at = datetime.now(timezone.utc)
    # La variante retirada no debe seguir vendible ni visible en ninguna
    # sucursal: `deleted_at` la saca de ProductRead.variants, pero su PBS
    # sigue existiendo (historial) y sin esto el POS podria seguir viendola.
    for pbs in db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all():
        pbs.is_active_pos = False
        pbs.is_visible = False
    db.commit()
    return Response(status_code=204)
