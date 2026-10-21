"""``GET /api/products/stats/*`` — catalog and branch KPIs.

Sprint 5b split — extracted verbatim from the original ``products.py``.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import Optional

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Product, ProductVariant, StockOnHand, User, ProductBranchStatus,
)
from app.core.security import get_current_user
from app.crud.products import query_visible_products, _is_admin

from app.services.existencias import umbral_poca_existencia

router = APIRouter()


@router.get("/stats/catalog-kpis")
def get_catalog_kpis(
    search: Optional[str] = None,
    department_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    approval_status: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    KPIs contextuales del catálogo — respetan los mismos filtros que
    `GET /products/`. Pensado para el header del Admin Catalog.

    Scope automático por rol (usa `query_visible_products`):
        - ADMIN / DUEÑO: catálogo completo de la org. Puede pasar
          `branch_id` para drill-down a una sucursal.
        - Resto (CAJERO / GERENTE / ...): siempre scoped a su sucursal.

    Devuelve 6 métricas:
        total_skus          — variantes visibles en el scope actual
        active_pos          — con PBS(is_active_pos=True) en ≥1 sucursal
        pending_approval    — productos con approval_status == 'PENDING'
        no_branch           — variants sin ningún PBS (huérfanas)
        critical_stock      — con qty_on_hand ≤ threshold en alguna rama
        zero_stock          — con qty_on_hand == 0 en alguna rama
    """
    is_admin = _is_admin(current_user)

    # Admin puede override branch; no-admin siempre su propia sucursal.
    branch_override = branch_id if (is_admin and branch_id and branch_id > 0) else None

    base_q = query_visible_products(
        db,
        current_user,
        org_id,
        include_inactive=True if is_admin else False,
        search=search or None,
        branch_id_override=branch_override,
    )

    if department_id:
        base_q = base_q.filter(Product.department_id == department_id)
    if brand_id:
        base_q = base_q.filter(Product.brand_id == brand_id)
    if approval_status and approval_status != 'ALL':
        base_q = base_q.filter(Product.approval_status == approval_status)

    # Subquery de IDs de productos en el scope — usada como filtro para las
    # métricas derivadas (variant/PBS/stock). Se materializa una vez.
    visible_product_ids = base_q.with_entities(Product.id).subquery()

    total_skus = db.query(func.count(ProductVariant.id)).filter(
        ProductVariant.product_id.in_(visible_product_ids.select()),
    ).scalar() or 0

    # Variants con al menos un PBS activo en cualquier sucursal (si admin
    # pasó branch_override, `query_visible_products` ya restringió a esa rama).
    active_pos_q = db.query(func.count(func.distinct(ProductBranchStatus.variant_id))).filter(
        ProductBranchStatus.organization_id == org_id,
        ProductBranchStatus.is_active_pos.is_(True),
    ).join(ProductVariant, ProductVariant.id == ProductBranchStatus.variant_id).filter(
        ProductVariant.product_id.in_(visible_product_ids.select()),
    )
    if branch_override:
        active_pos_q = active_pos_q.filter(ProductBranchStatus.branch_id == branch_override)
    active_pos = active_pos_q.scalar() or 0

    # PENDING viene del producto, no del PBS.
    pending_q = db.query(func.count(Product.id)).filter(
        Product.organization_id == org_id,
        Product.approval_status == 'PENDING',
        Product.is_active.is_(True),
    )
    if is_admin:
        if department_id:
            pending_q = pending_q.filter(Product.department_id == department_id)
        if brand_id:
            pending_q = pending_q.filter(Product.brand_id == brand_id)
    else:
        # No-admin no debería ver PENDING: query_visible_products ya filtra
        # por approval_status=APPROVED. Devolvemos 0 explícito.
        pending_q = pending_q.filter(Product.id.is_(None))
    pending_approval = pending_q.scalar() or 0

    # Variants sin NINGÚN PBS — huérfanas (un admin las debería activar).
    no_branch_subq = db.query(ProductBranchStatus.variant_id).filter(
        ProductBranchStatus.organization_id == org_id,
    ).subquery()
    no_branch = db.query(func.count(ProductVariant.id)).filter(
        ProductVariant.product_id.in_(visible_product_ids.select()),
        ~ProductVariant.id.in_(no_branch_subq.select()),
    ).scalar() or 0

    # Stock con PBS activo — usa el threshold constante de P3 (reports.py lo re-define).
    stock_base = db.query(StockOnHand.variant_id).join(
        ProductBranchStatus,
        and_(
            ProductBranchStatus.variant_id == StockOnHand.variant_id,
            ProductBranchStatus.branch_id == StockOnHand.branch_id,
            ProductBranchStatus.is_active_pos.is_(True),
        ),
    ).join(ProductVariant, ProductVariant.id == StockOnHand.variant_id).filter(
        StockOnHand.organization_id == org_id,
        StockOnHand.is_active.is_(True),
        ProductVariant.product_id.in_(visible_product_ids.select()),
    )
    if branch_override:
        stock_base = stock_base.filter(StockOnHand.branch_id == branch_override)

    umbral = umbral_poca_existencia(db, org_id)   # SP6: el tope de la empresa
    zero_stock = stock_base.filter(StockOnHand.qty_on_hand <= 0).distinct().count()
    critical_stock = stock_base.filter(
        StockOnHand.qty_on_hand > 0,
        StockOnHand.qty_on_hand <= umbral,
    ).distinct().count()

    return {
        "total_skus": int(total_skus),
        "active_pos": int(active_pos),
        "pending_approval": int(pending_approval),
        "no_branch": int(no_branch),
        "critical_stock": int(critical_stock),
        "zero_stock": int(zero_stock),
        "threshold": umbral,
    }


