"""``GET /api/products/search`` and friends — autocomplete-style endpoints
used by the POS, Quote Maker and admin variant pickers.

Sprint 5b split — extracted verbatim from the original ``products.py``.
"""
from __future__ import annotations
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, contains_eager
from sqlalchemy import or_, func
from typing import List, Literal, Optional, Dict, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

# Cache de bestseller ranking — keyed por (org_id, days). Valor: (expires_at, {product_id: score}).
# TTL=300s suficiente: el orden bestseller no cambia en segundos. Ahorra una agregación
# expensive cada búsqueda POS (visible para todos los cajeros simultáneos).
_BESTSELLER_CACHE: Dict[Tuple[int, int], Tuple[float, Dict[str, float]]] = {}
_BESTSELLER_TTL_SECONDS = 300
# Bound del cache: con N orgs × M valores de `days` (cliente puede mandar cualquier int),
# crece sin freno. Audit 2026-05-07. 64 entradas × ~1k productos × 16 bytes ≈ 1 MB tope.
_BESTSELLER_CACHE_MAX = 64


def _bestseller_cache_set(key: Tuple[int, int], value: Tuple[float, Dict[str, float]]) -> None:
    """Insert con cleanup de expirados + cap FIFO. Crude pero suficiente sin dependencias nuevas."""
    now = time.time()
    expired = [k for k, (exp, _) in _BESTSELLER_CACHE.items() if exp <= now]
    for k in expired:
        _BESTSELLER_CACHE.pop(k, None)
    while len(_BESTSELLER_CACHE) >= _BESTSELLER_CACHE_MAX:
        _BESTSELLER_CACHE.pop(next(iter(_BESTSELLER_CACHE)), None)
    _BESTSELLER_CACHE[key] = value


def _get_bestseller_rank(db: Session, org_id: int, days: int) -> Dict[str, float]:
    """Devuelve {product_id: total_qty_vendido} para la org en los últimos `days` días.
    Cacheado en memoria por proceso. Trade-off: un producto recién vendido puede
    no aparecer en bestsellers hasta 5 min después. Aceptable para POS."""
    from app.models.sales import SalesLineItem, SalesDocument, DocumentStatus
    key = (org_id, days)
    now = time.time()
    cached = _BESTSELLER_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]
    since = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (
        db.query(
            ProductVariant.product_id,
            func.coalesce(func.sum(SalesLineItem.quantity), 0),
        )
        .join(SalesLineItem, SalesLineItem.variant_id == ProductVariant.id)
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(
            SalesDocument.organization_id == org_id,
            SalesDocument.created_at >= since,
            SalesDocument.status.notin_([
                DocumentStatus.CANCELLED,
                DocumentStatus.REFUNDED_TOTAL,
            ]),
        )
        .group_by(ProductVariant.product_id)
        .all()
    )
    rank = {pid: float(qty or 0) for pid, qty in rows}
    _bestseller_cache_set(key, (now + _BESTSELLER_TTL_SECONDS, rank))
    return rank

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Product, ProductVariant, StockOnHand, User, PackagingUnit, ProductBranchStatus,
)
from app.core.security import get_current_user
from app.crud.products import query_visible_products, _is_admin
from app.modules.products.schemas import ProductRead, StockLevel

from ._shared import _compute_product_read

logger = logging.getLogger(__name__)

router = APIRouter()


