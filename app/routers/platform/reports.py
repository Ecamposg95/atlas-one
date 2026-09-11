"""Platform Reports endpoints (`/reports/*`).

Cross-tenant analytics for SUPERADMIN/SUPPORT. Pivots:
- products  (by product_id)
- branches  (by branch_id)
- sellers   (by seller_id == sales.user_id)
- customers (by customer_id, excludes anonymous)

Each pivot has a paginated list endpoint, a drill-down detail endpoint,
and a CSV streaming endpoint. List pivots cache 5 min; detail and CSV
bypass cache.

Auth is enforced at the package level via ``require_platform_admin``
in ``app/routers/platform/__init__.py`` — no per-endpoint check.
"""

import csv
import io
import time
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, case, distinct, func, nulls_last
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    Branch,
    DocumentStatus,
    Organization,
    Payment,
    Product,
    ProductVariant,
    SalesDocument,
    SalesLineItem,
    User,
)
from app.models.crm import Customer
from app.models.products import Brand, Department
from app.models.returns import SaleReturn, SaleReturnItem
from app.services.report_compare import COMPARE_MODES, compare_window, decorate_with_previous

router = APIRouter()


# ------------------------------------------------------------------ #
# In-process TTL cache (mirror of stats.py pattern)                  #
# ------------------------------------------------------------------ #

_cache: dict[str, tuple[float, Any]] = {}
_DEFAULT_TTL = 300  # 5 min


def _cached(key: str, fn: Callable[[], Any], ttl_seconds: int = _DEFAULT_TTL) -> Any:
    now = time.time()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < ttl_seconds:
        return cached[1]
    result = fn()
    _cache[key] = (now, result)
    return result


# ------------------------------------------------------------------ #
# Helpers                                                            #
# ------------------------------------------------------------------ #


