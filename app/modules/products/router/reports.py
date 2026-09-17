"""``GET /api/products/hq-inventory`` — paginated HQ inventory grid + KPIs.

Sprint 5b split — extracted verbatim from the original ``products.py``.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, contains_eager
from sqlalchemy import or_, and_, func
from typing import Optional

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Product, ProductVariant, StockOnHand, User, Department,
)
from app.core.security import get_current_user
from app.crud.products import _is_admin

from ._shared import _compute_product_read

router = APIRouter()


@router.get("/hq-inventory")
def hq_inventory_list(
    skip: int = 0,
    limit: int = 50,
    search: str = "",
    branch_id: int = None,
    department_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    stock_status: Optional[str] = None,   # no_stock | low_stock | in_stock
    product_active: Optional[bool] = None, # None = todos, True = activos, False = inactivos
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    from app.modules.products.schemas import HQInventoryPage, HQInventoryKPIs

    # [A1-10] Admin-only: ADMINISTRADOR / DUEÑO. GERENTE no accede a vista HQ.
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Solo ADMINISTRADOR o DUEÑO pueden ver el inventario global HQ",
        )

    # branch_id=0 means "all branches" (global); None also means global for HQ users
    target_branch_id = branch_id if branch_id and branch_id != 0 else None

    # ── Base query ────────────────────────────────────────────────────────
    query = (
        db.query(Product)
        .outerjoin(ProductVariant, ProductVariant.product_id == Product.id)
        .outerjoin(Department, Department.id == Product.department_id)
        .options(
            contains_eager(Product.variants).joinedload(ProductVariant.prices),
            contains_eager(Product.department),
            joinedload(Product.brand),
        )
        .filter(Product.organization_id == org_id)
        .distinct()
    )

    # ── Filters ───────────────────────────────────────────────────────────
    if product_active is not None:
        query = query.filter(Product.is_active == product_active)

    if search:
        s = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.ilike(s),
                ProductVariant.sku.ilike(s),
                ProductVariant.barcode.ilike(s),
            )
        ).distinct()

    if department_id:
        query = query.filter(Product.department_id == department_id)

    if brand_id:
        query = query.filter(Product.brand_id == brand_id)

    # ── Stock status filter ───────────────────────────────────────────────
    if stock_status:
        if target_branch_id:
            stock_agg = (
                db.query(StockOnHand.variant_id, func.sum(StockOnHand.qty_on_hand).label("qty"))
                .filter(StockOnHand.organization_id == org_id, StockOnHand.branch_id == target_branch_id)
                .group_by(StockOnHand.variant_id)
                .subquery()
            )
        else:
            stock_agg = (
                db.query(StockOnHand.variant_id, func.sum(StockOnHand.qty_on_hand).label("qty"))
                .filter(StockOnHand.organization_id == org_id)
                .group_by(StockOnHand.variant_id)
                .subquery()
            )
        query = query.outerjoin(stock_agg, ProductVariant.id == stock_agg.c.variant_id)
        if stock_status == "no_stock":
            query = query.filter(or_(stock_agg.c.qty == None, stock_agg.c.qty <= 0))
        elif stock_status == "low_stock":
            query = query.filter(stock_agg.c.qty > 0, stock_agg.c.qty <= 5)
        elif stock_status == "in_stock":
            query = query.filter(stock_agg.c.qty > 5)

    # ── Total count (before pagination) ──────────────────────────────────
    total = query.count()

    # ── KPIs on full filtered set ─────────────────────────────────────────
    product_ids_subq = query.with_entities(Product.id).subquery()

    if target_branch_id:
        kpi_stock_filter = and_(
            StockOnHand.variant_id == ProductVariant.id,
            StockOnHand.branch_id == target_branch_id,
            StockOnHand.organization_id == org_id,
        )
    else:
        kpi_stock_filter = and_(
            StockOnHand.variant_id == ProductVariant.id,
            StockOnHand.organization_id == org_id,
        )

    kpi_rows = (
        db.query(
            ProductVariant.cost,
            func.coalesce(func.sum(StockOnHand.qty_on_hand), 0).label("total_qty"),
        )
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(StockOnHand, kpi_stock_filter)
        .filter(Product.id.in_(product_ids_subq))
        .group_by(ProductVariant.id, ProductVariant.cost)
        .all()
    )

    zero_stock_count = sum(1 for _, s in kpi_rows if float(s or 0) <= 0)
    low_stock_count  = sum(1 for _, s in kpi_rows if 0 < float(s or 0) <= 5)
    inventory_value  = sum(float(c or 0) * float(s or 0) for c, s in kpi_rows)

    kpis = HQInventoryKPIs(
        total_skus=total,
        low_stock_count=low_stock_count,
        zero_stock_count=zero_stock_count,
        inventory_value=inventory_value,
    )

    # ── Paginated items ───────────────────────────────────────────────────
    products_db = query.offset(skip).limit(limit).all()

    # Todas las variantes (no solo la principal), para que
    # _compute_product_read llene el stock_total de cada una sin disparar
    # una query por variante faltante.
    variant_ids = [v.id for p in products_db for v in p.variants]
    stock_cache: dict = {}
    if variant_ids:
        if target_branch_id:
            stocks = (
                db.query(StockOnHand.variant_id, StockOnHand.qty_on_hand, StockOnHand.is_active)
                .filter(StockOnHand.variant_id.in_(variant_ids), StockOnHand.branch_id == target_branch_id)
                .all()
            )
            stock_cache = {s.variant_id: (s.qty_on_hand, s.is_active) for s in stocks}
        else:
            stocks = (
                db.query(StockOnHand.variant_id, func.sum(StockOnHand.qty_on_hand).label("qty"))
                .filter(StockOnHand.variant_id.in_(variant_ids), StockOnHand.organization_id == org_id)
                .group_by(StockOnHand.variant_id)
                .all()
            )
            stock_cache = {s.variant_id: (s.qty, True) for s in stocks}

    items = []
    for p in products_db:
        p_read = _compute_product_read(
            p, db, current_user,
            stock_cache=stock_cache,
            target_branch_id=target_branch_id,
        )
        if not target_branch_id and p.variants:
            cached = stock_cache.get(p.variants[0].id)
            if cached:
                p_read.stock_total = cached[0]
        items.append(p_read)

    return HQInventoryPage(items=items, total=total, skip=skip, limit=limit, kpis=kpis)
