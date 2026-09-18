"""Shared imports, helpers, schemas and constants used across the
``app.routers.products`` sub-package.

Created by the Sprint 5b split of the original 3.4k-line ``products.py``.
Single source of truth for helpers that two or more sub-modules need
(role gate, ProductRead enrichment, Excel-row coercers).
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload, contains_eager, selectinload
from typing import List, Literal, Optional
from decimal import Decimal
from sqlalchemy import or_, and_, func
import io
import csv
import math
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import (
    Product, ProductVariant, StockOnHand, User,
    InventoryMovement, MovementType, Department, ProductPrice,
    PackagingUnit, Brand, ProductBranchStatus
)
from app.models.organization import Branch, BranchType
from app.crud.products import (
    query_visible_products,
    get_product_if_visible,
    get_variant_if_visible,
    _is_admin,
    resolve_pbs_target_branch,
    update_branch_override,
    assert_variants_belong_to_org,
    assert_branches_belong_to_org,
    log_pbs_change,
)
from app.modules.products.schemas import (
    ProductCreate, ProductRead, ProductUpdate,
    DepartmentRead, StockLevel, BatchActionRequest, ProductListResponse,
    BranchStatusUpdate, PBSResponse,
    BulkToggleBranchStatusRequest, BranchStatusFlagsUpdate, PackagingUpdate,
    PbsCloneRequest, PbsCloneResponse,
)
from app.schemas.departments import (
    DepartmentCreate, DepartmentUpdate, DepartmentResponse,
)
from app.schemas.brands import BrandCreate, BrandUpdate, BrandResponse
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization

logger = logging.getLogger(__name__)

_MANAGER_ROLES: frozenset = frozenset({"ADMINISTRADOR", "GERENTE", "DUEÑO"})

# Track 3 (POS bug-fix): el cajero es el usuario con más control en tiendas.
# Tiene CRUD completo + bulk + import/export + approve/reject/restore sobre
# productos visibles en su sucursal. La invariante multi-tenant
# (organization_id == current_user.org_id) y el scope de sucursal
# (CAJERO solo actúa sobre PBS de su branch_id) se siguen aplicando en
# las funciones de bajo nivel (`get_product_if_visible`, `resolve_pbs_target_branch`).
_PRODUCT_ADVANCED_ROLES: frozenset = frozenset(
    {"ADMINISTRADOR", "GERENTE", "DUEÑO", "CAJERO"}
)

CRITICAL_STOCK_THRESHOLD = 5


def variantes_vivas(product: Product) -> list:
    """Variantes del producto que siguen vendibles (sin soft-delete)."""
    return [v for v in (product.variants or []) if v.deleted_at is None]


def variante_principal(product: Product):
    """La variante "principal": la primera VIVA en orden de creacion.

    `product.variants[0]` incluye las retiradas (`DELETE /variants/{id}`), asi
    que despues de retirar la primera talla las rutas de escritura terminaban
    editando una variante que ya no se vende. None si no queda ninguna viva.
    """
    vivas = variantes_vivas(product)
    return vivas[0] if vivas else None


def _compute_product_read(
    p: Product,
    db: Session,
    current_user: User,
    stock_cache: dict[str, Decimal] = None,
    target_branch_id: int = None,
    branch_statuses_cache: dict[str, list] = None,
    primary_variant_id: Optional[str] = None,
) -> ProductRead:
    """
    Convierte ORM Product -> ProductRead y agrega:
    - prices (de la variante principal)
    - stock_total / stock_levels
    - branch_statuses (usa cache batch si está disponible para evitar N+1)
    """
    p_read = ProductRead.model_validate(p)

    # Las variantes retiradas (soft-delete, `DELETE /variants/{id}`) ya no se
    # pueden vender ni editar -- no viajan al frontend, o el POS/la matriz
    # las mostraria como si siguieran vivas.
    p_read.variants = [
        vr for vr, orm in zip(p_read.variants, p.variants) if orm.deleted_at is None
    ]

    # ATS-12: Campos aplanados que el template POS consume directamente
    p_read.department_name = p.department.name if p.department else None
    p_read.brand_id = p.brand_id
    p_read.brand_name = p.brand.name if p.brand else None

    # Determinar qué sucursal mostrar: La solicitada o la del usuario
    real_branch_id = target_branch_id if target_branch_id is not None else current_user.branch_id

    # Multi-tenancy: todo lo que se consulte por variante se acota ademas a la
    # org del producto (los `variant_id` son UUID, pero el filtro es la regla).
    org_de_p = p.organization_id

    vivas = variantes_vivas(p)
    if vivas:
        # La variante "principal" es la pedida (p. ej. la que empato un
        # escaneo) o, si no, la primera viva en orden de creacion.
        v = next((x for x in vivas if x.id == primary_variant_id), vivas[0])
        # `matched_variant_id` SOLO cuando hubo empate real: el POS lo usa como
        # senal de "ya se que talla es" (`needsPicker`). Si lo fijamos siempre,
        # el selector de talla nunca abre y se vende `variants[0]`.
        p_read.matched_variant_id = (
            v.id if (primary_variant_id and v.id == primary_variant_id) else None
        )
        p_read.sku = v.sku
        p_read.barcode = v.barcode
        p_read.price = v.price
        p_read.cost = v.cost
        p_read.has_iva = v.has_iva
        p_read.tax_rate = v.tax_rate

        # Precios escalonados de la variante principal
        p_read.prices = list(v.prices or [])

        # Empaques de la variante principal
        p_read.packaging_units = list(v.packaging_units or [])

        # Cache de stock: puede traer Decimal o Tupla (qty, is_active)
        # segun el caller. Un solo lugar para desempacarlo.
        def _qty(val):
            if isinstance(val, tuple):
                return val[0] or Decimal(0)
            return val or Decimal(0)

        # Stock por sucursal objetivo
        qty = Decimal(0)
        is_active = True # Default en código, aunque en BD es True

        if stock_cache is not None:
             val = stock_cache.get(v.id)
             qty = _qty(val)
             if isinstance(val, tuple):
                 is_active = val[1] if val[1] is not None else True
        else:
            # Fallback a query individual (si no se usa cache)
            # Solo consultamos si hay un ID de sucursal válido (puede ser None para usuarios globales sin sucursal)
            if real_branch_id:
                q_stock = db.query(StockOnHand).filter(
                    StockOnHand.variant_id == v.id,
                    StockOnHand.branch_id == real_branch_id,
                )
                if org_de_p is not None:
                    q_stock = q_stock.filter(StockOnHand.organization_id == org_de_p)
                stock = q_stock.first()
                qty = stock.qty_on_hand if stock else Decimal(0)
                is_active = stock.is_active if (stock and stock.is_active is not None) else True

        p_read.stock_total = qty
        # [FIX] NO sobreescribir p_read.is_active con el flag de stock tracking.
        # p_read.is_active ya viene del producto ORM (Product.is_active) via model_validate.
        p_read.stock_levels = []
        if real_branch_id:
            pbs = (
                db.query(ProductBranchStatus)
                .filter(
                    ProductBranchStatus.variant_id == v.id,
                    ProductBranchStatus.branch_id == real_branch_id
                )
                .first()
            )
            p_read.stock_levels.append(
                StockLevel(
                    branch_id=real_branch_id,
                    qty_on_hand=qty,
                    is_active=is_active,
                    is_active_pos=pbs.is_active_pos if pbs else None
                )
            )

        # Determinar "Caja" principal para UI
        box = None
        if p_read.packaging_units:
            # Buscar explícitamente "Caja"
            box = next((pkg for pkg in p_read.packaging_units if pkg.name and "caja" in pkg.name.lower()), None)
            # Si no hay "Caja", usar el de mayor capacidad
            if not box:
                 box = max(p_read.packaging_units, key=lambda x: x.units_per_package or 0)

        if box:
            p_read.main_packaging_name = box.name
            p_read.main_packaging_units = box.units_per_package
            p_read.main_packaging_price = box.package_price

        # [FIX] Load Branch Statuses para la Matriz Comercial.
        # Si viene un cache batch (precargado en read_products) lo usamos directamente.
        # Si no, hacemos la query individual (fallback para read_product y otros callers).
        if branch_statuses_cache is not None:
            p_read.branch_statuses = branch_statuses_cache.get(v.id, [])
        else:
            p_read.branch_statuses = db.query(ProductBranchStatus).filter(
                ProductBranchStatus.variant_id == v.id
            ).all()

        # [PRICE OVERRIDE] Aplicar precio fijo de sucursal si está configurado.
        # Tiene precedencia sobre el precio base y anula los precios escalonados.
        if real_branch_id:
            bs_for_branch = next(
                (bs for bs in p_read.branch_statuses if bs.branch_id == real_branch_id),
                None
            )
            if bs_for_branch and bs_for_branch.price_override is not None:
                p_read.price = bs_for_branch.price_override
                p_read.prices = []  # Tier prices don't apply when override is active

        # Existencia por variante en la sucursal objetivo. Con una sola
        # variante coincide con stock_total; con varias es lo que permite al
        # POS mostrar cuantas piezas hay de cada talla.
        if stock_cache is not None:
            # El caller ya precargo el batch (core.py/search.py/reports.py
            # cachean TODAS las variantes de la pagina). Si una variante no
            # aparece ahi es porque no tiene stock en la sucursal objetivo:
            # NO disparamos una query por variante (evitaria el N+1 que el
            # cache batch existe para prevenir).
            for vr in p_read.variants:
                vr.stock_total = _qty(stock_cache.get(vr.id))
        elif real_branch_id:
            # Sin cache (callers de un solo producto, p. ej. read_product):
            # una sola query cubre todas las variantes de este producto.
            directo: dict[str, Decimal] = {}
            q_directo = db.query(StockOnHand.variant_id, StockOnHand.qty_on_hand).filter(
                StockOnHand.variant_id.in_([vr.id for vr in p_read.variants]),
                StockOnHand.branch_id == real_branch_id,
            )
            if org_de_p is not None:
                q_directo = q_directo.filter(StockOnHand.organization_id == org_de_p)
            for row in q_directo.all():
                directo[row.variant_id] = row.qty_on_hand
            for vr in p_read.variants:
                vr.stock_total = directo.get(vr.id, Decimal(0))

    return p_read


def _safe_str(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan":
        return ""
    return s


def _is_na(val) -> bool:
    """Return True when a cell value from openpyxl/csv should be treated as missing."""
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str) and val.strip().lower() in ("nan", "none"):
        return True
    return False


def _safe_decimal(val, default: Decimal = Decimal(0)) -> Decimal:
    try:
        if _is_na(val):
            return default
        return Decimal(str(val))
    except Exception:
        return default