def _parse_dates(start_str: Optional[str], end_str: Optional[str]) -> tuple[datetime, datetime]:
    """Parse ISO date/datetime params. Defaults: end=now, start=end-30d."""
    end = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999999)
    start = end - timedelta(days=30)
    if start_str:
        try:
            parsed = datetime.fromisoformat(start_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            # If only a date (no T) was supplied, anchor at start of day.
            if "T" not in start_str and " " not in start_str:
                parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
            start = parsed
        except Exception:
            raise HTTPException(422, f"Fecha start inválida: {start_str}")
    if end_str:
        try:
            parsed = datetime.fromisoformat(end_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if "T" not in end_str and " " not in end_str:
                parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
            end = parsed
        except Exception:
            raise HTTPException(422, f"Fecha end inválida: {end_str}")
    if start > end:
        raise HTTPException(422, "start debe ser anterior a end")
    return start, end


def _validate_filters(start: datetime, end: datetime, org_id: Optional[int], limit: int):
    if limit > 500:
        raise HTTPException(422, "limit máximo es 500")
    if limit < 1:
        raise HTTPException(422, "limit debe ser >= 1")
    if org_id is None and (end - start).days > 365:
        raise HTTPException(422, "Rango máximo es 365 días cuando no hay org filter")


def _validate_branch_in_org(db: Session, branch_id: int, org_id: Optional[int]) -> Branch:
    """Confirm branch exists and (if org_id given) belongs to that org. Returns the Branch."""
    q = db.query(Branch).filter(Branch.id == branch_id)
    if org_id is not None:
        q = q.filter(Branch.organization_id == org_id)
    branch = q.first()
    if not branch:
        raise HTTPException(
            404,
            f"Sucursal {branch_id} no encontrada"
            + (f" en org {org_id}" if org_id is not None else ""),
        )
    return branch


def _apply_doc_filters(query, start, end, org_id, branch_id, db):
    """Apply common time/org/branch/status filters on a query that already
    has SalesDocument joined. Excludes CANCELLED + DRAFT."""
    query = query.filter(SalesDocument.created_at >= start)
    query = query.filter(SalesDocument.created_at <= end)
    query = query.filter(
        ~SalesDocument.status.in_([DocumentStatus.CANCELLED, DocumentStatus.DRAFT])
    )
    if org_id is not None:
        query = query.filter(SalesDocument.organization_id == org_id)
    if branch_id is not None:
        if org_id is not None:
            _validate_branch_in_org(db, branch_id, org_id)
        query = query.filter(SalesDocument.branch_id == branch_id)
    return query


def _parse_sort(sort: str, allowed: set[str]) -> tuple[str, str]:
    """Parse 'field:asc|desc' → (field, direction). 422 if invalid."""
    if not sort:
        return "revenue", "desc"
    parts = sort.split(":")
    field = parts[0].strip()
    direction = parts[1].strip().lower() if len(parts) > 1 else "desc"
    if field not in allowed:
        raise HTTPException(
            422, f"sort field inválido: {field}. Permitidos: {sorted(allowed)}"
        )
    if direction not in ("asc", "desc"):
        raise HTTPException(422, f"sort direction inválida: {direction}")
    return field, direction


def _dec_str(value, places: int = 2) -> str:
    """Format Decimal/float/None as string with N decimal places."""
    if value is None:
        return "0.00"
    d = Decimal(str(value))
    quant = Decimal("1." + ("0" * places))
    return str(d.quantize(quant))


def _dec_str_or_none(value, places: int = 2) -> Optional[str]:
    if value is None:
        return None
    return _dec_str(value, places)


def _order_by_with_nulls_last(direction: str, *cols):
    """Apply asc/desc with NULLS LAST."""
    out = []
    for c in cols:
        if direction == "desc":
            out.append(nulls_last(c.desc()))
        else:
            out.append(nulls_last(c.asc()))
    return out


def _validate_compare(compare: str) -> str:
    if compare not in COMPARE_MODES:
        raise HTTPException(422, f"compare inválido: {compare}. Permitidos: {sorted(COMPARE_MODES)}")
    return compare


# Campos que ganan `prev_*`/`delta_*_pct` en cada pivote (spec §5.1).
_COMPARE_FIELDS = {
    "products":  ("revenue", "units_sold", "aov"),
    "branches":  ("revenue", "transactions", "avg_ticket"),
    "sellers":   ("revenue", "transactions", "avg_ticket"),
    "customers": ("total_revenue", "ticket_count", "avg_ticket"),
}
_COMPARE_KEYS = {
    "products": "product_id",
    "branches": "branch_id",
    "sellers": "user_id",
    "customers": "customer_id",
}


def _rows_for_window(db, s, e, org_id, branch_id, *, pivot: str) -> list[dict]:
    """Filas agregadas de un pivote para una ventana, sin ordenar ni paginar.

    Es el mismo cuerpo que consume el listado; se factoriza para poder correrlo
    una segunda vez sobre la ventana de comparación sin duplicar la consulta.
    """
    if pivot == "products":
        return _products_rows(db, s, e, org_id, branch_id)
    if pivot == "branches":
        return _branches_rows(db, s, e, org_id, branch_id)
    if pivot == "sellers":
        return _sellers_rows(db, s, e, org_id, branch_id)
    if pivot == "customers":
        return _customers_rows(db, s, e, org_id, branch_id)
    raise ValueError(f"pivote desconocido: {pivot}")


# ------------------------------------------------------------------ #
# Returned-quantity subquery (per variant + per document)            #
# ------------------------------------------------------------------ #


def _returned_qty_per_variant(db, start, end, org_id, branch_id):
    """Subquery: total returned qty per variant_id within filters."""
    q = (
        db.query(
            SaleReturnItem.variant_id.label("variant_id"),
            func.coalesce(func.sum(SaleReturnItem.quantity), 0).label("returned_qty"),
        )
        .join(SaleReturn, SaleReturnItem.return_id == SaleReturn.id)
        .join(SalesDocument, SaleReturn.sale_id == SalesDocument.id)
    )
    q = _apply_doc_filters(q, start, end, org_id, branch_id, db)
    return q.group_by(SaleReturnItem.variant_id).subquery()


def _returned_qty_per_branch(db, start, end, org_id):
    """Subquery: total return rows per branch within filters."""
    q = (
        db.query(
            SaleReturn.branch_id.label("branch_id"),
            func.count(distinct(SaleReturn.id)).label("return_count"),
        )
        .join(SalesDocument, SaleReturn.sale_id == SalesDocument.id)
    )
    q = _apply_doc_filters(q, start, end, org_id, None, db)
    return q.group_by(SaleReturn.branch_id).subquery()


# ================================================================== #
# 1. PIVOT: PRODUCTS                                                 #
# ================================================================== #

PRODUCT_SORT_FIELDS = {
    "units_sold",
    "revenue",
    "aov",
    "return_rate_pct",
    "estimated_margin_pct",
    "name",
    "sku",
}


def _build_products_query(
    db: Session,
    start: datetime,
    end: datetime,
    org_id: Optional[int],
    branch_id: Optional[int],
):
    """Returns (rows_query, total_count_query) for the products pivot."""
    units_sold = func.coalesce(func.sum(SalesLineItem.quantity), 0).label("units_sold")
    revenue = func.coalesce(func.sum(SalesLineItem.total_line), 0).label("revenue")
    # Margin only on lines that have unit_cost.
    margin_expr = case(
        (
            and_(
                SalesLineItem.unit_cost.isnot(None),
                SalesLineItem.unit_price > 0,
            ),
            (SalesLineItem.unit_price - SalesLineItem.unit_cost)
            / SalesLineItem.unit_price
            * 100,
        ),
        else_=None,
    )
    avg_margin = func.avg(margin_expr).label("avg_margin")

    base = (
        db.query(
            Product.id.label("product_id"),
            Product.name.label("name"),
            ProductVariant.sku.label("sku"),
            Brand.name.label("brand"),
            Department.name.label("department"),
            units_sold,
            revenue,
            avg_margin,
        )
        .select_from(SalesLineItem)
        .join(SalesDocument, SalesLineItem.document_id == SalesDocument.id)
        .join(ProductVariant, SalesLineItem.variant_id == ProductVariant.id)
        .join(Product, ProductVariant.product_id == Product.id)
        .outerjoin(Brand, Product.brand_id == Brand.id)
        .outerjoin(Department, Product.department_id == Department.id)
    )
    base = _apply_doc_filters(base, start, end, org_id, branch_id, db)
    base = base.group_by(
        Product.id, Product.name, ProductVariant.sku, Brand.name, Department.name
    )
    return base


def _products_rows(db, s, e, org_id, branch_id) -> list[dict]:
    """Filas agregadas del pivote products para una ventana, sin ordenar ni paginar."""
    q = _build_products_query(db, s, e, org_id, branch_id)
    # Returns subquery: returned qty per variant -> aggregate to product_id.
    ret_sub = _returned_qty_per_variant(db, s, e, org_id, branch_id)
    # Re-aggregate returned qty by product via variant->product join.
    ret_per_product = (
        db.query(
            ProductVariant.product_id.label("product_id"),
            func.coalesce(func.sum(ret_sub.c.returned_qty), 0).label("returned_qty"),
        )
        .outerjoin(ret_sub, ret_sub.c.variant_id == ProductVariant.id)
        .group_by(ProductVariant.product_id)
        .subquery()
    )

    rows = q.all()
    # Build map of returned qty by product_id for in-Python join (rows already aggregated).
    returns_map = {
        r.product_id: r.returned_qty
        for r in db.query(ret_per_product.c.product_id, ret_per_product.c.returned_qty).all()
    }

    # Decorate in Python (results are already aggregated; cardinality bounded
    # by # of products in time window).
    items = []
    for r in rows:
        units = float(r.units_sold or 0)
        rev = Decimal(str(r.revenue or 0))
        aov = (rev / Decimal(str(units))) if units > 0 else Decimal("0")
        returned_qty = float(returns_map.get(r.product_id, 0) or 0)
        return_rate = (returned_qty / units * 100) if units > 0 else 0.0
        items.append(
            {
                "product_id": r.product_id,
                "sku": r.sku,
                "name": r.name,
                "brand": r.brand,
                "department": r.department,
                "units_sold": units,
                "revenue": _dec_str(rev),
                "aov": _dec_str(aov),
                "return_rate_pct": _dec_str(return_rate),
                "estimated_margin_pct": _dec_str_or_none(r.avg_margin),
            }
        )
    return items


@router.get("/reports/products")
def report_products(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = "revenue:desc",
    compare: str = "none",
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)
    field, direction = _parse_sort(sort, PRODUCT_SORT_FIELDS)
    _validate_compare(compare)

    cache_key = f"products:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{limit}:{offset}:{sort}:{compare}"

    def _run():
        items = _products_rows(db, s, e, org_id, branch_id)

        # Sort
        def _sort_key(it):
            v = it.get(field)
            if field in ("name", "sku"):
                return (v is None, (v or "").lower())
            if v is None:
                return (1, 0.0)
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (1, 0.0)

        items.sort(key=_sort_key, reverse=(direction == "desc"))
        total = len(items)
        page = items[offset : offset + limit]

        prev_window = compare_window(s, e, compare)
        if prev_window is not None:
            prev_s, prev_e = prev_window
            # Cache propia para la ventana previa, sin limit/offset/sort:
            # así páginas y ordenamientos distintos de la MISMA ventana
            # comparten un único cómputo en vez de re-agregar la ventana
            # anterior en cada combinación.
            prev_key = f"prevwin:products:{prev_s.isoformat()}:{prev_e.isoformat()}:{org_id}:{branch_id}"
            prev_items = _cached(prev_key, lambda: _rows_for_window(db, prev_s, prev_e, org_id, branch_id, pivot="products"))
            page = decorate_with_previous(
                page, prev_items,
                key=_COMPARE_KEYS["products"], fields=_COMPARE_FIELDS["products"],
            )

        return {"items": page, "total": total, "offset": offset, "limit": limit}

    return _cached(cache_key, _run)


# ================================================================== #
# 2. PIVOT: BRANCHES                                                 #
# ================================================================== #

BRANCH_SORT_FIELDS = {
    "transactions",
    "revenue",
    "avg_ticket",
    "active_cashiers",
    "return_rate_pct",
    "name",
}


def _branches_rows(db, s, e, org_id, branch_id) -> list[dict]:
    """Filas agregadas del pivote branches para una ventana, sin ordenar ni paginar."""
    transactions = func.count(distinct(SalesDocument.id)).label("transactions")
    revenue = func.coalesce(func.sum(SalesDocument.total_amount), 0).label("revenue")
    active_cashiers = func.count(distinct(SalesDocument.seller_id)).label("active_cashiers")

    q = (
        db.query(
            Branch.id.label("branch_id"),
            Branch.name.label("name"),
            Branch.city.label("city"),
            Organization.id.label("org_id"),
            Organization.name.label("org_name"),
            transactions,
            revenue,
            active_cashiers,
        )
        .select_from(SalesDocument)
        .join(Branch, SalesDocument.branch_id == Branch.id)
        .join(Organization, Branch.organization_id == Organization.id)
    )
    q = _apply_doc_filters(q, s, e, org_id, branch_id, db)
    q = q.group_by(Branch.id, Branch.name, Branch.city, Organization.id, Organization.name)
    q = q.having(func.count(distinct(SalesDocument.id)) > 0)
    rows = q.all()

    # Returns count per branch
    ret_sub = _returned_qty_per_branch(db, s, e, org_id)
    returns_map = {
        r.branch_id: r.return_count
        for r in db.query(ret_sub.c.branch_id, ret_sub.c.return_count).all()
    }

    items = []
    for r in rows:
        txn = int(r.transactions or 0)
        rev = Decimal(str(r.revenue or 0))
        avg_ticket = (rev / Decimal(txn)) if txn > 0 else Decimal("0")
        ret_count = int(returns_map.get(r.branch_id, 0) or 0)
        return_rate = (ret_count / txn * 100) if txn > 0 else 0.0
        items.append(
            {
                "branch_id": r.branch_id,
                "name": r.name,
                "org_id": r.org_id,
                "org_name": r.org_name,
                "city": r.city,
                "transactions": txn,
                "revenue": _dec_str(rev),
                "avg_ticket": _dec_str(avg_ticket),
                "active_cashiers": int(r.active_cashiers or 0),
                "return_rate_pct": _dec_str(return_rate),
            }
        )
    return items


@router.get("/reports/branches")
def report_branches(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = "revenue:desc",
    compare: str = "none",
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)
    field, direction = _parse_sort(sort, BRANCH_SORT_FIELDS)
    _validate_compare(compare)

    cache_key = f"branches:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{limit}:{offset}:{sort}:{compare}"

    def _run():
        items = _branches_rows(db, s, e, org_id, branch_id)

        def _sort_key(it):
            v = it.get(field)
            if field == "name":
                return (v is None, (v or "").lower())
            if v is None:
                return (1, 0.0)
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (1, 0.0)

        items.sort(key=_sort_key, reverse=(direction == "desc"))
        total = len(items)
        page = items[offset : offset + limit]

        prev_window = compare_window(s, e, compare)
        if prev_window is not None:
            prev_s, prev_e = prev_window
            prev_key = f"prevwin:branches:{prev_s.isoformat()}:{prev_e.isoformat()}:{org_id}:{branch_id}"
            prev_items = _cached(prev_key, lambda: _rows_for_window(db, prev_s, prev_e, org_id, branch_id, pivot="branches"))
            page = decorate_with_previous(
                page, prev_items,
                key=_COMPARE_KEYS["branches"], fields=_COMPARE_FIELDS["branches"],
            )

        return {"items": page, "total": total, "offset": offset, "limit": limit}

    return _cached(cache_key, _run)


# ================================================================== #
# 3. PIVOT: SELLERS                                                  #
# ================================================================== #

SELLER_SORT_FIELDS = {
    "transactions",
    "revenue",
    "avg_ticket",
    "active_days",
    "full_name",
}


def _sellers_rows(db, s, e, org_id, branch_id) -> list[dict]:
    """Filas agregadas del pivote sellers para una ventana, sin ordenar ni paginar."""
    transactions = func.count(distinct(SalesDocument.id)).label("transactions")
    revenue = func.coalesce(func.sum(SalesDocument.total_amount), 0).label("revenue")
    active_days = func.count(
        distinct(func.date(SalesDocument.created_at))
    ).label("active_days")

    q = (
        db.query(
            User.id.label("user_id"),
            User.full_name.label("full_name"),
            User.username.label("username"),
            User.role.label("role"),
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            Organization.id.label("org_id"),
            Organization.name.label("org_name"),
            transactions,
            revenue,
            active_days,
        )
        .select_from(SalesDocument)
        .join(User, SalesDocument.seller_id == User.id)
        .join(Branch, SalesDocument.branch_id == Branch.id)
        .join(Organization, Branch.organization_id == Organization.id)
    )
    q = _apply_doc_filters(q, s, e, org_id, branch_id, db)
    q = q.group_by(
        User.id,
        User.full_name,
        User.username,
        User.role,
        Branch.id,
        Branch.name,
        Organization.id,
        Organization.name,
    )
    q = q.having(func.count(distinct(SalesDocument.id)) > 0)
    rows = q.all()

    items = []
    for r in rows:
        txn = int(r.transactions or 0)
        rev = Decimal(str(r.revenue or 0))
        avg_ticket = (rev / Decimal(txn)) if txn > 0 else Decimal("0")
        role_val = r.role.value if hasattr(r.role, "value") else (r.role or "")
        full_name = r.full_name or r.username or f"user_{r.user_id}"
        items.append(
            {
                "user_id": r.user_id,
                "full_name": full_name,
                "role": role_val,
                "branch_id": r.branch_id,
                "branch_name": r.branch_name,
                "org_id": r.org_id,
                "org_name": r.org_name,
                "transactions": txn,
                "revenue": _dec_str(rev),
                "avg_ticket": _dec_str(avg_ticket),
                "active_days": int(r.active_days or 0),
            }
        )
    return items


@router.get("/reports/sellers")
def report_sellers(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = "revenue:desc",
    compare: str = "none",
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)
    field, direction = _parse_sort(sort, SELLER_SORT_FIELDS)
    _validate_compare(compare)

    cache_key = f"sellers:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{limit}:{offset}:{sort}:{compare}"

    def _run():
        items = _sellers_rows(db, s, e, org_id, branch_id)

        def _sort_key(it):
            v = it.get(field)
            if field == "full_name":
                return (v is None, (v or "").lower())
            if v is None:
                return (1, 0.0)
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (1, 0.0)

        items.sort(key=_sort_key, reverse=(direction == "desc"))
        total = len(items)
        page = items[offset : offset + limit]

        prev_window = compare_window(s, e, compare)
        if prev_window is not None:
            prev_s, prev_e = prev_window
            prev_key = f"prevwin:sellers:{prev_s.isoformat()}:{prev_e.isoformat()}:{org_id}:{branch_id}"
            prev_items = _cached(prev_key, lambda: _rows_for_window(db, prev_s, prev_e, org_id, branch_id, pivot="sellers"))
            page = decorate_with_previous(
                page, prev_items,
                key=_COMPARE_KEYS["sellers"], fields=_COMPARE_FIELDS["sellers"],
            )

        return {"items": page, "total": total, "offset": offset, "limit": limit}

    return _cached(cache_key, _run)


# ================================================================== #
# 4. PIVOT: CUSTOMERS                                                #
# ================================================================== #

CUSTOMER_SORT_FIELDS = {
    "ticket_count",
    "total_revenue",
    "avg_ticket",
    "last_purchase",
    "avg_days_between_purchases",
    "customer_name",
}


def _customers_rows(db, s, e, org_id, branch_id) -> list[dict]:
    """Filas agregadas del pivote customers para una ventana, sin ordenar ni paginar."""
    ticket_count = func.count(distinct(SalesDocument.id)).label("ticket_count")
    total_rev = func.coalesce(func.sum(SalesDocument.total_amount), 0).label(
        "total_revenue"
    )
    last_purchase = func.max(SalesDocument.created_at).label("last_purchase")
    first_purchase = func.min(SalesDocument.created_at).label("first_purchase")

    q = (
        db.query(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            ticket_count,
            total_rev,
            last_purchase,
            first_purchase,
        )
        .select_from(SalesDocument)
        .join(Customer, SalesDocument.customer_id == Customer.id)
    )
    q = _apply_doc_filters(q, s, e, org_id, branch_id, db)
    q = q.filter(SalesDocument.customer_id.isnot(None))
    q = q.group_by(Customer.id, Customer.name)
    q = q.having(func.count(distinct(SalesDocument.id)) > 0)
    rows = q.all()

    items = []
    for r in rows:
        tc = int(r.ticket_count or 0)
        rev = Decimal(str(r.total_revenue or 0))
        avg_ticket = (rev / Decimal(tc)) if tc > 0 else Decimal("0")
        avg_gap = None
        if tc >= 2 and r.first_purchase and r.last_purchase:
            delta_seconds = (r.last_purchase - r.first_purchase).total_seconds()
            avg_gap = round(delta_seconds / 86400 / (tc - 1), 2)
        items.append(
            {
                "customer_id": r.customer_id,
                "customer_name": r.customer_name,
                "ticket_count": tc,
                "total_revenue": _dec_str(rev),
                "avg_ticket": _dec_str(avg_ticket),
                "last_purchase": r.last_purchase.isoformat() if r.last_purchase else None,
                "avg_days_between_purchases": avg_gap,
            }
        )
    return items


@router.get("/reports/customers")
def report_customers(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = "total_revenue:desc",
    compare: str = "none",
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)
    # Map "revenue" → "total_revenue" so default "revenue:desc" caller works.
    if sort and sort.split(":")[0] == "revenue":
        sort = "total_revenue:" + (sort.split(":")[1] if ":" in sort else "desc")
    field, direction = _parse_sort(sort, CUSTOMER_SORT_FIELDS)
    _validate_compare(compare)

    cache_key = f"customers:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{limit}:{offset}:{sort}:{compare}"

    def _run():
        items = _customers_rows(db, s, e, org_id, branch_id)

        def _sort_key(it):
            v = it.get(field)
            if field == "customer_name":
                return (v is None, (v or "").lower())
            if field == "last_purchase":
                return (v is None, v or "")
            if v is None:
                return (1, 0.0)
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (1, 0.0)

        items.sort(key=_sort_key, reverse=(direction == "desc"))
        total = len(items)
        page = items[offset : offset + limit]

        prev_window = compare_window(s, e, compare)
        if prev_window is not None:
            prev_s, prev_e = prev_window
            prev_key = f"prevwin:customers:{prev_s.isoformat()}:{prev_e.isoformat()}:{org_id}:{branch_id}"
            prev_items = _cached(prev_key, lambda: _rows_for_window(db, prev_s, prev_e, org_id, branch_id, pivot="customers"))
            page = decorate_with_previous(
                page, prev_items,
                key=_COMPARE_KEYS["customers"], fields=_COMPARE_FIELDS["customers"],
            )

        return {"items": page, "total": total, "offset": offset, "limit": limit}

    return _cached(cache_key, _run)


# ================================================================== #
# 5. DETAIL: PRODUCT                                                 #
# ================================================================== #


@router.get("/reports/products/{product_id}/detail")
def report_product_detail(
    product_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, f"Producto {product_id} no encontrado")

    base = (
        db.query(
            SalesDocument.id.label("document_id"),
            SalesDocument.folio.label("folio"),
            SalesDocument.series.label("series"),
            SalesDocument.created_at.label("created_at"),
            Organization.name.label("org_name"),
            Branch.name.label("branch_name"),
            User.full_name.label("seller_full_name"),
            User.username.label("seller_username"),
            SalesLineItem.quantity.label("quantity"),
            SalesLineItem.unit_price.label("unit_price"),
            SalesLineItem.total_line.label("total_line"),
        )
        .select_from(SalesLineItem)
        .join(SalesDocument, SalesLineItem.document_id == SalesDocument.id)
        .join(ProductVariant, SalesLineItem.variant_id == ProductVariant.id)
        .join(Branch, SalesDocument.branch_id == Branch.id)
        .join(Organization, Branch.organization_id == Organization.id)
        .outerjoin(User, SalesDocument.seller_id == User.id)
        .filter(ProductVariant.product_id == product_id)
    )
    base = _apply_doc_filters(base, s, e, org_id, branch_id, db)

    total = base.count()
    rows = (
        base.order_by(SalesDocument.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []
    for r in rows:
        items.append(
            {
                "document_id": r.document_id,
                "folio": r.folio,
                "series": r.series,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "org_name": r.org_name,
                "branch_name": r.branch_name,
                "seller_name": r.seller_full_name or r.seller_username,
                "quantity": float(r.quantity or 0),
                "unit_price": _dec_str(r.unit_price),
                "total_line": _dec_str(r.total_line),
            }
        )

    return {
        "product_id": product_id,
        "product_name": product.name,
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ================================================================== #
# 6. DETAIL: BRANCH (top products + top sellers)                     #
# ================================================================== #


@router.get("/reports/branches/{branch_id}/detail")
def report_branch_detail(
    branch_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, None, 100)
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(404, f"Sucursal {branch_id} no encontrada")
    org_id = branch.organization_id

    # Top 10 products in this branch.
    units_sold = func.coalesce(func.sum(SalesLineItem.quantity), 0).label("units_sold")
    revenue = func.coalesce(func.sum(SalesLineItem.total_line), 0).label("revenue")
    prod_q = (
        db.query(
            Product.id.label("product_id"),
            Product.name.label("name"),
            ProductVariant.sku.label("sku"),
            units_sold,
            revenue,
        )
        .select_from(SalesLineItem)
        .join(SalesDocument, SalesLineItem.document_id == SalesDocument.id)
        .join(ProductVariant, SalesLineItem.variant_id == ProductVariant.id)
        .join(Product, ProductVariant.product_id == Product.id)
    )
    prod_q = _apply_doc_filters(prod_q, s, e, org_id, branch_id, db)
    prod_q = prod_q.group_by(Product.id, Product.name, ProductVariant.sku)
    prod_q = prod_q.order_by(func.coalesce(func.sum(SalesLineItem.total_line), 0).desc())
    top_products = [
        {
            "product_id": r.product_id,
            "name": r.name,
            "sku": r.sku,
            "units_sold": float(r.units_sold or 0),
            "revenue": _dec_str(r.revenue),
        }
        for r in prod_q.limit(10).all()
    ]

    # Top 5 sellers in this branch.
    transactions = func.count(distinct(SalesDocument.id)).label("transactions")
    sell_revenue = func.coalesce(func.sum(SalesDocument.total_amount), 0).label("revenue")
    sell_q = (
        db.query(
            User.id.label("user_id"),
            User.full_name.label("full_name"),
            User.username.label("username"),
            transactions,
            sell_revenue,
        )
        .select_from(SalesDocument)
        .join(User, SalesDocument.seller_id == User.id)
    )
    sell_q = _apply_doc_filters(sell_q, s, e, org_id, branch_id, db)
    sell_q = sell_q.group_by(User.id, User.full_name, User.username)
    sell_q = sell_q.order_by(func.coalesce(func.sum(SalesDocument.total_amount), 0).desc())
    top_sellers = [
        {
            "user_id": r.user_id,
            "full_name": r.full_name or r.username,
            "transactions": int(r.transactions or 0),
            "revenue": _dec_str(r.revenue),
        }
        for r in sell_q.limit(5).all()
    ]

    return {
        "branch_id": branch_id,
        "branch_name": branch.name,
        "org_id": org_id,
        "top_products": top_products,
        "top_sellers": top_sellers,
    }


# ================================================================== #
# 7. DETAIL: SELLER                                                  #
# ================================================================== #


@router.get("/reports/sellers/{user_id}/detail")
def report_seller_detail(
    user_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, f"Usuario {user_id} no encontrado")

    base = (
        db.query(
            SalesDocument.id.label("document_id"),
            SalesDocument.folio.label("folio"),
            SalesDocument.series.label("series"),
            SalesDocument.created_at.label("created_at"),
            SalesDocument.total_amount.label("total"),
            SalesDocument.status.label("status"),
            SalesDocument.customer_name.label("customer_name"),
            Branch.name.label("branch_name"),
        )
        .select_from(SalesDocument)
        .join(Branch, SalesDocument.branch_id == Branch.id)
        .filter(SalesDocument.seller_id == user_id)
    )
    base = _apply_doc_filters(base, s, e, org_id, branch_id, db)
    total = base.count()
    rows = (
        base.order_by(SalesDocument.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [
        {
            "document_id": r.document_id,
            "folio": r.folio,
            "series": r.series,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "total": _dec_str(r.total),
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "customer_name": r.customer_name,
            "branch_name": r.branch_name,
        }
        for r in rows
    ]
    return {
        "user_id": user_id,
        "full_name": user.full_name or user.username,
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ================================================================== #
# 8. DETAIL: CUSTOMER                                                #
# ================================================================== #


@router.get("/reports/customers/{customer_id}/detail")
def report_customer_detail(
    customer_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, f"Cliente {customer_id} no encontrado")

    # Aggregate first payment method per document via subquery (cheap-ish).
    pm_sub = (
        db.query(
            Payment.sales_document_id.label("doc_id"),
            func.min(Payment.method).label("method"),
        )
        .group_by(Payment.sales_document_id)
        .subquery()
    )

    base = (
        db.query(
            SalesDocument.id.label("document_id"),
            SalesDocument.folio.label("folio"),
            SalesDocument.series.label("series"),
            SalesDocument.created_at.label("created_at"),
            SalesDocument.total_amount.label("total"),
            SalesDocument.status.label("status"),
            Branch.name.label("branch_name"),
            pm_sub.c.method.label("payment_method"),
        )
        .select_from(SalesDocument)
        .join(Branch, SalesDocument.branch_id == Branch.id)
        .outerjoin(pm_sub, pm_sub.c.doc_id == SalesDocument.id)
        .filter(SalesDocument.customer_id == customer_id)
    )
    base = _apply_doc_filters(base, s, e, org_id, branch_id, db)
    total = base.count()
    rows = (
        base.order_by(SalesDocument.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [
        {
            "document_id": r.document_id,
            "folio": r.folio,
            "series": r.series,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "total": _dec_str(r.total),
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "branch_name": r.branch_name,
            "payment_method": (
                r.payment_method.value
                if hasattr(r.payment_method, "value")
                else (r.payment_method or None)
            ),
        }
        for r in rows
    ]
    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ================================================================== #
# 9-12. CSV STREAMING                                                #
# ================================================================== #


def _csv_stream(rows_iter, headers):
    buf = io.StringIO()
    writer = csv.writer(buf)
    # BOM for Excel UTF-8 recognition.
    buf.write("﻿")
    writer.writerow(headers)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()
    for row in rows_iter:
        writer.writerow(row)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()


def _today_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


@router.get("/reports/products.csv")
def export_products_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)

    headers = [
        "product_id",
        "sku",
        "name",
        "brand",
        "department",
        "units_sold",
        "revenue",
        "aov",
        "return_rate_pct",
        "estimated_margin_pct",
    ]
    q = _build_products_query(db, s, e, org_id, branch_id)
    ret_sub = _returned_qty_per_variant(db, s, e, org_id, branch_id)
    ret_per_product = (
        db.query(
            ProductVariant.product_id.label("product_id"),
            func.coalesce(func.sum(ret_sub.c.returned_qty), 0).label("returned_qty"),
        )
        .outerjoin(ret_sub, ret_sub.c.variant_id == ProductVariant.id)
        .group_by(ProductVariant.product_id)
        .subquery()
    )
    returns_map = {
        r.product_id: r.returned_qty
        for r in db.query(ret_per_product.c.product_id, ret_per_product.c.returned_qty).all()
    }

    def _rows():
        for r in q.yield_per(500):
            units = float(r.units_sold or 0)
            rev = Decimal(str(r.revenue or 0))
            aov = (rev / Decimal(str(units))) if units > 0 else Decimal("0")
            ret_qty = float(returns_map.get(r.product_id, 0) or 0)
            return_rate = (ret_qty / units * 100) if units > 0 else 0.0
            yield [
                r.product_id,
                r.sku,
                r.name,
                r.brand or "",
                r.department or "",
                units,
                _dec_str(rev),
                _dec_str(aov),
                _dec_str(return_rate),
                _dec_str_or_none(r.avg_margin) or "",
            ]

    filename = f"report_products_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_rows(), headers),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/branches.csv")
def export_branches_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)

    headers = [
        "branch_id",
        "name",
        "org_id",
        "org_name",
        "city",
        "transactions",
        "revenue",
        "avg_ticket",
        "active_cashiers",
        "return_rate_pct",
    ]

    transactions = func.count(distinct(SalesDocument.id)).label("transactions")
    revenue = func.coalesce(func.sum(SalesDocument.total_amount), 0).label("revenue")
    active_cashiers = func.count(distinct(SalesDocument.seller_id)).label("active_cashiers")
    q = (
        db.query(
            Branch.id.label("branch_id"),
            Branch.name.label("name"),
            Branch.city.label("city"),
            Organization.id.label("org_id"),
            Organization.name.label("org_name"),
            transactions,
            revenue,
            active_cashiers,
        )
        .select_from(SalesDocument)
        .join(Branch, SalesDocument.branch_id == Branch.id)
        .join(Organization, Branch.organization_id == Organization.id)
    )
    q = _apply_doc_filters(q, s, e, org_id, branch_id, db)
    q = q.group_by(Branch.id, Branch.name, Branch.city, Organization.id, Organization.name)
    q = q.having(func.count(distinct(SalesDocument.id)) > 0)

    ret_sub = _returned_qty_per_branch(db, s, e, org_id)
    returns_map = {
        r.branch_id: r.return_count
        for r in db.query(ret_sub.c.branch_id, ret_sub.c.return_count).all()
    }

    def _rows():
        for r in q.yield_per(500):
            txn = int(r.transactions or 0)
            rev = Decimal(str(r.revenue or 0))
            avg_ticket = (rev / Decimal(txn)) if txn > 0 else Decimal("0")
            ret_count = int(returns_map.get(r.branch_id, 0) or 0)
            return_rate = (ret_count / txn * 100) if txn > 0 else 0.0
            yield [
                r.branch_id,
                r.name,
                r.org_id,
                r.org_name,
                r.city or "",
                txn,
                _dec_str(rev),
                _dec_str(avg_ticket),
                int(r.active_cashiers or 0),
                _dec_str(return_rate),
            ]

    filename = f"report_branches_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_rows(), headers),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/sellers.csv")
def export_sellers_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)

    headers = [
        "user_id",
        "full_name",
        "role",
        "branch_id",
        "branch_name",
        "org_id",
        "org_name",
        "transactions",
        "revenue",
        "avg_ticket",
        "active_days",
    ]

    transactions = func.count(distinct(SalesDocument.id)).label("transactions")
    revenue = func.coalesce(func.sum(SalesDocument.total_amount), 0).label("revenue")
    active_days = func.count(distinct(func.date(SalesDocument.created_at))).label(
        "active_days"
    )
    q = (
        db.query(
            User.id.label("user_id"),
            User.full_name.label("full_name"),
            User.username.label("username"),
            User.role.label("role"),
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            Organization.id.label("org_id"),
            Organization.name.label("org_name"),
            transactions,
            revenue,
            active_days,
        )
        .select_from(SalesDocument)
        .join(User, SalesDocument.seller_id == User.id)
        .join(Branch, SalesDocument.branch_id == Branch.id)
        .join(Organization, Branch.organization_id == Organization.id)
    )
    q = _apply_doc_filters(q, s, e, org_id, branch_id, db)
    q = q.group_by(
        User.id,
        User.full_name,
        User.username,
        User.role,
        Branch.id,
        Branch.name,
        Organization.id,
        Organization.name,
    )
    q = q.having(func.count(distinct(SalesDocument.id)) > 0)

    def _rows():
        for r in q.yield_per(500):
            txn = int(r.transactions or 0)
            rev = Decimal(str(r.revenue or 0))
            avg_ticket = (rev / Decimal(txn)) if txn > 0 else Decimal("0")
            role_val = r.role.value if hasattr(r.role, "value") else (r.role or "")
            yield [
                r.user_id,
                r.full_name or r.username or "",
                role_val,
                r.branch_id,
                r.branch_name,
                r.org_id,
                r.org_name,
                txn,
                _dec_str(rev),
                _dec_str(avg_ticket),
                int(r.active_days or 0),
            ]

    filename = f"report_sellers_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_rows(), headers),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/customers.csv")
def export_customers_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    if branch_id is not None and org_id is not None:
        _validate_branch_in_org(db, branch_id, org_id)

    headers = [
        "customer_id",
        "customer_name",
        "ticket_count",
        "total_revenue",
        "avg_ticket",
        "last_purchase",
        "avg_days_between_purchases",
    ]

    ticket_count = func.count(distinct(SalesDocument.id)).label("ticket_count")
    total_rev = func.coalesce(func.sum(SalesDocument.total_amount), 0).label("total_revenue")
    last_purchase = func.max(SalesDocument.created_at).label("last_purchase")
    first_purchase = func.min(SalesDocument.created_at).label("first_purchase")
    q = (
        db.query(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            ticket_count,
            total_rev,
            last_purchase,
            first_purchase,
        )
        .select_from(SalesDocument)
        .join(Customer, SalesDocument.customer_id == Customer.id)
    )
    q = _apply_doc_filters(q, s, e, org_id, branch_id, db)
    q = q.filter(SalesDocument.customer_id.isnot(None))
    q = q.group_by(Customer.id, Customer.name)
    q = q.having(func.count(distinct(SalesDocument.id)) > 0)

    def _rows():
        for r in q.yield_per(500):
            tc = int(r.ticket_count or 0)
            rev = Decimal(str(r.total_revenue or 0))
            avg_ticket = (rev / Decimal(tc)) if tc > 0 else Decimal("0")
            avg_gap = ""
            if tc >= 2 and r.first_purchase and r.last_purchase:
                delta_seconds = (r.last_purchase - r.first_purchase).total_seconds()
                avg_gap = round(delta_seconds / 86400 / (tc - 1), 2)
            yield [
                r.customer_id,
                r.customer_name or "",
                tc,
                _dec_str(rev),
                _dec_str(avg_ticket),
                r.last_purchase.isoformat() if r.last_purchase else "",
                avg_gap,
            ]

    filename = f"report_customers_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_rows(), headers),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
