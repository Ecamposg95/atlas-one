"""Variantes de color/talla (preset boutique).

Las tiendas ATLAS_POS siguen con una variante "Estándar" por producto y nunca
llaman estos endpoints. Aqui vive todo lo que crea, edita o retira variantes;
`create_product` (core.py) delega en `crear_variantes` para `extra_variants`.
"""
from __future__ import annotations

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

from ._shared import _compute_product_read

router = APIRouter()


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
    if p is None or not p.variants:
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


def _atributos(color: Optional[str], size: Optional[str], indice: int) -> tuple[Optional[str], Optional[str]]:
    try:
        return clean_attr(color, COLOR_MAX), clean_attr(size, SIZE_MAX)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"variants[{indice}]: color/talla {e}")


def _pareja_repetida(producto: Product, color: Optional[str], size: Optional[str], excepto_id: Optional[str] = None) -> bool:
    clave = ((color or "").lower(), (size or "").lower())
    for v in producto.variants:
        if v.deleted_at is not None or v.id == excepto_id:
            continue
        if ((v.color or "").lower(), (v.size or "").lower()) == clave:
            return True
    return False


def crear_variantes(db: Session, org_id: int, producto: Product, entradas: List[ProductVariantCreate]) -> List[ProductVariant]:
    """Crea variantes hermanas de la principal. Sin commit: lo hace el caller.

    Cada variante nueva hereda precio/costo/IVA de la principal si no los trae,
    y se habilita (PBS) con existencia 0 en las mismas sucursales donde ya esta
    la principal, para que aparezca en el POS de inmediato.
    """
    principal = producto.variants[0]
    pbs_base = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == principal.id).all()
    nuevas: List[ProductVariant] = []
    vistos: set[tuple[str, str]] = set()
    for i, e in enumerate(entradas):
        color, size = _atributos(e.color, e.size, i)
        if not color and not size:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: indica color o talla")
        clave = ((color or "").lower(), (size or "").lower())
        if clave in vistos or _pareja_repetida(producto, color, size):
            raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
        vistos.add(clave)

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


def _leer(db: Session, current_user: User, producto_id: str) -> ProductRead:
    p = db.query(Product).filter(Product.id == producto_id).first()
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
    if not body.variants:
        raise HTTPException(status_code=422, detail="Manda al menos una variante")
    producto = _producto_de_la_org(db, org_id, product_id)
    # Si `crear_variantes` revienta a medio lote, no hacemos rollback explicito
    # aqui: no hubo commit todavia, asi que no hay nada que confirmar, y el
    # teardown de `get_db` (finally: db.close()) descarta lo pendiente al
    # cerrar la sesion de la request.
    crear_variantes(db, org_id, producto, body.variants)
    db.commit()
    return _leer(db, current_user, product_id)


@router.put("/variants/{variant_id}", response_model=ProductRead,
            dependencies=[Depends(require_module("variants"))])
def editar_variante(
    variant_id: str,
    body: ProductVariantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    v = _variante_de_la_org(db, org_id, variant_id)
    enviados = body.model_dump(exclude_unset=True)
    color = clean_attr(body.color, COLOR_MAX) if "color" in enviados else v.color
    size = clean_attr(body.size, SIZE_MAX) if "size" in enviados else v.size
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
    return _leer(db, current_user, v.product_id)


@router.delete("/variants/{variant_id}", status_code=204,
               dependencies=[Depends(require_module("variants"))])
def retirar_variante(
    variant_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
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
    db.commit()
    return Response(status_code=204)