@router.get("/stats/branch-kpis")
def get_branch_kpis(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization), # [HARDENING]
):
    """
    Returns KPI metrics for a specific branch or the entire organization (branch_id=0).

    [A1-09] Autorización por branch:
    - ADMINISTRADOR / DUEÑO: acceso libre a cualquier branch (incluye 0 = global).
    - Resto: solo pueden consultar KPIs de su propia sucursal.
    """
    # [A1-09] No-admins solo ven KPIs de su propia sucursal.
    if not _is_admin(current_user):
        # branch_id=0 (global) bloqueado para no-admins.
        if branch_id == 0 or branch_id != current_user.branch_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes consultar KPIs de tu sucursal asignada",
            )

    if branch_id == 0:
        # 0 means Global Organization View
        base_query = db.query(Product).filter(or_(Product.organization_id == org_id, Product.organization_id == None))

        total_active = base_query.filter(Product.is_active == True).count()
        total_inactive = base_query.filter(Product.is_active == False).count()

        # [FIX] Aggregate stock alerts con JOIN explícito a ProductBranchStatus.
        # Sin el JOIN, SQLAlchemy genera un cross join que produce conteos incorrectos.
        _pbs_join = and_(
            ProductBranchStatus.variant_id == StockOnHand.variant_id,
            ProductBranchStatus.branch_id == StockOnHand.branch_id,
            ProductBranchStatus.is_active_pos == True,
        )

        # Count variants con Stock Total <= 0 en cualquier sucursal donde esté activo
        zero_stock_count = (
            db.query(StockOnHand.variant_id)
            .join(ProductBranchStatus, _pbs_join)
            .filter(StockOnHand.organization_id == org_id)
            .group_by(StockOnHand.variant_id)
            .having(func.sum(StockOnHand.qty_on_hand) <= 0)
            .count()
        )

        # Variantes con stock total entre 1 y el umbral de la empresa (stock bajo, SP6)
        umbral = umbral_poca_existencia(db, org_id)
        low_stock_count = (
            db.query(StockOnHand.variant_id)
            .join(ProductBranchStatus, _pbs_join)
            .filter(StockOnHand.organization_id == org_id)
            .group_by(StockOnHand.variant_id)
            .having(and_(func.sum(StockOnHand.qty_on_hand) > 0, func.sum(StockOnHand.qty_on_hand) <= umbral))
            .count()
        )

        return {
            "total_active": total_active,
            "total_inactive": total_inactive,
            "zero_stock": zero_stock_count,
            "low_stock": low_stock_count
        }

    # [HARDENING] Validate branch belongs to org
    from app.models.organization import Branch
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if not branch:
        raise HTTPException(status_code=403, detail="Branch not found or access denied")

    # [FIX] Base query con JOIN explícito a ProductBranchStatus para esta sucursal.
    # Antes se filtraba ProductBranchStatus sin JOIN (cross join implícito → conteos erróneos).
    _pbs_join_branch = and_(
        ProductBranchStatus.variant_id == StockOnHand.variant_id,
        ProductBranchStatus.branch_id == StockOnHand.branch_id,
    )
    base_query = (
        db.query(StockOnHand)
        .join(ProductBranchStatus, _pbs_join_branch)
        .filter(StockOnHand.branch_id == branch_id)
    )

    total_active = base_query.filter(ProductBranchStatus.is_active_pos == True).count()
    total_inactive = base_query.filter(StockOnHand.is_active == False).count()

    zero_stock = base_query.filter(
        ProductBranchStatus.is_active_pos == True,
        StockOnHand.qty_on_hand <= 0
    ).count()

    low_stock = base_query.filter(
        ProductBranchStatus.is_active_pos == True,
        StockOnHand.qty_on_hand > 0,
        StockOnHand.qty_on_hand <= umbral_poca_existencia(db, org_id),   # SP6: umbral único
    ).count()

    return {
        "total_active": total_active,
        "total_inactive": total_inactive,
        "zero_stock": zero_stock,
        "low_stock": low_stock
    }
