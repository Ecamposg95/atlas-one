# app/routers/sales.py
"""
MOONSHOT_ENGINE: Transaction Engine
DOMAIN: Sales / POS
STATUS: Active (MVP Critical)
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import csv
import io
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, false as sql_false
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

# Asegúrate de que estas importaciones coincidan con la estructura de tu proyecto
from app.core.database import get_db
import logging
from app.models import (
    ProductVariant, StockOnHand, InventoryMovement, Product, Branch,
    SalesDocument, SalesLineItem, Payment,
    User, DocumentType, DocumentStatus, MovementType,
    Customer, CustomerLedgerEntry, PaymentMethod,
    CashSession, CashSessionStatus,
    ParkedTicket,
)

logger = logging.getLogger(__name__)


def _safe_sale_items(doc) -> "List[Dict[str, Any]]":
    """Build the SalesDocumentCreated payload without ever raising.

    Previously this was an inline comprehension using ``l.variant.sku``; a single
    line whose variant relationship was null threw AttributeError, the publish was
    swallowed by ``except: pass``, and NEITHER ingredient consumption NOR the
    table-free ran — silently. Defensive access removes that landmine.
    """
    items: "List[Dict[str, Any]]" = []
    for l in (getattr(doc, "lines", None) or []):
        variant = getattr(l, "variant", None)
        vid = getattr(l, "variant_id", None)
        qty = getattr(l, "quantity", None)
        items.append({
            "variant_id": str(vid) if vid else None,
            "quantity": float(qty) if qty is not None else 0.0,
            "sku": getattr(variant, "sku", None),
        })
    return items


from app.models.returns import SaleReturn, SaleReturnItem
from app.schemas.sales import SaleCreate, SaleRead
from app.core.security import get_current_user
# --- NUEVA IMPORTACIÓN PARA FOLIOS ---
from app.utils.folios import get_next_folio
from app.core.events import EventBus, SalesDocumentCreated # [NEW] Event Bus Integration
from app.core.tenant_context import get_current_active_organization
from app.models.organization import Organization
from app.services.tax import compute_line_tax, quantize_amount, quantize_totals, resolve_org_tax_mode
from app.crud.products import get_variant_if_visible
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

MX_TZ = ZoneInfo("America/Mexico_City")

from app.core.permissions import require_module

# Máximo descuento permitido por línea para roles no-admin (CAJERO/GERENTE/etc.)
# Rechazamos ventas donde unit_price < reference_price * (1 - MAX_DISCOUNT_PCT).
# Futuro: mover a Organization settings.
MAX_DISCOUNT_PCT = Decimal("0.50")


def _is_hq_role(current_user: User) -> bool:
    """HQ roles see all branches in the org. Branch users (GERENTE, CAJERO, …)
    only their own. SUPERADMIN platform-role bypasses everything."""
    user_role_str = (
        str(current_user.role.value) if hasattr(current_user.role, 'value')
        else str(current_user.role)
    )
    if hasattr(current_user, 'platform_role'):
        p_role = (
            str(current_user.platform_role.value)
            if hasattr(current_user.platform_role, 'value')
            else str(current_user.platform_role)
        )
        if p_role == "SUPERADMIN":
            return True
    return user_role_str in ("ADMINISTRADOR", "DUEÑO")


def _assert_sale_branch_access(sale: SalesDocument, current_user: User) -> None:
    """Raise 404 if `current_user` cannot access this sale's branch.

    Returns 404 (not 403) so we don't leak existence of sales in branches the
    user has no business knowing about — a CAJERO enumerating folios should
    not be able to distinguish "exists but I'm not allowed" from "does not exist".

    Legacy compat: sales created before sale.branch_id was reliably populated
    (e.g. during 2026-Q1 migrations) may have NULL branch_id. We treat NULL as
    org-wide and let any user of the same org print/reprint — the org_id check
    in the caller already prevents cross-tenant access. This keeps reprints
    working for old folios while the new RBAC gate still blocks the cross-
    branch leak that this guard was added to fix (audit C-4).
    """
    if _is_hq_role(current_user):
        return
    if current_user.branch_id is None:
        logger.warning(
            "BRANCH_GATE_DENY: user_id=%s username=%s role=%s reason=user_branch_null sale_id=%s sale_branch_id=%s",
            getattr(current_user, "id", None),
            getattr(current_user, "username", None),
            getattr(current_user, "role", None),
            getattr(sale, "id", None),
            getattr(sale, "branch_id", None),
        )
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if sale.branch_id is None:
        logger.info(
            "BRANCH_GATE_LEGACY_PASS: sale_id=%s has NULL branch_id, allowing user_id=%s branch_id=%s",
            getattr(sale, "id", None),
            getattr(current_user, "id", None),
            current_user.branch_id,
        )
        return
    if sale.branch_id != current_user.branch_id:
        logger.warning(
            "BRANCH_GATE_DENY: user_id=%s username=%s role=%s user_branch_id=%s sale_id=%s sale_branch_id=%s reason=branch_mismatch",
            getattr(current_user, "id", None),
            getattr(current_user, "username", None),
            getattr(current_user, "role", None),
            current_user.branch_id,
            getattr(sale, "id", None),
            sale.branch_id,
        )
        raise HTTPException(status_code=404, detail="Venta no encontrada")


router = APIRouter(dependencies=[Depends(require_module("pos"))])
templates = Jinja2Templates(directory="app/templates")

@router.get("/stats")
def get_sales_stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    branch_id: Optional[int] = None, # [NEW] HQ Filter
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Calcula KPIs de ventas: Total, Cantidad, Ticket Promedio, Desglose por Método.
    """
    # ATS-6: misma lógica de scoping que read_sales
    _role_str = str(current_user.role.value) if hasattr(current_user.role, 'value') else str(current_user.role)
    _is_hq = _role_str in ["ADMINISTRADOR", "DUEÑO"]
    if hasattr(current_user, 'platform_role'):
        _pr = str(current_user.platform_role.value) if hasattr(current_user.platform_role, 'value') else str(current_user.platform_role)
        if _pr == "SUPERADMIN":
            _is_hq = True

    # Calcular target_branch_id según el rol
    if _is_hq:
        target_branch_id = branch_id if (branch_id and branch_id > 0) else None
    else:
        target_branch_id = current_user.branch_id

    # Base Query
    query = db.query(SalesDocument).filter(
        SalesDocument.organization_id == org_id,
        SalesDocument.status != DocumentStatus.CANCELLED,
        SalesDocument.doc_type == DocumentType.INVOICE
    )

    if target_branch_id:
        query = query.filter(SalesDocument.branch_id == target_branch_id)

    if start_date:
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=MX_TZ)
        query = query.filter(SalesDocument.created_at >= start_date)
    if end_date:
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=MX_TZ)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(SalesDocument.created_at <= end_date)

    # 1. KPIs Generales
    total_sales = query.with_entities(func.sum(SalesDocument.total_amount)).scalar() or Decimal(0)
    total_count = query.count()
    avg_ticket = total_sales / total_count if total_count > 0 else Decimal(0)

    # 2. Desglose por Método de Pago
    payment_stats_query = (
        db.query(Payment.method, func.sum(Payment.amount))
        .join(SalesDocument)
        .filter(
            SalesDocument.organization_id == org_id,
            SalesDocument.status != DocumentStatus.CANCELLED,
            SalesDocument.doc_type == DocumentType.INVOICE
        )
    )

    if target_branch_id:
        payment_stats_query = payment_stats_query.filter(SalesDocument.branch_id == target_branch_id)

    if start_date:
        payment_stats_query = payment_stats_query.filter(SalesDocument.created_at >= start_date)
    if end_date:
        payment_stats_query = payment_stats_query.filter(SalesDocument.created_at <= end_date)
        # end_date ya ajustado a 23:59:59 arriba

    payment_stats = payment_stats_query.group_by(Payment.method).all()

    methods_data = {method.value: float(amount) for method, amount in payment_stats}

    # 3. Devoluciones — count + total refunded across the period
    refunds_query = db.query(SaleReturn).filter(
        SaleReturn.organization_id == org_id,
        SaleReturn.status == "APPROVED",
    )
    if target_branch_id:
        refunds_query = refunds_query.filter(SaleReturn.branch_id == target_branch_id)
    if start_date:
        refunds_query = refunds_query.filter(SaleReturn.created_at >= start_date)
    if end_date:
        refunds_query = refunds_query.filter(SaleReturn.created_at <= end_date)

    refund_count = refunds_query.count()
    refund_total = refunds_query.with_entities(
        func.coalesce(func.sum(SaleReturn.total_refunded), Decimal(0))
    ).scalar() or Decimal(0)

    # 4. Hora pico — hour of day with most PAID sales in the period
    peak_query = (
        db.query(
            func.extract('hour', func.timezone('America/Mexico_City', SalesDocument.created_at)).label('hr'),
            func.count(SalesDocument.id).label('n'),
        )
        .filter(
            SalesDocument.organization_id == org_id,
            SalesDocument.status == DocumentStatus.PAID,
            SalesDocument.doc_type == DocumentType.INVOICE,
        )
    )
    if target_branch_id:
        peak_query = peak_query.filter(SalesDocument.branch_id == target_branch_id)
    if start_date:
        peak_query = peak_query.filter(SalesDocument.created_at >= start_date)
    if end_date:
        peak_query = peak_query.filter(SalesDocument.created_at <= end_date)

    peak_row = peak_query.group_by('hr').order_by(func.count(SalesDocument.id).desc()).first()
    peak_hour = f"{int(peak_row.hr):02d}:00" if peak_row else None

    return {
        "total_sales": float(total_sales),
        "total_transactions": total_count,
        "average_ticket": float(avg_ticket),
        "payment_methods": methods_data,
        "refund_count": int(refund_count),
        "refund_total": float(refund_total),
        "peak_hour": peak_hour,
    }

