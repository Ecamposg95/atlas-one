"""Variantes de color/talla (preset boutique).

Las tiendas ATLAS_POS siguen con una variante "Estándar" por producto y nunca
llaman estos endpoints. Aqui vive todo lo que crea, edita o retira variantes;
`create_product` (core.py) delega en `crear_variantes` para `extra_variants`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import Product, ProductBranchStatus, ProductVariant, StockOnHand, User
from app.models.sales import SalesLineItem
from app.modules.products.schemas import (
    ProductRead, ProductVariantUpdate, VariantBatchCreate,
)
from app.modules.products.services.codigos import sku_en_uso as _sku_en_uso, validar_barcode_libre
from app.modules.products.services.variantes import (  # noqa: F401  (re-export para core/import_export)
    atributos as _atributos,
    crear_variantes,
    pareja_repetida as _pareja_repetida,
)
from app.modules.products.variant_label import variant_label

from ._shared import _PRODUCT_ADVANCED_ROLES, _compute_product_read

logger = logging.getLogger(__name__)

router = APIRouter()


def _exigir_rol_avanzado(current_user: User, accion: str) -> None:
    """`require_module("variants")` solo comprueba que la org tenga el modulo.
    El CRUD de variantes toca precio, SKU y disponibilidad, asi que ademas pide
    el mismo rol que `delete_product` (ADMINISTRADOR/GERENTE/DUENO/CAJERO)."""
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail=f"No autorizado para {accion}")


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
    crear_variantes(db, org_id, producto, body.variants,
                    stock_branch_id=body.branch_id, user_id=current_user.id)
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
        v.barcode = validar_barcode_libre(db, org_id, body.barcode, excepto_id=v.id)
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
