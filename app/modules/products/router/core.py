"""``/api/products`` — core product CRUD plus approval/restore/duplicate.

Endpoints (9):
    GET    /                       (list w/ filters + pagination)
    POST   /                       (create)
    GET    /{product_id}            (read single)
    PUT    /{product_id}            (update)
    DELETE /{product_id}            (soft-delete)
    POST   /{product_id}/restore    (un-archive)
    POST   /{product_id}/duplicate  (clone)
    PUT    /{product_id}/approve    (approval workflow)
    PUT    /{product_id}/reject     (approval workflow)

Sprint 5b split — extracted verbatim from the original ``products.py``.
"""
from __future__ import annotations
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.utils import image_storage
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.tenant_context import get_current_active_organization
from app.models import Product, ProductBranchStatus, ProductVariant, StockOnHand, User
from app.core.security import get_current_user
from app.crud.products import (
    query_visible_products,
    get_product_if_visible,
    _is_admin,
)
from app.modules.products.schemas import (
    ProductCreate, ProductRead, ProductUpdate, ProductListResponse,
)
from app.modules.products.sale_name import sku_sugerido
from app.modules.products.services import actualizar_producto, crear_producto, duplicar_producto

from ._shared import _PRODUCT_ADVANCED_ROLES, _compute_product_read

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=ProductListResponse)
def read_products(
    skip: int = 0,
    limit: int = 100,
    search: str = "",
    branch_id: int = None, # Optional filter
    brand_id: Optional[str] = None,
    department_id: Optional[str] = None,
    active_in_branch: bool = False, # NEW: Strict active filter
    active_only: bool = False,  # Filter: solo productos activos
    approval_status: str = None, # NEW: Filter by status
    include_inactive: bool = False,  # Admin: incluir productos desactivados
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    # include_inactive solo aplica a admins (helper lo ignora para no-admins)
    is_admin = _is_admin(current_user)

    # Drill-down por sucursal: admins pueden pasar branch_id; no-admins siempre
    # se filtran por su propia branch (helper lo fuerza).
    branch_override = None
    if is_admin and branch_id and branch_id != 0:
        branch_override = branch_id

    # Fuente única de verdad para visibilidad (policy CAJERO/GERENTE + anti-ATS-11).
    # selectinload evita:
    #   1. Producto cartesiano — contains_eager requiere JOIN explícito de variants
    #      en la query outer, pero `query_visible_products` NO joinea variants para
    #      admin sin `branch_id_override`. El JOIN implícito dejaba product_variants
    #      sin condición → cartesian product warning + resultados incorrectos.
    #   2. Duplicados cuando un Product tiene múltiples variants/prices.
    # selectinload hace un segundo SELECT con IN() — 1 extra round-trip, sin duplicar.
    query = query_visible_products(
        db,
        current_user,
        org_id,
        include_inactive=include_inactive,
        search=search if search else None,
        branch_id_override=branch_override,
    ).options(
        selectinload(Product.variants).selectinload(ProductVariant.prices),
        joinedload(Product.department),
        joinedload(Product.brand),
    )

    # Filtro explícito de status (admin puede pedir PENDING/REJECTED)
    if approval_status and approval_status != 'ALL':
        query = query.filter(Product.approval_status == approval_status)

    if department_id:
        query = query.filter(Product.department_id == department_id)

    if brand_id:
        query = query.filter(Product.brand_id == brand_id)

    if active_only:
        query = query.filter(Product.is_active == True)

    # target_branch_id para enriquecimiento de stock (abajo) — fuera del filtro de visibilidad
    target_branch_id = branch_id if branch_id is not None else current_user.branch_id

    # active_in_branch ya está cubierto para no-admins por el helper (INNER JOIN a PBS is_active_pos=True).
    # Para admin con override, el helper también hace INNER JOIN. Sin override queda como antes
    # (admin ve todo incluyendo sin PBS).

    total_count = query.count()
    products_db = query.offset(skip).limit(limit).all()
    # --- Optimización N+1 Stock ---
    # Colectar IDs de TODAS las variantes (no solo la principal), para que
    # _compute_product_read pueda llenar el stock_total de cada una.
    variant_ids = [v.id for p in products_db for v in p.variants]

    stock_cache = {}
    if variant_ids and target_branch_id:
        stocks = (
            db.query(StockOnHand.variant_id, StockOnHand.qty_on_hand, StockOnHand.is_active)
            .filter(
                StockOnHand.variant_id.in_(variant_ids),
                StockOnHand.branch_id == target_branch_id,
                StockOnHand.organization_id == org_id,
            )
            .all()
        )
        # Convertir a Dict {variant_id: (qty, is_active)}
        stock_cache = {s.variant_id: (s.qty_on_hand, s.is_active) for s in stocks}

    # [FIX] Batch load de ProductBranchStatus para TODOS los productos en esta página.
    # Evita N+1: antes se hacía 1 query por producto dentro de _compute_product_read.
    branch_statuses_cache: dict[str, list] = {}
    if variant_ids:
        all_statuses = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id.in_(variant_ids),
            ProductBranchStatus.organization_id == org_id,
        ).all()
        for bs in all_statuses:
            branch_statuses_cache.setdefault(bs.variant_id, []).append(bs)

    results: List[ProductRead] = []
    for p in products_db:
        results.append(
            _compute_product_read(p, db, current_user, stock_cache, target_branch_id, branch_statuses_cache)
        )

    return ProductListResponse(items=results, total=total_count)