# -----------------------------
# 1.1 Search Variants (Autocomplete)
# -----------------------------
@router.get("/variants/search")
def search_variants(
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Search for variants by SKU or Product Name for autocomplete."""
    if not q or len(q) < 2:
        return []

    s = f"%{q}%"

    # Restringe a productos visibles para el usuario (policy CAJERO/GERENTE).
    visible_pids = query_visible_products(db, current_user, org_id).with_entities(Product.id)
    query = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(Product.id.in_(visible_pids))
        .filter(
            or_(
                ProductVariant.sku.ilike(s),
                Product.name.ilike(s),
                ProductVariant.barcode.ilike(s)
            )
        )
    )

    # .distinct() prevents duplicate variant rows caused by the joinedload on
    # packaging_units (a variant can have N packaging rows).
    query = (
        query.options(
            joinedload(ProductVariant.product),
            joinedload(ProductVariant.packaging_units),
        )
        .distinct(ProductVariant.id)
        .limit(20)
    )

    results = []
    for v in query.all():
        results.append({
            "id": v.id,
            "sku": v.sku,
            "product_name": v.product.name,
            "packaging_units": [
                {
                    "name": p.name,
                    "units_per_package": float(p.units_per_package)
                } for p in v.packaging_units
            ]
        })
    return results


@router.get("/search", response_model=List[ProductRead])
def search_products(
    q: str = "",
    skip: int = 0,
    limit: int = 20,
    department_id: Optional[str] = None,
    stock_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Search products by name or SKU for the Quote Maker / POS.
    Returns GLOBAL STOCK (all branches) for VIP quote management.
    Supports pagination and filters for performance.
    """
    # Visibilidad basada en rol: CAJERO/GERENTE solo ven productos con PBS activo
    # en su sucursal; ADMIN/DUEÑO ven todo. Helper aplica tenant + is_active +
    # approval_status y filtra por branch cuando corresponde.
    query = (
        query_visible_products(
            db,
            current_user,
            org_id,
            search=q if q else None,
        )
        .options(
            joinedload(Product.variants).joinedload(ProductVariant.prices),
            joinedload(Product.variants).joinedload(ProductVariant.packaging_units),
        )
    )

    # Department Filter
    if department_id:
        query = query.filter(Product.department_id == department_id)

    # Get total before pagination for potential "Load More" UI
    products = query.offset(skip).limit(limit).all()

    # Enrich with GLOBAL and LOCAL stock
    results = []

    # Collect variant IDs
    variant_ids = [p.variants[0].id for p in products if p.variants]

    # Fetch ALL stock records for these variants (all branches)
    from app.models.organization import Branch
    all_stocks = []

    if variant_ids:
        all_stocks = db.query(
            StockOnHand.variant_id,
            StockOnHand.qty_on_hand,
            StockOnHand.is_active,
            StockOnHand.branch_id,
            Branch.name.label('branch_name')
        ).join(Branch, StockOnHand.branch_id == Branch.id)\
         .filter(
            StockOnHand.variant_id.in_(variant_ids),
            StockOnHand.organization_id == org_id
        ).all()

        # Fetch is_active_pos from ProductBranchStatus for all variant+branch combos
        all_pbs = db.query(
            ProductBranchStatus.variant_id,
            ProductBranchStatus.branch_id,
            ProductBranchStatus.is_active_pos
        ).filter(
            ProductBranchStatus.variant_id.in_(variant_ids)
        ).all()
        pbs_map = {(r.variant_id, r.branch_id): r.is_active_pos for r in all_pbs}
    else:
        pbs_map = {}

    # Group stocks by variant
    stock_by_variant = {}
    for stock_rec in all_stocks:
        vid = stock_rec.variant_id
        if vid not in stock_by_variant:
            stock_by_variant[vid] = {
                'global_total': Decimal(0),
                'local_qty': Decimal(0),
                'local_active': True,
                'by_branch': []
            }

        stock_by_variant[vid]['global_total'] += stock_rec.qty_on_hand
        stock_by_variant[vid]['by_branch'].append({
            'branch_id': stock_rec.branch_id,
            'branch_name': stock_rec.branch_name,
            'qty': stock_rec.qty_on_hand,
            'is_active': stock_rec.is_active,
            'is_active_pos': pbs_map.get((vid, stock_rec.branch_id))
        })

        # Track local branch (current user's branch)
        if stock_rec.branch_id == current_user.branch_id:
            stock_by_variant[vid]['local_qty'] = stock_rec.qty_on_hand
            stock_by_variant[vid]['local_active'] = stock_rec.is_active

    for p in products:
        if not p.variants:
            continue

        v = p.variants[0]

        # Stock enrichment
        stock_data = stock_by_variant.get(v.id, {
            'global_total': Decimal(0),
            'local_qty': Decimal(0),
            'local_active': True,
            'by_branch': []
        })

        # Apply stock_only filter
        if stock_only and stock_data['global_total'] <= 0:
            continue

        p_read = ProductRead.model_validate(p)

        # Flatten variant data
        p_read.sku = v.sku
        p_read.barcode = v.barcode
        p_read.price = v.price
        p_read.cost = v.cost
        p_read.has_iva = v.has_iva
        p_read.tax_rate = v.tax_rate
        p_read.prices = list(v.prices or [])
        p_read.packaging_units = list(v.packaging_units or [])

        p_read.global_stock = stock_data['global_total']
        p_read.stock_total = stock_data['local_qty']  # Backward compat
        p_read.is_active = stock_data['local_active']

        # Detailed stock levels
        p_read.stock_levels = [
            StockLevel(
                branch_id=b['branch_id'],
                branch_name=b['branch_name'],
                qty_on_hand=b['qty'],
                is_active=b['is_active'],
                is_active_pos=b.get('is_active_pos')
            ) for b in stock_data['by_branch']
        ]

        # Main packaging
        if p_read.packaging_units:
            box = next((pkg for pkg in p_read.packaging_units if pkg.name and "caja" in pkg.name.lower()), None)
            if not box:
                box = max(p_read.packaging_units, key=lambda x: x.units_per_package or 0)
            if box:
                p_read.main_packaging_name = box.name
                p_read.main_packaging_units = box.units_per_package
                p_read.main_packaging_price = box.package_price

        results.append(p_read)

    return results


# -----------------------------
# 5. Búsqueda rápida (CORREGIDA)
# -----------------------------
@router.get("/pos/search", response_model=List[ProductRead])
def search_products_pos(
    q: str,
    order_by: Literal["best_sellers", "name_asc", "price_asc", "price_desc"] = "best_sellers",
    days: int = 30,
    exact: bool = False,
    branch_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    try:
        """
        Devuelve productos POS-friendly:
        - Incluye variants[0].sku y variants[0].price
        - Incluye prices escalonados y departamento
        - Incluye stock_total por sucursal del usuario

        `exact=true` es para el scanner de tienda: el texto viene de un ESCANEO,
        no del teclado, así que compara por igualdad contra los códigos y no por
        `%parcial%`. Con parcial, escanear "750123456789" también trae los
        productos cuyo código lo CONTIENE — en el pasillo eso es editarle el
        precio al producto equivocado. No busca por nombre: un escaneo nunca
        produce un nombre.
        """
        # Sucursal objetivo para el stock. Mismo patrón que `read_products`
        # (core.py): el hint `branch_id` SOLO lo respetan los admins; para
        # cajero/gerente se fuerza la suya, así que el parámetro no sirve para
        # espiar otra tienda. Lo necesita el scanner: un ADMINISTRADOR de HQ
        # tiene branch_id NULL y sin esto el stock siempre volvía 0 — con base
        # 0 un conteo de anaquel se convierte SIEMPRE en entrada y nunca puede
        # registrar un faltante.
        _is_adm = _is_admin(current_user)
        target_branch_id = branch_id if (_is_adm and branch_id) else current_user.branch_id

        # Visibilidad: helper aplica tenant + branch + PBS (anti-ATS-11) según rol.
        # search cubre name/sku; agregamos PackagingUnit.barcode manualmente abajo.
        # En modo exacto NO se le pasa `search`: su ILIKE sobre name/sku/description
        # se combinaría con AND y escondería el producto cuyo barcode empata pero
        # cuyo SKU es otro (el caso normal — códigos de barras y SKUs internos
        # conviven en el mismo catálogo).
        s = f"%{q}%"
        query = (
            query_visible_products(
                db, current_user, org_id,
                search=None if exact else q,
                join_variants=exact,
            )
            .outerjoin(PackagingUnit, ProductVariant.id == PackagingUnit.variant_id)
            .options(
                contains_eager(Product.variants).joinedload(ProductVariant.prices),
                contains_eager(Product.variants).contains_eager(ProductVariant.packaging_units),
                joinedload(Product.department),
            )
        )

        # Extiende búsqueda a barcode de PackagingUnit (el helper ya cubre sku/name/description).
        # Si matchea SOLO por packaging barcode, incluirlo vía OR.
        if exact:
            # El SKU se teclea a mano y buena parte del catálogo lo tiene en
            # minúsculas, así que comparar sensible a mayúsculas obligaría a
            # adivinar cómo se capturó. Los códigos de barras SÍ se comparan
            # exactos: son dígitos, y aflojar ahí sería aflojar la precisión
            # que justifica todo el modo `exact`.
            query = query.filter(
                or_(
                    func.lower(ProductVariant.sku) == q.lower(),
                    ProductVariant.barcode == q,
                    PackagingUnit.barcode == q,
                )
            )
        else:
            query = query.filter(
                or_(
                    Product.name.ilike(s),
                    ProductVariant.sku.ilike(s),
                    ProductVariant.barcode.ilike(s),
                    PackagingUnit.barcode.ilike(s),
                )
            )

        # .distinct() defends against duplicate Product rows introduced by the
        # outerjoin on PackagingUnit (1 variant × N packaging rows) and by
        # contains_eager on variants.packaging_units.
        products_db = query.distinct(Product.id).limit(20).all()

        # --- Ordering (Python-side para no chocar con DISTINCT ON) ---
        if products_db:
            if order_by == "best_sellers":
                # Ranking de toda la org cacheado 5min — evita agregación cada búsqueda.
                rank = _get_bestseller_rank(db, org_id, days)
                products_db.sort(key=lambda p: (-rank.get(p.id, 0.0), (p.name or "").lower()))
            elif order_by == "name_asc":
                products_db.sort(key=lambda p: (p.name or "").lower())
            elif order_by in ("price_asc", "price_desc"):
                def _price(p):
                    try:
                        return float(p.variants[0].price) if p.variants else 0.0
                    except Exception:
                        return 0.0
                products_db.sort(key=_price, reverse=(order_by == "price_desc"))

        # --- Batch: Stock + BranchStatus caches (avoid N+1) ---
        variant_ids = [p.variants[0].id for p in products_db if p.variants]

        stock_cache = {}
        branch_statuses_cache = {}
        if variant_ids:
            stocks = (
                db.query(StockOnHand.variant_id, StockOnHand.qty_on_hand, StockOnHand.is_active)
                .filter(
                    StockOnHand.variant_id.in_(variant_ids),
                    StockOnHand.branch_id == target_branch_id,
                    StockOnHand.organization_id == org_id,
                )
                .all()
            )
            stock_cache = {s.variant_id: (s.qty_on_hand, s.is_active) for s in stocks}

            all_statuses = (
                db.query(ProductBranchStatus)
                .filter(
                    ProductBranchStatus.variant_id.in_(variant_ids),
                    ProductBranchStatus.organization_id == org_id,
                )
                .all()
            )
            for bs in all_statuses:
                branch_statuses_cache.setdefault(bs.variant_id, []).append(bs)

        return [
            _compute_product_read(
                p, db, current_user, stock_cache, target_branch_id,
                branch_statuses_cache=branch_statuses_cache,
            )
            for p in products_db
        ]
    except Exception as e:
        logger.exception("SEARCH_PRODUCTS_FAILED org_id=%s query=%s", org_id, q)
        raise HTTPException(status_code=500, detail="Error al buscar productos. Intente de nuevo.")