@router.get("", response_model=Dict[str, Any], include_in_schema=False)
@router.get("/", response_model=Dict[str, Any])
def read_sales(
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[DocumentStatus] = None,
    customer_id: Optional[int] = None,
    branch_id: Optional[int] = None, # [NEW] HQ Filter
    doc_type: Optional[List[DocumentType]] = Query(None),
    folio_search: Optional[str] = Query(
        None,
        description="Busca por folio exacto, tolerante al formato: '540', 'a-540', 'A-0540'.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    # ATS-6: branch scoping — normalizar rol a string una sola vez
    user_role_str = str(current_user.role.value) if hasattr(current_user.role, 'value') else str(current_user.role)

    is_superadmin = False
    if hasattr(current_user, 'platform_role'):
        p_role = str(current_user.platform_role.value) if hasattr(current_user.platform_role, 'value') else str(current_user.platform_role)
        if p_role == "SUPERADMIN":
            is_superadmin = True

    # Roles HQ: visibilidad global (pueden filtrar por sucursal específica con branch_id)
    # GERENTE es BRANCH-scoped — solo ve su propia sucursal
    is_hq_role = is_superadmin or user_role_str in ["ADMINISTRADOR", "DUEÑO"]

    query = db.query(SalesDocument).filter(SalesDocument.organization_id == org_id)

    if is_hq_role:
        # HQ: global por defecto, o filtrado por sucursal si se especifica
        if branch_id is not None and branch_id > 0:
            query = query.filter(SalesDocument.branch_id == branch_id)
        # branch_id=None → vista global
    else:
        # Usuarios branch-scoped (GERENTE, CAJERO, VENDEDOR, etc.): siempre su sucursal
        query = query.filter(SalesDocument.branch_id == current_user.branch_id)

    if doc_type:
        query = query.filter(SalesDocument.doc_type.in_(doc_type))

    if start_date:
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=MX_TZ)
        query = query.filter(SalesDocument.created_at >= start_date)
    if end_date:
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=MX_TZ)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(SalesDocument.created_at <= end_date)
    if status is not None:
        query = query.filter(SalesDocument.status == status)
    if customer_id is not None:
        query = query.filter(SalesDocument.customer_id == customer_id)

    # Devoluciones buscan un ticket exacto por folio. El POS lo muestra como
    # "A-0540" (saleLabel hace padStart(4)), y muchas veces se teclea sólo el
    # número o sin los ceros a la izquierda ("540" o "a-540"). Se extraen los
    # dígitos (los ceros a la izquierda mueren solos al convertir a int) y, si
    # además escribió serie, se filtra también por ella. Sin dígitos no hay
    # folio que buscar: se fuerza vacío en vez de ignorar el filtro y devolver
    # TODA la lista (que sería engañoso para quien está buscando un ticket).
    if folio_search is not None and folio_search.strip():
        raw = folio_search.strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            query = query.filter(sql_false())
        else:
            query = query.filter(SalesDocument.folio == int(digits))
            letters = "".join(ch for ch in raw if ch.isalpha())
            if letters:
                query = query.filter(func.upper(SalesDocument.series) == letters.upper())

    # Count before adding eager-load options (joinedload inflates count)
    total = query.count()

    # Optimización: Cargar relaciones para evitar N+1 y completar el esquema
    from sqlalchemy.orm import selectinload
    query = query.options(
        joinedload(SalesDocument.lines).joinedload(SalesLineItem.variant),
        joinedload(SalesDocument.payments),
        selectinload(SalesDocument.returns).selectinload(SaleReturn.items).joinedload(SaleReturnItem.variant)
    )

    # Order by newest first
    sales = query.order_by(SalesDocument.created_at.desc()).offset(skip).limit(limit).all()

    pages = max(1, -(-total // limit)) if limit else 1
    items = [SaleRead.model_validate(s) for s in sales]
    return {"items": items, "total": total, "page": skip // limit if limit else 0, "pages": pages}

@router.post("", response_model=Dict[str, Any], include_in_schema=False)
def _line_description(variant) -> str:
    """Descripcion del renglon de venta: nombre del producto y, si la variante
    tiene un nombre propio distinto del estandar, ese nombre entre parentesis.
    """
    nombre = variant.product.name or ""
    variante = (variant.variant_name or "").strip()
    if variante and variante != "Estándar":
        return f"{nombre} ({variante})"
    return nombre


def _respuesta_de_venta_existente(db: Session, sale: SalesDocument) -> Dict[str, Any]:
    """Respuesta del checkout para una venta que ya existía (reenvío idempotente).

    Misma forma que el alta normal, para que el POS no tenga que distinguir
    entre "se registró ahora" y "ya estaba registrada".
    """
    pagado = db.query(
        func.coalesce(func.sum(Payment.amount), Decimal("0"))
    ).filter(Payment.sales_document_id == sale.id).scalar() or Decimal("0")
    total = Decimal(str(sale.total_amount or 0)).quantize(Decimal("0.01"))
    return {
        "status": "success",
        "sale_id": sale.id,
        "folio": f"{sale.series}-{sale.folio}",
        "total": float(total),
        "paid": float(Decimal(str(pagado)).quantize(Decimal("0.01"))),
        "change": float(Decimal(str(sale.change_given or 0)).quantize(Decimal("0.01"))),
        "credit_debt": 0.0,
        # Misma forma que el alta normal: el POS no distingue.
        "usd_rate": float(sale.usd_rate) if sale.usd_rate is not None else None,
        "duplicate_ignored": True,
    }


@router.post("/", response_model=Dict[str, Any])
def create_sale(
    sale_in: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Registra una nueva venta o actualiza una existente (PENDING).
    Maneja descuento de stock, créditos y pagos.
    """
    if not sale_in.items:
        raise HTTPException(status_code=400, detail="El ticket está vacío")

    # Idempotencia del checkout. El POS guarda las ventas que no pudo confirmar
    # y las reenvía con el MISMO client_uuid; si la venta sí entró y solo se
    # perdió la respuesta, aquí se devuelve la original en vez de cobrar y
    # descontar inventario por segunda vez.
    if sale_in.client_uuid:
        previa = db.query(SalesDocument).filter(
            SalesDocument.organization_id == org_id,
            SalesDocument.client_uuid == sale_in.client_uuid,
        ).first()
        if previa is not None:
            return _respuesta_de_venta_existente(db, previa)

    # --- Guard 2: Branch required for sales with payments ---
    if sale_in.payments and not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Los usuarios de oficina central no pueden procesar cobros directamente. Use el módulo de ventas."
        )

    # --- H-2 guard: rango del descuento global (0..50). >50 requiere supervisor. ---
    global_disc_pct = Decimal(str(sale_in.global_discount_pct or 0))
    if global_disc_pct < Decimal("0") or global_disc_pct > Decimal("50"):
        raise HTTPException(
            status_code=422,
            detail="Descuento global fuera de rango (0–50%). Excedentes requieren autorización."
        )

    # --- 0b. Cash session gate (H-5) ---
    # El efectivo es fisico y no admite excepciones de rol: si esta venta mete
    # billetes en un cajon de sucursal, tiene que haber una caja abierta que
    # responda por ellos. La exencion historica para roles HQ se conserva solo
    # para lo que NO toca el cajon (tarjeta, transferencia, credito), que es el
    # caso de back-office/migracion para el que se escribio.
    cobra_efectivo = any(
        str(getattr(p.method, "value", p.method)).upper() == "CASH"
        for p in (sale_in.payments or [])
    )
    requiere_caja = bool(current_user.branch_id) and (
        cobra_efectivo or not _is_hq_role(current_user)
    )
    if requiere_caja:
        active_session = db.query(CashSession).filter(
            CashSession.user_id == current_user.id,
            CashSession.branch_id == current_user.branch_id,
            CashSession.status == CashSessionStatus.OPEN,
        ).first()
        if not active_session:
            logger.warning(
                "BLOCKED_CHECKOUT: user_id=%s branch_id=%s pending_sale_id=%s reason=%s",
                current_user.id, current_user.branch_id, sale_in.id,
                "no_open_cash_session_cash_payment" if cobra_efectivo else "no_open_cash_session",
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    "Debes abrir caja antes de cobrar en efectivo"
                    if cobra_efectivo
                    else "Debes abrir caja antes de registrar ventas"
                ),
            )

    # --- 0. Verificar si es una actualización de una venta existente ---
    existing_sale = None
    if sale_in.id:
        existing_sale = db.query(SalesDocument).filter(
            SalesDocument.id == sale_in.id,
            SalesDocument.organization_id == org_id
        ).first()
        
        if existing_sale:
            if existing_sale.status != DocumentStatus.PENDING:
                raise HTTPException(status_code=400, detail="Solo se pueden modificar ventas con estatus PENDING")
            
            # --- REVERTIR STOCK EXISTENTE ---
            for old_line in existing_sale.lines:
                stock_old = db.query(StockOnHand).filter(
                    StockOnHand.variant_id == old_line.variant_id,
                    StockOnHand.branch_id == existing_sale.branch_id,
                    StockOnHand.organization_id == org_id
                ).first()
                if stock_old:
                    stock_old.qty_on_hand += Decimal(str(old_line.quantity))
                    # Omitimos movimiento de reversión para no ensuciar el kardex si es un update inmediato
            
            # Limpiar líneas y pagos anteriores
            db.query(SalesLineItem).filter(SalesLineItem.document_id == existing_sale.id).delete()
            db.query(Payment).filter(Payment.sales_document_id == existing_sale.id).delete()

    # --- 1. Cálculos de Stock y Precios ---
    total_sale = Decimal("0.00")
    accumulated_subtotal = Decimal("0.00")
    accumulated_tax = Decimal("0.00")
    db_lines = []

    # Modo de precio de la organización (neto vs. precio con IVA incluido). Se
    # resuelve una sola vez y lo consume compute_line_tax por renglón.
    price_includes_tax = resolve_org_tax_mode(
        db.query(Organization).filter(Organization.id == org_id).first()
    )

    # --- BATCH RESOLVE (perf 2026-05-07) ---
    # Antes: 4 queries × N items (variant lookup + eager re-fetch + stock + PBS).
    # Ahora: 3 queries totales (variants con eager-load + visibilidad, stock bulk, PBS bulk).
    # Para ventas de 10 items: ~40 queries → ~3-5 queries. Submit baja de 1-2s a <300ms.
    from sqlalchemy import or_, and_
    from app.models.products import ProductBranchStatus

    requested_variant_ids = [getattr(i, "variant_id", None) for i in sale_in.items if getattr(i, "variant_id", None)]
    requested_skus = [i.sku for i in sale_in.items if not getattr(i, "variant_id", None)]

    _role_str = str(current_user.role.value) if hasattr(current_user.role, "value") else str(current_user.role)
    # Paridad 1:1 con app/crud/products.py:_is_admin (audit 2026-05-07).
    # SUPERADMIN no se trata como admin aquí; si el SUPERADMIN cajea, debe
    # seguir respetando la visibilidad PBS de su sucursal igual que antes.
    _is_admin_role = _role_str in ("ADMINISTRADOR", "DUEÑO")

    vq = (
        db.query(ProductVariant)
        .options(joinedload(ProductVariant.prices), joinedload(ProductVariant.product))
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(Product.organization_id == org_id)
    )
    match_filters = []
    if requested_variant_ids:
        match_filters.append(ProductVariant.id.in_(requested_variant_ids))
    if requested_skus:
        match_filters.append(ProductVariant.sku.in_(requested_skus))
    if match_filters:
        vq = vq.filter(or_(*match_filters))

    # Cashier visibility (anti-ATS-11): mismo gate que `get_variant_if_visible`,
    # pero aplicado bulk con join a PBS.
    if not _is_admin_role:
        _branch_check = db.query(Branch).filter(Branch.id == current_user.branch_id).first()
        if _branch_check is None or not _branch_check.can_sell:
            raise HTTPException(status_code=404, detail="Sucursal no autorizada para vender")
        vq = vq.filter(Product.is_active.is_(True)).join(
            ProductBranchStatus,
            and_(
                ProductBranchStatus.variant_id == ProductVariant.id,
                ProductBranchStatus.branch_id == current_user.branch_id,
                ProductBranchStatus.is_active_pos.is_(True),
            ),
        )

    variants_list = vq.all()
    variants_by_id = {v.id: v for v in variants_list}
    variants_by_sku = {v.sku: v for v in variants_list}

    # Validar resolución de cada item (preserva 404 por SKU)
    for item in sale_in.items:
        _vid = getattr(item, "variant_id", None)
        _v = variants_by_id.get(_vid) if _vid else variants_by_sku.get(item.sku)
        if not _v:
            raise HTTPException(status_code=404, detail=f"SKU '{item.sku}' no encontrado")

    _all_vids = [v.id for v in variants_list]
    _stocks = db.query(StockOnHand).filter(
        StockOnHand.variant_id.in_(_all_vids),
        StockOnHand.branch_id == current_user.branch_id,
        or_(StockOnHand.organization_id == org_id, StockOnHand.organization_id == None),
    ).all()
    stock_by_variant = {s.variant_id: s for s in _stocks}

    _pbs_rows = db.query(ProductBranchStatus).filter(
        ProductBranchStatus.variant_id.in_(_all_vids),
        ProductBranchStatus.branch_id == current_user.branch_id,
    ).all()
    pbs_by_variant = {p.variant_id: p for p in _pbs_rows}

    for item in sale_in.items:
        # Resolver desde mapas pre-cargados (sin queries dentro del loop).
        variant_id_attr = getattr(item, "variant_id", None)
        variant = variants_by_id.get(variant_id_attr) if variant_id_attr else variants_by_sku.get(item.sku)

        # Stock pre-cargado.
        stock_record = stock_by_variant.get(variant.id)

        qty_dec = Decimal(str(item.quantity))
        current_stock = stock_record.qty_on_hand if stock_record else Decimal(0.0)

        if current_stock < qty_dec:
             raise HTTPException(status_code=400, detail=f"Stock insuficiente para: {variant.sku}.")

        # Precios y Escalas — branch override pre-cargado.
        branch_status = pbs_by_variant.get(variant.id)
        branch_price_override = branch_status.price_override if branch_status else None

        if branch_price_override is not None:
            # Precio fijo de sucursal: ignora precio enviado por cliente y precios escalonados
            unit_price = branch_price_override
        else:
            unit_price = variant.price
            if item.unit_price is not None and item.unit_price > 0:
                unit_price = item.unit_price
            else:
                if variant.prices:
                    applicable = sorted([p for p in variant.prices if p.min_quantity <= qty_dec], key=lambda x: x.unit_price)
                    if applicable: unit_price = applicable[0].unit_price

        unit_price = Decimal(str(unit_price))

        # --- Guard: Discount ceiling (server-side margin protection) ---
        # ADMINISTRADOR y DUEÑO pueden autorizar descuentos mayores; los demás roles
        # no pueden vender por debajo del (precio mínimo de referencia) * (1 - MAX_DISCOUNT_PCT).
        # Skip si hay branch_price_override: ya es un precio autorizado por admin.
        _role_str_discount = str(current_user.role.value) if hasattr(current_user.role, 'value') else str(current_user.role)
        if _role_str_discount not in ("ADMINISTRADOR", "DUEÑO") and branch_price_override is None:
            tier_prices = [Decimal(str(p.unit_price)) for p in (variant.prices or []) if p.unit_price is not None]
            reference_price = min([Decimal(str(variant.price))] + tier_prices) if variant.price is not None else (min(tier_prices) if tier_prices else None)
            if reference_price is not None and unit_price < reference_price:
                min_allowed = reference_price * (Decimal(1) - MAX_DISCOUNT_PCT)
                if unit_price < min_allowed:
                    _variant_label = variant.product.name if (variant.product and variant.product.name) else variant.sku
                    raise HTTPException(
                        status_code=403,
                        detail=f"Descuento excede el límite permitido ({int(MAX_DISCOUNT_PCT*100)}%) en '{_variant_label}'. Precio mínimo permitido: ${float(min_allowed):.2f}"
                    )

        discount_factor = Decimal(1) - Decimal(str(item.discount or 0)) / Decimal(100)
        line_total = unit_price * qty_dec * discount_factor
        
        # IVA: fuente única (app/services/tax.py). Antes la fórmula vivía aquí
        # en línea y repetida en el ticket reemitido y en la devolución, cada
        # copia con su propio redondeo (auditoría Rmazh §3).
        #
        # `quantize=False` a propósito: se acumula sin redondear y se redondea
        # una sola vez al final (ver `quantize_totals` más abajo). Redondear
        # renglón por renglón corre el total unos centavos respecto del que
        # calcula el carrito del POS —`frontend/src/store/posStore.ts` suma sin
        # redondeos intermedios— y la validación de pagos de esta misma función
        # solo tolera un centavo: un carrito de cuatro renglones con descuento
        # rebotaba con 422 al cobrar con tarjeta.
        desglose = compute_line_tax(
            line_gross=line_total,
            tax_rate=variant.tax_rate,
            has_iva=bool(variant.has_iva),
            price_includes_tax=price_includes_tax,
            requires_invoice=bool(sale_in.requires_invoice),
            quantize=False,
        )
        accumulated_subtotal += desglose.subtotal
        accumulated_tax += desglose.tax
        total_sale += desglose.total
        line_total_gross = desglose.total

        new_line = SalesLineItem(
            variant_id=variant.id,
            # `variant_name` puede venir NULL en catalogos cargados fuera de la
            # aplicacion: sin el `or ''` la condicion era verdadera y se
            # intentaba concatenar None, tumbando el cobro con un 500.
            description=_line_description(variant),
            quantity=item.quantity,
            unit_price=unit_price,
            unit_cost=variant.cost,
            discount_percent=Decimal(str(item.discount or 0)),
            total_line=line_total_gross,
            organization_id=org_id
        )
        db_lines.append(new_line)

        # Resta de Stock y Kardex
        if stock_record:
            qty_before = stock_record.qty_on_hand
            stock_record.qty_on_hand -= qty_dec
            db.add(InventoryMovement(
                branch_id=current_user.branch_id,
                variant_id=variant.id,
                user_id=current_user.id,
                movement_type=MovementType.SALE_OUT,
                qty_change=-qty_dec,
                qty_before=qty_before,
                qty_after=qty_before - qty_dec,
                reference=f"Venta POS ({'Update' if existing_sale else 'Nueva'})",
                organization_id=org_id
            ))

    # --- Gastro: propina ---
    # La propina se suma al total a cobrar (los pagos deben cubrir bienes + propina).
    # Se persiste por separado en tip_amount para el reporte de propinas por mesero.
    tip_amount = Decimal(str(sale_in.tip_amount or 0))
    if tip_amount < 0:
        raise HTTPException(status_code=400, detail="La propina no puede ser negativa")
    total_sale += tip_amount

    # --- 2. Análisis Financiero ---
    # Guard 0: Montos negativos en pagos nunca son válidos. Devoluciones van por /api/returns.
    if any(Decimal(str(p.amount)) < 0 for p in sale_in.payments):
        raise HTTPException(
            status_code=400,
            detail="Los montos de pago no pueden ser negativos"
        )

    # Hallazgo preexistente (revisión final): `sum()` sin valor inicial
    # devuelve `int 0` (no `Decimal`) cuando `sale_in.payments` está vacío
    # (venta a crédito puro). Eso dejaba pasar folio, descuento de stock y
    # cargo de deuda al cliente, y solo reventaba después, al commitear,
    # cuando `total_paid.quantize(...)` truena con `AttributeError` porque
    # `int` no tiene `.quantize()` — 500 después de mutar todo. `Decimal("0")`
    # como valor inicial evita el `int 0`.
    total_paid = sum((Decimal(str(p.amount)) for p in sale_in.payments), Decimal("0"))

    # Fase 1.3: cambio entregado al cliente. Se calcula al crear la venta y se
    # persiste para que el cuadre de turno NO recompute (evita drift si la
    # lógica retrospectiva cambia). Fórmula: excedente de pagos en efectivo
    # sobre lo que el efectivo realmente tenía que cubrir (descontando
    # métodos no-cash en pagos mixtos).
    cash_paid = sum(
        (Decimal(str(p.amount)) for p in sale_in.payments if p.method == PaymentMethod.CASH),
        Decimal(0),
    )
    non_cash_paid = sum(
        (Decimal(str(p.amount)) for p in sale_in.payments if p.method != PaymentMethod.CASH),
        Decimal(0),
    )
    cash_needed = max(Decimal(0), total_sale - non_cash_paid)
    change_given = max(Decimal(0), cash_paid - cash_needed) if cash_paid > 0 else Decimal(0)

    # --- H-1: Server-side recompute + payment validation ---
    # `total_sale` ya está computado autoritativamente arriba (server). El monto
    # recibido del cliente NO se confía; lo recomputamos desde sale_in.payments y
    # validamos contra `total_sale` con tolerancia de centavo para absorber
    # redondeo. Un cajero malicioso/confundido no puede registrar `amount=9999`
    # para una venta de $100.
    if sale_in.payments:
        expected_total = total_sale
        tolerance = Decimal("0.01")
        # Pago insuficiente → 422
        if total_paid < (expected_total - tolerance):
            raise HTTPException(
                status_code=422,
                detail=f"Pagos insuficientes: recibido {float(total_paid):.2f} vs total {float(expected_total):.2f}"
            )
        # Sobrepago anómalo (>10x) → 422 (subsume L-1 parcialmente)
        if expected_total > Decimal("0") and total_paid > expected_total * Decimal("10"):
            raise HTTPException(
                status_code=422,
                detail="Sobrepago anómalo, revisa el monto"
            )
        # Discrepancia: solo es señal cuando NO hay efectivo en el mix.
        # En México es BAU pagar con billete grande (250 → 500, 18 → 20) y el
        # cajero devuelve el cambio; eso satura logs sin aportar info. Si el
        # mix es 100% no-cash (TARJETA, TRANSFER, OTHER), el monto recibido
        # debe coincidir con el total — ahí sí es señal de fat-finger.
        has_cash = any(
            (p.method.value if hasattr(p.method, 'value') else str(p.method)).upper() == "CASH"
            for p in sale_in.payments
        )
        if not has_cash and (total_paid - expected_total).copy_abs() > tolerance:
            logger.warning(
                "PAYMENT_DISCREPANCY (no-cash): user=%s branch_id=%s sale_id=%s expected=%s received=%s methods=%s",
                current_user.username, current_user.branch_id, sale_in.id,
                expected_total, total_paid,
                [str(p.method) for p in sale_in.payments],
            )

    balance_diff = total_sale - total_paid
    remaining_debt = Decimal("0.00")
    doc_status = DocumentStatus.PAID

    if balance_diff > Decimal("0.05"):
        remaining_debt = balance_diff
        doc_status = DocumentStatus.PENDING
        # Crédito Cliente
        if sale_in.customer_id:
            customer = db.query(Customer).filter(Customer.id == sale_in.customer_id, Customer.organization_id == org_id).first()
            if customer and customer.has_credit:
                customer.current_balance += remaining_debt
                db.add(CustomerLedgerEntry(
                    customer_id=customer.id,
                    amount=remaining_debt,
                    description=f"Crédito por Venta",
                    organization_id=org_id
                ))

    # --- 3. Guardar / Actualizar Cabecera ---
    # Redondeo a centavos UNA sola vez, ya pasada la validación de pagos, para
    # que el total que se compara contra lo que cobró el cajero sea exactamente
    # el que suma el carrito (ver `quantize=False` arriba). Antes esto lo hacía
    # de forma implícita la columna NUMERIC(10,2) al guardar.
    _totales_doc = quantize_totals(accumulated_subtotal, accumulated_tax)
    accumulated_subtotal = _totales_doc.subtotal
    accumulated_tax = _totales_doc.tax
    total_sale = quantize_amount(total_sale)  # incluye la propina

    if existing_sale:
        sales_doc = existing_sale
        sales_doc.status = doc_status
        sales_doc.customer_id = sale_in.customer_id
        sales_doc.customer_name = sale_in.customer_name
        sales_doc.total_amount = total_sale
        sales_doc.subtotal = accumulated_subtotal
        sales_doc.tax_amount = accumulated_tax
        sales_doc.requires_invoice = sale_in.requires_invoice
        sales_doc.change_given = change_given
        sales_doc.tip_amount = tip_amount

        # El dinero entra al cajon de HOY, no al del dia en que se abrio la
        # venta a credito. Si el turno que la abrio ya cerro, ese efectivo
        # quedaria fuera de todo corte (ver CASH_INCLUDED_STATUSES arriba: sin
        # esta reasignacion, el Payment recien creado seguiria colgado del
        # cash_session_id viejo, que puede pertenecer a una sesion ya cerrada
        # cuyo `expected` ya quedo fijo en el cierre).
        if doc_status == DocumentStatus.PAID:
            active_cash = db.query(CashSession.id).filter(
                CashSession.user_id == current_user.id,
                CashSession.branch_id == current_user.branch_id,
                CashSession.status == CashSessionStatus.OPEN,
            ).first()
            if active_cash:
                sales_doc.cash_session_id = active_cash[0]
    else:
        current_series = "A"
        next_folio = get_next_folio(db, branch_id=current_user.branch_id, series=current_series)
        # Track 1: vincular venta a sesión OPEN del cajero (si existe).
        # N PCs del mismo cajero comparten la misma sesión.
        from app.models.cash import CashSession as _CashSession, CashSessionStatus as _CSStatus
        active_cash = db.query(_CashSession.id).filter(
            _CashSession.user_id == current_user.id,
            _CashSession.branch_id == current_user.branch_id,
            _CashSession.status == _CSStatus.OPEN,
        ).first()
        cash_session_id_value = active_cash[0] if active_cash else None
        sales_doc = SalesDocument(
            id=sale_in.id, doc_type=DocumentType.INVOICE, status=doc_status,
            branch_id=current_user.branch_id, seller_id=current_user.id,
            customer_id=sale_in.customer_id, customer_name=sale_in.customer_name,
            total_amount=total_sale, subtotal=accumulated_subtotal,
            tax_amount=accumulated_tax, requires_invoice=sale_in.requires_invoice,
            series=current_series, folio=next_folio, organization_id=org_id,
            cash_session_id=cash_session_id_value,
            change_given=change_given,
            tip_amount=tip_amount,
            client_uuid=sale_in.client_uuid,
        )
        db.add(sales_doc)

    # Equivalente en dolares (informativo). Se congela el tipo de cambio
    # efectivo del momento para que el ticket y su reimpresion muestren el
    # mismo numero. Si Banxico, la tabla o el servicio fallan la venta se
    # cobra igual y el tipo queda en NULL (ver el try/except de abajo). NO
    # participa de ningun calculo de totales, pagos, stock ni caja.
    if getattr(sales_doc, "usd_rate", None) is None:
        from app.services.exchange_rate import tipo_vigente_o_error
        # SAVEPOINT + try/except AFUERA del `with` (a proposito, no es un
        # descuido): si Banxico esta vivo pero la tabla/consulta revienta a
        # nivel SQL (no solo un bug de Python), Postgres aborta la
        # transaccion completa. El SAVEPOINT aisla esas consultas para que
        # el fallo no contamine el resto del cobro — pero SOLO si la
        # excepcion cruza la frontera del `with`: por eso aqui se usa
        # `tipo_vigente_o_error` (que SI lanza) y NO `snapshot_usd_rate`
        # (que se traga su propio error). Si el try/except estuviera DENTRO
        # del `with`, SQLAlchemy no veria ninguna excepcion al salir y
        # emitiria RELEASE SAVEPOINT sobre una conexion ya abortada, que
        # revienta con InFailedSqlTransaction igual que sin el SAVEPOINT.
        try:
            with db.begin_nested():
                sales_doc.usd_rate = tipo_vigente_o_error(db, org_id)
        except Exception:  # noqa: BLE001 — jamas impedir un cobro
            logger.warning("USD_SNAPSHOT_FAILED org=%s", org_id, exc_info=True)
            sales_doc.usd_rate = None

    db.flush()

    # --- H-2: Persist global_discount_pct (defensive write) ---
    # La columna se agrega via migrator runtime (scripts/railway_init.py); el
    # modelo ORM aún NO la declara para mantener este cambio chico. setattr la
    # ignora silenciosamente si el atributo no existe (deploy ordering safety).
    if global_disc_pct > 0:
        try:
            setattr(sales_doc, 'global_discount_pct', global_disc_pct)
        except Exception:
            pass

    # --- Gastro: atribuir la venta al mesero de la mesa (ventas por mesero) ---
    # Al cobrar una mesa, la venta viene de un parked ticket; la mesa que apunta
    # a ese ticket guarda el mesero asignado. Lo copiamos a la venta.
    if sale_in.parked_ticket_id:
        try:
            from app.modules.tables.models import DiningTable
            row = db.query(DiningTable.server_user_id).filter(
                DiningTable.current_ticket_id == sale_in.parked_ticket_id,
                DiningTable.organization_id == org_id,
            ).first()
            if row and row[0]:
                sales_doc.server_user_id = row[0]
        except Exception:
            pass

    for line in db_lines:
        line.document_id = sales_doc.id
        db.add(line)

    for p in sale_in.payments:
        # ATS-9: rechazar montos negativos o cero explícito
        if p.amount < 0:
            raise HTTPException(status_code=400, detail=f"Monto de pago inválido: {p.amount}")
        if p.amount > 0:
            db.add(Payment(
                sales_document_id=sales_doc.id, amount=p.amount, method=p.method,
                created_by_id=current_user.id, reference=p.reference, organization_id=org_id
            ))

    # --- M-3: Mark parked ticket as CONVERTED (atómico con la venta) ---
    # Si la venta proviene de un ticket pausado, marcamos el parked CONVERTED y
    # guardamos el FK al sale para trazabilidad. Esto evita que un doble-click o
    # back-button convierta el mismo parked en dos ventas. Se elige UPDATE en vez
    # de DELETE para preservar el audit trail (cart_json, who/when parked).
    if sale_in.parked_ticket_id and not existing_sale:
        pt = db.query(ParkedTicket).filter(
            ParkedTicket.id == sale_in.parked_ticket_id,
            ParkedTicket.organization_id == org_id,
            ParkedTicket.branch_id == current_user.branch_id,
            ParkedTicket.deleted_at == None,
        ).first()
        if pt is None:
            raise HTTPException(
                status_code=404,
                detail="Ticket pausado no encontrado o ya consumido."
            )
        # Reject if already converted (column may not exist en deploys legados →
        # getattr defensivo; ausencia se trata como 'ACTIVE').
        pt_status = getattr(pt, 'status', None) or 'ACTIVE'
        if pt_status != 'ACTIVE':
            raise HTTPException(
                status_code=410,
                detail=f"Ticket pausado en estado {pt_status}; no se puede reanudar."
            )
        try:
            setattr(pt, 'status', 'CONVERTED')
            setattr(pt, 'converted_to_sale_id', sales_doc.id)
        except Exception:
            # Si las columnas aún no existen, fallback a soft-delete.
            pt.deleted_at = datetime.now(timezone.utc)

    # Outbox transaccional: encolamos el evento DENTRO de la misma transacción que
    # la venta, así los efectos (consumo de insumos, liberar mesa, reorden de abasto)
    # nunca se pierden en silencio. Si el enqueue falla, la venta NO se bloquea.
    outbox_id = None
    try:
        outbox_id = EventBus.enqueue(db, SalesDocumentCreated(
            sales_document_id=str(sales_doc.id),
            items=_safe_sale_items(sales_doc),
        ))
    except Exception:
        logger.exception("OUTBOX_ENQUEUE_FAILED sale=%s", getattr(sales_doc, "id", None))

    # ATS-4: commit atómico — si falla, revertir todo (stock, pagos, documento, evento)
    try:
        db.commit()
        db.refresh(sales_doc)
    except Exception as exc:
        db.rollback()
        logger.error(
            "CHECKOUT_COMMIT_FAILED: user_id=%s branch_id=%s error=%s",
            current_user.id, current_user.branch_id, str(exc)
        )
        raise HTTPException(
            status_code=500,
            detail="Error al guardar la venta. No se realizó ningún cargo. Intente de nuevo."
        )

    # --- 4. Eventos y Respuesta ---
    # Entrega inmediata (baja latencia) del evento recién commiteado; el worker del
    # outbox reintenta cualquier cosa que quede pendiente. No lanza al request.
    if outbox_id:
        try:
            from app.core.outbox import drain_now
            drain_now([outbox_id])
        except Exception:
            logger.exception("OUTBOX_DRAIN_FAILED sale=%s", sales_doc.id)

    # Fase 1.4: redondeo explícito a 2 decimales antes de serializar a float.
    # Antes `float(max(0, total_paid - total_sale))` podía devolver 0.009999...
    # por imprecisión binaria; ahora `change_given` ya es Decimal cuantizado.
    change_response = change_given.quantize(Decimal("0.01"))
    return {
        "status": "success",
        "sale_id": sales_doc.id,
        "folio": f"{sales_doc.series}-{sales_doc.folio}",
        "total": float(sales_doc.total_amount.quantize(Decimal("0.01")) if sales_doc.total_amount is not None else Decimal("0.00")),
        "paid": float(total_paid.quantize(Decimal("0.01"))),
        "change": float(change_response),
        "credit_debt": float(remaining_debt.quantize(Decimal("0.01"))),
        # Tipo de cambio congelado en la venta. None = la organizacion no tiene
        # equivalente en dolares configurado.
        "usd_rate": float(sales_doc.usd_rate) if sales_doc.usd_rate is not None else None,
    }

# --------------------------------------------------------------------------
# 6. OBTENER DETALLE DE VENTA
# --------------------------------------------------------------------------
@router.get("/by-folio/{series}/{folio}", response_model=SaleRead)
def get_sale_by_folio(
    series: str,
    folio: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    sale = db.query(SalesDocument).filter(
        SalesDocument.organization_id == org_id,
        SalesDocument.series == series,
        SalesDocument.folio == folio
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail=f"Ticket {series}-{folio} no encontrado")
    _assert_sale_branch_access(sale, current_user)
    return sale


@router.get("/my-last", response_model=SaleRead)
def get_my_last_sale(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Returns the most recent PAID INVOICE sale of the current user in their branch."""
    q = (
        db.query(SalesDocument)
        .options(
            joinedload(SalesDocument.lines),
            joinedload(SalesDocument.payments),
        )
        .filter(
            SalesDocument.organization_id == org_id,
            SalesDocument.seller_id == current_user.id,
            SalesDocument.status == DocumentStatus.PAID,
            SalesDocument.doc_type == DocumentType.INVOICE,
        )
    )
    if current_user.branch_id is not None:
        q = q.filter(SalesDocument.branch_id == current_user.branch_id)
    sale = q.order_by(SalesDocument.created_at.desc()).first()
    if sale is None:
        raise HTTPException(status_code=404, detail="No tienes ventas recientes.")
    return SaleRead.model_validate(sale)


# ─────────────────────────────────────────────────────────────────────────────
# Track 2 (POS bug-fix): tickets pausados — tabla aparte, no son ventas.
# NO consumen folio. NO descuentan inventario. NO aparecen en historial.
# Hand-off entre PCs de la misma sucursal: cualquier cajero puede reanudar.
# Routes deben ir ANTES de "/{sale_id}" para que /parked no sea capturado.
# ─────────────────────────────────────────────────────────────────────────────
from app.schemas.sales import ParkedTicketCreate, ParkedTicketRead, ParkedTicketUpdate


def _parked_to_read(p: ParkedTicket) -> ParkedTicketRead:
    return ParkedTicketRead(
        id=p.id,
        branch_id=p.branch_id,
        user_id=p.user_id,
        customer_id=p.customer_id,
        cart_json=p.cart_json,
        notes=p.notes,
        parked_at=p.created_at,
        expires_at=p.expires_at,
    )


@router.post("/parked", response_model=ParkedTicketRead)
def park_ticket(
    payload: ParkedTicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    if not current_user.branch_id:
        raise HTTPException(status_code=400, detail="Tu usuario no tiene sucursal asignada.")
    if not payload.cart_json:
        raise HTTPException(status_code=422, detail="cart_json no puede estar vacío.")

    hours = payload.expires_in_hours or 24
    expires = datetime.now(timezone.utc) + timedelta(hours=hours)

    pt = ParkedTicket(
        organization_id=org_id,
        branch_id=current_user.branch_id,
        user_id=current_user.id,
        customer_id=payload.customer_id,
        cart_json=payload.cart_json,
        notes=payload.notes,
        expires_at=expires,
    )
    db.add(pt)
    db.commit()
    db.refresh(pt)
    return _parked_to_read(pt)


@router.get("/parked", response_model=List[ParkedTicketRead])
def list_parked_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Lista tickets pausados de la sucursal del cajero, no expirados."""
    if not current_user.branch_id:
        return []
    now = datetime.now(timezone.utc)
    rows = db.query(ParkedTicket).filter(
        ParkedTicket.organization_id == org_id,
        ParkedTicket.branch_id == current_user.branch_id,
        ParkedTicket.deleted_at == None,
        # expires_at NULL o futuro
        ((ParkedTicket.expires_at == None) | (ParkedTicket.expires_at > now)),
    ).order_by(ParkedTicket.created_at.desc()).all()
    return [_parked_to_read(p) for p in rows]


@router.get("/parked/{parked_id}", response_model=ParkedTicketRead)
def get_parked_ticket(
    parked_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    pt = db.query(ParkedTicket).filter(
        ParkedTicket.id == parked_id,
        ParkedTicket.organization_id == org_id,
        ParkedTicket.branch_id == current_user.branch_id,
        ParkedTicket.deleted_at == None,
    ).first()
    if not pt:
        raise HTTPException(status_code=404, detail="Ticket pausado no encontrado.")
    return _parked_to_read(pt)


@router.post("/parked/{parked_id}/resume", response_model=ParkedTicketRead)
def resume_parked_ticket(
    parked_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Devuelve el cart_json para que el frontend lo cargue. NO borra el
    ticket — el cliente decide si lo descarta tras cobrar."""
    pt = db.query(ParkedTicket).filter(
        ParkedTicket.id == parked_id,
        ParkedTicket.organization_id == org_id,
        ParkedTicket.branch_id == current_user.branch_id,
        ParkedTicket.deleted_at == None,
    ).first()
    if not pt:
        raise HTTPException(status_code=404, detail="Ticket pausado no encontrado.")
    # M-3: rechazar reanudar si el ticket ya se materializó en una venta.
    pt_status = getattr(pt, 'status', None) or 'ACTIVE'
    if pt_status != 'ACTIVE':
        raise HTTPException(
            status_code=410,
            detail=f"Ticket pausado en estado {pt_status}; no se puede reanudar."
        )
    return _parked_to_read(pt)


@router.patch("/parked/{parked_id}", response_model=ParkedTicketRead)
def update_parked_ticket(
    parked_id: str,
    payload: ParkedTicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Actualiza el carrito de una cuenta abierta (usado por la comanda para
    acumular platillos enviados a cocina). No consume folio ni descuenta stock.

    Contrato: last-write-wins sobre las llaves que trae `payload.cart_json`
    (típicamente `items`, que el cliente manda ya mergeado = existentes + nuevos).
    Se hace un shallow-merge de nivel superior para NO perder llaves hermanas que
    el POS guarda junto a `items` (p.ej. `requires_invoice`, `global_discount`).
    Asume un solo escritor por cuenta; si dos clientes editan la misma cuenta en
    paralelo, gana el último PATCH (los `items` no fusionados del otro se pierden)."""
    if not payload.cart_json:
        raise HTTPException(status_code=422, detail="cart_json no puede estar vacío.")
    pt = db.query(ParkedTicket).filter(
        ParkedTicket.id == parked_id,
        ParkedTicket.organization_id == org_id,
        ParkedTicket.branch_id == current_user.branch_id,
        ParkedTicket.deleted_at == None,
    ).first()
    if not pt:
        raise HTTPException(status_code=404, detail="Ticket pausado no encontrado.")
    pt_status = getattr(pt, 'status', None) or 'ACTIVE'
    if pt_status != 'ACTIVE':
        raise HTTPException(
            status_code=410,
            detail=f"Ticket pausado en estado {pt_status}; no se puede modificar."
        )
    # Shallow-merge: conserva llaves top-level existentes (requires_invoice,
    # global_discount…) y sobrescribe solo las que el payload trae.
    base = dict(pt.cart_json) if isinstance(pt.cart_json, dict) else {}
    base.update(payload.cart_json)
    pt.cart_json = base
    if payload.notes is not None:
        pt.notes = payload.notes
    db.commit()
    db.refresh(pt)
    return _parked_to_read(pt)


@router.delete("/parked/{parked_id}")
def delete_parked_ticket(
    parked_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    pt = db.query(ParkedTicket).filter(
        ParkedTicket.id == parked_id,
        ParkedTicket.organization_id == org_id,
        ParkedTicket.branch_id == current_user.branch_id,
        ParkedTicket.deleted_at == None,
    ).first()
    if not pt:
        raise HTTPException(status_code=404, detail="Ticket pausado no encontrado.")
    pt.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "deleted", "id": parked_id}


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale_detail(
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    sale = db.query(SalesDocument).filter(
        SalesDocument.id == sale_id,
        SalesDocument.organization_id == org_id
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    _assert_sale_branch_access(sale, current_user)
    return sale

@router.get("/{sale_id}/print-view", response_class=HTMLResponse)
def get_sale_print_view(
    request: Request,
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Returns a print-friendly HTML view of the sale ticket.
    """
    sale = db.query(SalesDocument).filter(
        SalesDocument.id == sale_id,
        SalesDocument.organization_id == org_id
    ).options(
        joinedload(SalesDocument.lines).joinedload(SalesLineItem.variant),
        joinedload(SalesDocument.payments),
        joinedload(SalesDocument.seller)
    ).first()
    
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    _assert_sale_branch_access(sale, current_user)

    organization = db.query(Organization).filter(Organization.id == org_id).first()
    branch = db.query(Branch).filter(Branch.id == sale.branch_id).first()

    from app.models.returns import SaleReturn
    returns = db.query(SaleReturn).filter(
        SaleReturn.sale_id == sale_id,
        SaleReturn.status == "APPROVED"
    ).options(joinedload(SaleReturn.items)).all()

    # Sprint 4 (tech-debt): template movido a app/templates/print/ — KEEP-SSR
    # justificado para impresión térmica (HTML estático sin React).
    return templates.TemplateResponse("print/ticket.html", {
        "request": request,
        "sale": sale,
        "organization": organization,
        "branch": branch,
        "seller": sale.seller,
        "payments": sale.payments,
        "approved_returns": returns
    })

# --------------------------------------------------------------------------
# 7. CANCELAR VENTA (ANULACIÓN)
# --------------------------------------------------------------------------
@router.delete("/{sale_id}")
def cancel_sale(
    sale_id: str,
    reason: str = "Cancelación directa",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Anula una venta completa. 
    1. Marca estatus como CANCELLED.
    2. Revertir Stock (Entrada por Cancelación).
    3. Si hubo crédito, revertir deuda del cliente.
    """
    sale = db.query(SalesDocument).filter(
        SalesDocument.id == sale_id,
        SalesDocument.organization_id == org_id
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    if sale.status == DocumentStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Esta venta ya está cancelada")

    # 1. Revertir Stock
    for line in sale.lines:
        variant = db.query(ProductVariant).filter(
            ProductVariant.id == line.variant_id,
            ProductVariant.organization_id == org_id
        ).first()
        if variant:
            stock_record = db.query(StockOnHand).filter(
                StockOnHand.variant_id == variant.id, 
                StockOnHand.branch_id == sale.branch_id,
                StockOnHand.organization_id == org_id
            ).first()

            if stock_record:
                qty_to_restore = Decimal(str(line.quantity)) # Asumiendo unidad base
                qty_before = stock_record.qty_on_hand
                
                # Restaurar stock
                stock_record.qty_on_hand += qty_to_restore
                
                # Registrar movimiento
                move = InventoryMovement(
                    branch_id=sale.branch_id,
                    variant_id=variant.id,
                    user_id=current_user.id,
                    movement_type=MovementType.SALE_RETURN, # O un tipo específico CANCELLATION
                    qty_change=qty_to_restore,
                    qty_before=qty_before,
                    qty_after=qty_before + qty_to_restore,
                    reference=f"Cancelación Venta #{sale.folio}",
                    notes=f"Motivo: {reason}",
                    organization_id=org_id
                )
                db.add(move)

    # 2. Revertir Deuda (Si aplicó)
    # Si la venta estaba PENDING (crédito), reducimos la deuda del cliente
    # Si estaba PAID, asumimos que se devolvió el dinero o se queda como saldo a favor (Nota de Crédito)
    # Para simplificar este endpoint DELETE, asumiremos reversión total.
    
    if sale.customer_id:
        customer = db.query(Customer).filter(
            Customer.id == sale.customer_id,
            Customer.organization_id == org_id
        ).first()
        if customer:
            # ¿Cuánto se cargó al cliente?
            # Si status=PENDING, el cliente debe (total - pagado).
            # Al cancelar, quitamos esa deuda.
            
            # Calculamos cuánto se debía originalmente
            paid_amount = sum(p.amount for p in sale.payments)
            debt_amount = sale.total_amount - paid_amount
            
            if debt_amount > 0 and sale.status == DocumentStatus.PENDING:
                customer.current_balance -= debt_amount # Reducir deuda
                
                # Ledger entry
                ledger = CustomerLedgerEntry(
                    customer_id=customer.id,
                    sales_document_id=sale.id,
                    amount=-debt_amount,
                    description=f"Cancelación Venta #{sale.folio}",
                    entry_type="CANCELLATION",
                    organization_id=org_id
                )
                db.add(ledger)

    # 3. Marcar Cancelado
    prev_status = sale.status.value if hasattr(sale.status, "value") else str(sale.status)
    sale.status = DocumentStatus.CANCELLED

    # Rastro append-only de la cancelación: es la ÚNICA fuente del pivote de
    # cancelaciones (`/api/platform/reports/cancellations`). `updated_at` no
    # sirve —cualquier UPDATE masivo lo pisa— y el estatus CANCELLED solo
    # dice que pasó, no cuándo ni quién. `audit_cash_event` escribe dentro de
    # un SAVEPOINT y no propaga: si el insert falla, se deshace solo él y el
    # `db.commit()` de abajo confirma igual la cancelación.
    from app.services.cash_audit import audit_cash_event
    from app.models.cash_audit import CashAuditEvent
    audit_cash_event(
        db,
        event_type=CashAuditEvent.SALE_CANCELLED,
        organization_id=org_id,
        session_id=sale.cash_session_id,
        branch_id=sale.branch_id,
        user_id=current_user.id,
        amount=sale.total_amount,
        related_table="sales_documents",
        related_id=sale.id,
        payload={
            "reason": reason,
            "prev_status": prev_status,
            "folio": sale.folio,
        },
    )

    db.commit()
    return {"message": "Venta cancelada exitosamente", "sale_id": sale.id}

# --------------------------------------------------------------------------
# 8. REEMBOLSO / DEVOLUCIÓN (NUEVO)
# --------------------------------------------------------------------------
@router.post("/{sale_id}/refund")
def refund_sale(
    sale_id: int,
    amount: Decimal = None, # Opcional: Monto parcial. Si es nulo, total.
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Genera una devolución monetaria o nota de crédito.
    Por ahora, lo implementaremos como una 'Nota de Reembolso' simple.
    """
    sale = db.query(SalesDocument).filter(
        SalesDocument.id == sale_id,
        SalesDocument.organization_id == org_id
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    
    # Lógica simplificada: Solo marcar reembolso si está pagada
    # Implementación completa requiere modelo de "Devoluciones" (Returns) separado.
    # Por ahora solo modificamos estado o notas.
    return {"message": "Funcionalidad de reembolso parcial en construcción"}


@router.get("/export/csv")
def export_sales_csv(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[DocumentStatus] = None,
    doc_type: Optional[List[DocumentType]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    # 0. Debug Check
    print(f"DEBUG_CSV_EXPORT: org_id={org_id}, user={current_user.username}")
    """
    Exporta el reporte de ventas a CSV compatible con Excel.
    """
    # 1. Construir Query (Misma lógica que read_sales pero sin paginación)
    query = db.query(SalesDocument).filter(
        SalesDocument.organization_id == org_id
    )

    # Branch scoping — HQ ve todo, branch users solo su sucursal.
    if not _is_hq_role(current_user):
        if current_user.branch_id is None:
            raise HTTPException(status_code=403, detail="Sin acceso a exportación de ventas.")
        query = query.filter(SalesDocument.branch_id == current_user.branch_id)

    if doc_type:
        query = query.filter(SalesDocument.doc_type.in_(doc_type))
    
    # Optimización: Cargar relaciones necesarias
    query = query.options(
        joinedload(SalesDocument.payments),
        joinedload(SalesDocument.seller)
    )

    if start_date:
        query = query.filter(SalesDocument.created_at >= start_date)
    if end_date:
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=MX_TZ)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(SalesDocument.created_at <= end_date)
    if status is not None:
        query = query.filter(SalesDocument.status == status)

    sales = query.order_by(SalesDocument.created_at.desc()).all()

    # 2. Generar CSV en memoria
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Encabezados (BOM para que Excel reconozca UTF-8 correctamente)
    output.write(u'\ufeff') 
    writer.writerow(["Folio", "Fecha", "Hora", "Cliente", "Total", "Estatus", "Método Pago", "Vendedor", "Notas"])

    # Mapa de traducción
    METHOD_MAP = {
        "CASH": "Efectivo",
        "CARD": "Tarjeta",
        "TRANSFER": "Transferencia",
        "CHECK": "Cheque",
        "STORE_CREDIT": "Crédito Tienda",
        "OTHER": "Otro"
    }

    # Timezone handling
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo
    MX_TZ = ZoneInfo("America/Mexico_City")

    for sale in sales:
        # Timezone Conversion
        dt = sale.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(MX_TZ)

        # Formatear datos
        folio = f"{sale.series or ''}-{sale.folio}"
        fecha = local_dt.strftime("%Y-%m-%d")
        hora = local_dt.strftime("%H:%M:%S")
        cliente = sale.customer_name or "Público General"
        total = f"{sale.total_amount:.2f}"
        estatus = sale.status.value
        
        # Método de pago (Concatenar si hay múltiples)
        methods = []
        references = []
        
        for p in sale.payments:
            # Traducir método
            m_str = p.method.value if hasattr(p.method, 'value') else str(p.method)
            methods.append(METHOD_MAP.get(m_str, m_str))
            
            # Recopilar referencias (autorizaciones)
            if p.reference:
                references.append(f"{METHOD_MAP.get(m_str, m_str)[:3]}:{p.reference}")

        metodo_pago = ", ".join(set(methods)) if methods else "N/A"
        
        vendedor = sale.seller.username if sale.seller else "N/A"
        
        # Notas incluye las referencias de pago
        notas = " / ".join(references)
        
        writer.writerow([folio, fecha, hora, cliente, total, estatus, metodo_pago, vendedor, notas])

    output.seek(0)
    
    # 3. Retornar StreamingResponse
    filename = f"Ventas_Corte_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# Parked-ticket routes were moved above /{sale_id} (around line 551) so
# /api/sales/parked is not captured by the sale-id parameter route.
# See block immediately above @router.get("/{sale_id}", ...).