# -----------------------------
# 2. Crear producto
# -----------------------------
@router.post("/", response_model=ProductRead,
             dependencies=[Depends(require_module("catalog"))])
def create_product(
    prod_in: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Alta de producto. La lógica vive en `services.crear_producto`; aquí
    solo se confirma la transacción y se serializa la respuesta."""
    try:
        producto = crear_producto(db, org_id, current_user, prod_in)
        db.commit()
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        if "product_variants" in str(e) and "sku" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"El SKU '{prod_in.sku}' ya existe en esta organización.",
            )
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(producto)
    return _compute_product_read(producto, db, current_user, target_branch_id=current_user.branch_id)


@router.get("/sku-suggest")
def sugerir_sku(
    name: str = "",
    brand: Optional[str] = None,
    model: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    gender: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """SKU que sugiere la convención MARCA-PRENDA-MODELO-GENERO-COLOR-TALLA.

    Es solo una SUGERENCIA: nada la aplica sola y el alta sigue aceptando
    cualquier SKU único de la organización. `available` dice si ese código ya
    lo ocupa una variante viva de ESTA organización (el mismo SKU en otra
    tienda no estorba).

    Va declarado ANTES de `GET /{product_id}`: al revés, FastAPI resolvería
    "sku-suggest" como un id de producto y devolvería 404.
    """
    sku = sku_sugerido(brand, name, model, color, size, gender=gender)
    ocupado = False
    if sku:
        ocupado = db.query(ProductVariant.id).filter(
            ProductVariant.sku == sku,
            ProductVariant.organization_id == org_id,
            ProductVariant.deleted_at == None,  # noqa: E711
        ).first() is not None
    return {"sku": sku, "available": bool(sku) and not ocupado}


@router.get("/{product_id}", response_model=ProductRead)
def read_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Returns full details for a single product, including:
    - Main variant info (SKU, Base Price)
    - Tiered pricing list
    - Packaging info (Boxes)
    - Department
    - Stock in current user's branch

    [A1-05] Usa get_product_if_visible para cerrar IDOR cross-branch:
    CAJERO/GERENTE solo ven el producto si tiene PBS(is_active_pos=True)
    en su sucursal.

    [A1-07] Para no-admins, branch_statuses se filtra a su propia sucursal
    — no se filtra el array completo de todas las sucursales (leak).
    """
    # get_product_if_visible aplica la policy completa (tenant + branch + PBS).
    # Devuelve None si el usuario no puede verlo -> 404.
    visible = get_product_if_visible(db, current_user, org_id, product_id)
    if not visible:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # Recarga con eager-loading para _compute_product_read (relaciones anidadas).
    product = (
        db.query(Product)
        .options(
            joinedload(Product.variants).joinedload(ProductVariant.prices),
            joinedload(Product.variants).joinedload(ProductVariant.packaging_units),
            joinedload(Product.department),
        )
        .filter(Product.id == product_id, Product.organization_id == org_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    p_read = _compute_product_read(product, db, current_user)

    # [A1-07] Leak de branch_statuses: no-admins solo ven su branch.
    if not _is_admin(current_user) and current_user.branch_id is not None:
        p_read.branch_statuses = [
            bs for bs in (p_read.branch_statuses or [])
            if bs.branch_id == current_user.branch_id
        ]

    return p_read


# NOTE: `@router.put("/{product_id}/legacy")` was removed. Its deprecated
# update flow was superseded by the canonical `PUT /{product_id}` at the
# bottom of this file (see `update_product`). The legacy handler also
# tolerated `organization_id == None` products — a tenancy hole carried
# over from pre-multitenant seed data.


# -----------------------------
# 4. Eliminar (soft delete — único DELETE, cascade a variants/PBS/Stock)
# -----------------------------
# Nota: existía un segundo @router.delete("/{product_id}") más abajo en el
# archivo (previamente L2684) sin guard de rol — quedaba primero en el order
# y permitía a CAJERO eliminar productos físicamente. Consolidamos en este
# único endpoint con: RBAC, tenancy, soft-delete transaccional y cascade a
# ProductBranchStatus + StockOnHand.
@router.delete("/{product_id}")
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Soft-delete de un producto. Propaga `is_active=False` a todas sus
    variantes, sus ProductBranchStatus y sus StockOnHand en una sola
    transacción.
    """
    # Track 3: cajero también puede borrar productos visibles en su sucursal.
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado para eliminar productos")

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.organization_id == org_id,
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado o no pertenece a su organización",
        )

    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        product.deleted_at = now
        product.is_active = False

        variant_ids = [v.id for v in product.variants]
        for v in product.variants:
            v.deleted_at = now

        if variant_ids:
            # Cascade PBS — que el producto deje de aparecer en POS inmediatamente.
            db.query(ProductBranchStatus).filter(
                ProductBranchStatus.variant_id.in_(variant_ids),
                ProductBranchStatus.organization_id == org_id,
            ).update(
                {
                    ProductBranchStatus.is_active_pos: False,
                    ProductBranchStatus.is_active_hq: False,
                    ProductBranchStatus.is_visible: False,
                },
                synchronize_session=False,
            )

            # Cascade StockOnHand — no mostrar stock fantasma.
            db.query(StockOnHand).filter(
                StockOnHand.variant_id.in_(variant_ids),
                StockOnHand.organization_id == org_id,
            ).update(
                {StockOnHand.is_active: False},
                synchronize_session=False,
            )

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("DELETE_PRODUCT_FAILED product_id=%s org_id=%s", product_id, org_id)
        raise HTTPException(status_code=500, detail="Error al eliminar producto")

    return {"status": "ok", "message": "Producto archivado"}


# -----------------------------
# 8. WORKFLOW ENDPOINTS (NEW)
# -----------------------------

@router.put("/{product_id}/approve")
def approve_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Approve a PENDING product for Global Visibility."""
    # Track 3: el cajero también puede aprobar productos creados en su sucursal.
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")

    prod = db.query(Product).filter(Product.id == product_id, Product.organization_id == org_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    prod.approval_status = 'APPROVED'
    db.commit()
    return {"status": "approved", "product_id": product_id}


@router.put("/{product_id}/reject")
def reject_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Rechaza un producto PENDING. Marca approval_status='REJECTED' y
    desactiva PBS.is_active_pos en TODAS sus sucursales (no se vende
    mientras esté rechazado). Admin-only.

    Revertir: PUT /{product_id}/approve lo vuelve a APPROVED; quien
    aprueba debe re-activar PBS manualmente desde la matriz.
    """
    # Track 3: cajero puede rechazar productos visibles en su sucursal.
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")

    prod = db.query(Product).filter(
        Product.id == product_id,
        Product.organization_id == org_id,
    ).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        prod.approval_status = 'REJECTED'
        variant_ids = [v.id for v in prod.variants]
        if variant_ids:
            db.query(ProductBranchStatus).filter(
                ProductBranchStatus.variant_id.in_(variant_ids),
                ProductBranchStatus.organization_id == org_id,
            ).update(
                {ProductBranchStatus.is_active_pos: False},
                synchronize_session=False,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("PRODUCT_REJECT_FAILED product_id=%s org_id=%s", product_id, org_id)
        raise HTTPException(status_code=500, detail="Error al rechazar producto")

    return {"status": "rejected", "product_id": product_id}


@router.post("/{product_id}/restore")
def restore_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Restaura un producto archivado (soft-deleted). Admin-only.
    Pone `is_active=True`, limpia `deleted_at` y limpia el `deleted_at`
    de las variantes.

    Las filas PBS y StockOnHand quedan en `is_active_pos=False` /
    `is_active=False` tras el archive previo; el admin las re-activa
    desde la matriz de sucursales — no se asume que todas las sucursales
    deban volver a venderlo automáticamente.
    """
    # Track 3: cajero también puede restaurar productos archivados.
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")

    prod = db.query(Product).filter(
        Product.id == product_id,
        Product.organization_id == org_id,
    ).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    if prod.is_active and prod.deleted_at is None:
        return {"status": "ok", "product_id": product_id, "message": "Producto ya activo"}

    try:
        prod.is_active = True
        prod.deleted_at = None
        for v in prod.variants:
            if getattr(v, "deleted_at", None) is not None:
                v.deleted_at = None
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("PRODUCT_RESTORE_FAILED product_id=%s org_id=%s", product_id, org_id)
        raise HTTPException(status_code=500, detail="Error al restaurar producto")

    return {
        "status": "restored",
        "product_id": product_id,
        "message": "Producto restaurado. Re-activa sus sucursales desde la matriz.",
    }


@router.post("/{product_id}/duplicate", response_model=ProductRead,
             dependencies=[Depends(require_module("catalog"))])
def duplicate_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Duplica un producto (ver `services.duplicar_producto`). Sin existencias."""
    # Track 3: cajero también puede duplicar productos visibles en su sucursal.
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        copia = duplicar_producto(db, org_id, current_user, product_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("PRODUCT_DUPLICATE_FAILED product_id=%s org_id=%s", product_id, org_id)
        raise HTTPException(status_code=500, detail="Error al duplicar producto")
    db.refresh(copia)
    return _compute_product_read(copia, db, current_user, target_branch_id=current_user.branch_id)


# -----------------------------
# 3. MDM Operations (Update / Delete / Approve)
# -----------------------------

@router.put("/{product_id}", response_model=ProductRead,
            dependencies=[Depends(require_module("catalog"))])
def update_product(
    product_id: str,
    prod_in: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Edición de producto (ver `services.actualizar_producto`)."""
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")
    producto = actualizar_producto(db, org_id, current_user, product_id, prod_in)
    db.commit()
    db.refresh(producto)
    return _compute_product_read(producto, db, current_user)

# NOTE: previously a second `@router.delete("/{product_id}")` lived here without
# RBAC; consolidated into the single DELETE endpoint earlier in the file.

# NOTE: `POST /{product_id}/approve` was removed — duplicated the
# canonical `PUT /{product_id}/approve` earlier in this file. No frontend
# caller used the POST verb.


# ─────────────────────────────────────────────────────────────────────────────
# Image upload / delete
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB
_IMAGE_DIR = Path("app/static/product_images")


@router.post("/{product_id}/image", response_model=ProductRead)
async def upload_product_image(
    product_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Upload or replace the product image (JPEG / PNG / WEBP, max 2 MB).

    Cuando `CLOUDINARY_URL` está configurada, la imagen va a Cloudinary y la
    URL CDN se persiste en `Product.image_url`. Sin esa env var, fallback a
    `app/static/product_images/<id>.<ext>` (legacy).
    """
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="Sin permiso para subir imágenes")

    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.organization_id == org_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo no permitido ({file.content_type}). Usa JPEG, PNG o WEBP.",
        )

    contents = await file.read()
    if len(contents) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="La imagen supera el límite de 2 MB")

    product.image_url = image_storage.upload_image(
        contents,
        public_id=product_id,
        folder=image_storage.PRODUCTS_FOLDER,
        content_type=file.content_type,
    )
    db.commit()
    db.refresh(product)

    return _compute_product_read(product, db, current_user)


@router.delete("/{product_id}/image", response_model=ProductRead)
def delete_product_image(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Remove the product image and clear ``Product.image_url``."""
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="Sin permiso para eliminar imágenes")

    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.organization_id == org_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    image_storage.delete_image(product_id, folder=image_storage.PRODUCTS_FOLDER)
    product.image_url = None
    db.commit()
    db.refresh(product)

    return _compute_product_read(product, db, current_user)
