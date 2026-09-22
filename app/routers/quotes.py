from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional

from app.core.database import get_db
from app.models import (
    SalesDocument, SalesLineItem, DocumentType, DocumentStatus,
    ProductVariant, StockOnHand, InventoryMovement, MovementType,
    Payment, Customer, Product
)
from app.schemas.sales import SaleCreate, SaleRead, QuoteDetailRead
from app.core.security import get_current_user
from app.models import User
from app.core.tenant_context import get_current_active_organization
from app.crud.products import get_variant_if_visible
from app.utils.folios import get_next_folio
from app.utils.pdf_generator import generate_quote_pdf

from app.core.permissions import require_module

router = APIRouter(dependencies=[Depends(require_module("quotes"))])

@router.post("/", response_model=Dict[str, Any])
def create_quote(
    quote_in: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Crea una cotización (No afecta stock ni caja)."""
    if not quote_in.items:
        raise HTTPException(status_code=400, detail="La cotización está vacía")

    # Calcular folio de cotización
    next_folio = get_next_folio(db, branch_id=current_user.branch_id, series="Q")

    total_amount = Decimal("0.00")
    temp_lines = []

    # Validar productos (tenant + branch scope via helper)
    for item in quote_in.items:
        variant = get_variant_if_visible(
            db,
            current_user,
            org_id,
            sku=item.sku,
            require_pos_active=True,
        )
        if not variant:
            # 404: evita distinguir "no existe" vs "no visible en tu sucursal"
            raise HTTPException(status_code=404, detail=f"SKU '{item.sku}' no encontrado")

        qty = Decimal(str(item.quantity))
        # Descuento por línea (porcentaje 0-100) capturado por el vendedor.
        discount_pct = Decimal(str(item.discount or 0))
        line_total = (variant.price * qty * (Decimal("100") - discount_pct) / Decimal("100")).quantize(Decimal("0.01"))
        total_amount += line_total

        temp_lines.append({
            "variant_id": variant.id,
            "description": f"{variant.sku} - {variant.variant_name}",
            "quantity": item.quantity,
            "unit_price": variant.price,
            "total_line": line_total,
            "discount_percent": discount_pct,
        })

    # Crear documento
    # Validar doc_type (QUOTE o ORDER)
    target_type = DocumentType.QUOTE
    if quote_in.doc_type == "ORDER":
        target_type = DocumentType.ORDER

    new_quote = SalesDocument(
        doc_type=target_type,
        status=DocumentStatus.PENDING,
        organization_id=org_id,
        branch_id=current_user.branch_id,
        seller_id=current_user.id,
        customer_id=quote_in.customer_id,
        total_amount=total_amount,
        notes=quote_in.notes,
        series="Q" if target_type == DocumentType.QUOTE else "P", # Q=Quote, P=Pedido
        folio=next_folio # Usamos el mismo contador o distinto?
        # TODO: Pedidos deberían tener su propia serie. Por ahora compartimos folio o usamos Q/P prefix.
        # Simplificación: Usar mismo contador pero diferente prefijo VISUAL.
        # Pero get_next_folio usa series para contar.
        # Si cambiamos series a P, contará P indenpendientemente.
    )
    
    # ADJUST FOLIO IF ORDER
    if target_type == DocumentType.ORDER:
        new_quote.series = "P"
        new_quote.folio = get_next_folio(db, branch_id=current_user.branch_id, series="P")

    db.add(new_quote)
    db.flush()

    # Agregar líneas
    for l in temp_lines:
        db_line = SalesLineItem(
            document_id=new_quote.id,
            variant_id=l["variant_id"],
            description=l["description"],
            quantity=l["quantity"],
            unit_price=l["unit_price"],
            total_line=l["total_line"],
            discount_percent=l["discount_percent"],
        )
        db.add(db_line)

    db.commit()
    print(f"DEBUG: Document Created {new_quote.id} Type: {target_type}")
    return {"status": "success", "quote_id": new_quote.id, "folio": f"{new_quote.series}-{new_quote.folio}"}

@router.get("", include_in_schema=False)
@router.get("/")
def list_quotes(
    skip: int = 0,
    limit: int = 100,
    doc_type: Optional[str] = None,
    status: Optional[DocumentStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Lista cotizaciones (QUOTE) y/o pedidos (ORDER) con paginación."""
    user_role_str = str(current_user.role.value) if hasattr(current_user.role, 'value') else str(current_user.role)
    is_superadmin = False
    if hasattr(current_user, 'platform_role'):
        p_role = str(current_user.platform_role.value) if hasattr(current_user.platform_role, 'value') else str(current_user.platform_role)
        if p_role == "SUPERADMIN":
            is_superadmin = True
    is_hq_role = is_superadmin or user_role_str in ["ADMINISTRADOR", "DUEÑO"]

    # Map doc_type filter (string from query) to enum list
    if doc_type == "QUOTE":
        type_filter = [DocumentType.QUOTE]
    elif doc_type == "ORDER":
        type_filter = [DocumentType.ORDER]
    else:
        type_filter = [DocumentType.QUOTE, DocumentType.ORDER]

    query = db.query(SalesDocument).filter(
        SalesDocument.organization_id == org_id,
        SalesDocument.doc_type.in_(type_filter),
    )
    if not is_hq_role and current_user.branch_id is not None:
        query = query.filter(SalesDocument.branch_id == current_user.branch_id)
    if status is not None:
        query = query.filter(SalesDocument.status == status)

    total = query.count()
    items_orm = (
        query.options(
            selectinload(SalesDocument.lines).joinedload(SalesLineItem.variant),
            selectinload(SalesDocument.payments),
            selectinload(SalesDocument.customer),
        )
        .order_by(SalesDocument.created_at.desc())
        .offset(skip).limit(limit).all()
    )

    items: List[Dict[str, Any]] = []
    for q in items_orm:
        items.append({
            "id": q.id,
            "series": q.series,
            "folio": q.folio,
            "doc_type": q.doc_type.value if hasattr(q.doc_type, 'value') else q.doc_type,
            "status": q.status.value if hasattr(q.status, 'value') else q.status,
            "customer_id": q.customer_id,
            "customer_name": (q.customer.name if q.customer else None) or q.customer_name,
            "subtotal": float(q.subtotal) if q.subtotal is not None else 0.0,
            "tax_amount": float(q.tax_amount) if q.tax_amount is not None else 0.0,
            "total_amount": float(q.total_amount) if q.total_amount is not None else 0.0,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "lines": [
                {
                    "id": l.id,
                    "variant_id": l.variant_id,
                    "sku": l.variant.sku if l.variant else None,
                    "description": l.description,
                    "quantity": float(l.quantity) if l.quantity is not None else 0.0,
                    "unit_price": float(l.unit_price) if l.unit_price is not None else 0.0,
                    "total_line": float(l.total_line) if l.total_line is not None else 0.0,
                }
                for l in (q.lines or [])
            ],
            "payments": [
                {"method": (p.method.value if hasattr(p.method, 'value') else p.method), "amount": float(p.amount)}
                for p in (q.payments or [])
            ],
        })

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{quote_id}", response_model=QuoteDetailRead)
def get_quote_detail(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Obtiene detalle de una cotización o pedido para edición."""
    quote = db.query(SalesDocument).filter(
        SalesDocument.id == quote_id,
        SalesDocument.organization_id == org_id,
    ).first()
    if not quote or quote.doc_type not in [DocumentType.QUOTE, DocumentType.ORDER]:
        raise HTTPException(404, "Documento no encontrado o inválido")
    
    # Enrich lines
    enriched_lines = []
    for line in quote.lines:
        variant = db.query(ProductVariant).get(line.variant_id)
        stock_qty = 0
        pkg_units = []
        prod_id = None
        
        if variant:
            prod = variant.product
            if prod:
                prod_id = prod.id
                # Get packaging units (Schema expects List[dict] or Pydantic models?)
                # We'll use dicts to match what the frontend expects or just pass the objects
                # Frontend needs: name, package_price, units_per_package
                pkg_units = [
                    {
                        "name": p.name, 
                        "package_price": float(p.package_price), 
                        "units_per_package": float(p.units_per_package)
                    } for p in prod.packaging_units
                ]
            
            # Get stock
            stock_rec = db.query(StockOnHand).filter(
                StockOnHand.variant_id == variant.id,
                StockOnHand.branch_id == current_user.branch_id
            ).first()
            if stock_rec:
                stock_qty = float(stock_rec.qty_on_hand)
        
        line_dict = {
            "id": line.id,
            "variant_id": line.variant_id,
            "sku": variant.sku if variant else "UNKNOWN",
            "description": line.description,
            "quantity": float(line.quantity),
            "unit_price": float(line.unit_price),
            "total_line": float(line.total_line),
            "product_id": prod_id,
            "stock": stock_qty,
            "packaging_units": pkg_units
        }
        enriched_lines.append(line_dict)

    # Convert quote to dict and replace lines
    quote_dict = {
        "id": quote.id,
        "doc_type": quote.doc_type.value,
        "status": quote.status.value,
        "branch_id": quote.branch_id,
        "seller_id": quote.seller_id,
        "customer_id": quote.customer_id,
        "customer_name": quote.customer.name if quote.customer else "Publico General",
        "series": quote.series,
        "folio": quote.folio,
        "subtotal": float(quote.subtotal) if quote.subtotal else 0.0,
        "tax_amount": float(quote.tax_amount) if quote.tax_amount else 0.0,
        "total_amount": float(quote.total_amount),
        "created_at": quote.created_at,
        "lines": enriched_lines,
        "payments": quote.payments
    }
    
    return quote_dict

@router.delete("/{quote_id}")
def delete_quote(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Cancela o Elimina."""
    quote = db.query(SalesDocument).filter(
        SalesDocument.id == quote_id,
        SalesDocument.organization_id == org_id,
    ).first()
    if not quote or quote.doc_type not in [DocumentType.QUOTE, DocumentType.ORDER]:
        raise HTTPException(404, "Documento no encontrado")
    
    if quote.status == DocumentStatus.PAID:
        raise HTTPException(400, "No se puede eliminar un documento ya procesado")

    # Hard Delete if PENDING to keep DB clean? Or Soft Delete?
    # User said "Eliminar", implying removal. 
    # Let's do Soft Delete (CANCELLED) if it has history, but Hard Delete if it's just a draft?
    # For simplicity and safety: Mark as CANCELLED.
    # User Reqt: "Eliminarlas" -> if I just cancel, it stays in list.
    # If I hard delete, it's gone.
    # Let's HARD DELETE if status is PENDING.
    
    if quote.status == DocumentStatus.PENDING:
        # Delete lines first
        db.query(SalesLineItem).filter(SalesLineItem.document_id == quote.id).delete()
        db.delete(quote)
        db.commit()
        return {"status": "success", "message": "Documento eliminado"}
    
    # If it was something else (shouldn't be, but handled), just set cancelled
    quote.status = DocumentStatus.CANCELLED
    db.commit()
    return {"status": "success", "message": "Documento cancelado"}

@router.put("/{quote_id}")
def update_quote(
    quote_id: str,
    quote_in: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Actualiza una cotización/pedido existente."""
    quote = db.query(SalesDocument).filter(
        SalesDocument.id == quote_id,
        SalesDocument.organization_id == org_id,
    ).first()
    if not quote or quote.doc_type not in [DocumentType.QUOTE, DocumentType.ORDER]:
        raise HTTPException(404, "Documento no encontrado")

    if quote.status == DocumentStatus.PAID:
        raise HTTPException(400, "No se puede editar un documento ya procesado")

    # Update Header
    if quote_in.customer_id:
        quote.customer_id = quote_in.customer_id

    # Update Items: Strategy -> Delete all existing lines and recreate.
    # This is simplest for full-document edits.
    db.query(SalesLineItem).filter(SalesLineItem.document_id == quote.id).delete()

    total_amount = Decimal("0.00")

    for item in quote_in.items:
        variant = get_variant_if_visible(
            db,
            current_user,
            org_id,
            sku=item.sku,
            require_pos_active=True,
        )
        if not variant:
            # Mantiene comportamiento original (skip silencioso) pero ahora
            # ya no permite resolver variants de otro tenant.
            continue

        # Use forced price if present (logic from Sales creation)
        unit_price = variant.price
        if item.unit_price is not None and item.unit_price > 0:
            unit_price = item.unit_price

        qty = Decimal(str(item.quantity))
        line_total = unit_price * qty
        total_amount += line_total
        
        db_line = SalesLineItem(
            document_id=quote.id,
            variant_id=variant.id,
            description=f"{variant.sku} - {variant.variant_name}",
            quantity=item.quantity,
            unit_price=unit_price,
            total_line=line_total,
            # SalesLineItem no tiene columna `notes`: pasarla como kwarg
            # tronaba este endpoint con TypeError en cada edición.
        )
        db.add(db_line)

    quote.total_amount = total_amount
    db.commit()
    return {"status": "success", "quote_id": quote.id, "folio": f"{quote.series}-{quote.folio}"}

@router.get("/{quote_id}/pdf")
def get_quote_pdf_file(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Genera el PDF."""
    quote = db.query(SalesDocument).filter(
        SalesDocument.id == quote_id,
        SalesDocument.organization_id == org_id,
    ).first()
    if not quote or quote.doc_type not in [DocumentType.QUOTE, DocumentType.ORDER]:
        raise HTTPException(404, "Documento no encontrado")
    
    # Reuse template, title changes dynamically inside? Need to check PDF gen.
    # Assuming generic PDF generator handles it or we accept "Cotizacion" title for now.
    pdf_content = generate_quote_pdf(quote)
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={quote.doc_type}_{quote.folio}.pdf"}
    )

@router.post("/{quote_id}/convert-to-sale")
def convert_quote_to_sale(
    quote_id: str,
    payment_method: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Convierte Cotización/Pedido/Nota en Venta Real (Invoice)."""
    quote = db.query(SalesDocument).filter(
        SalesDocument.id == quote_id,
        SalesDocument.organization_id == org_id,
        SalesDocument.doc_type.in_([DocumentType.QUOTE, DocumentType.ORDER])
    ).first()

    if not quote:
        raise HTTPException(404, "Documento no encontrado")

    if quote.status == DocumentStatus.PAID:
        raise HTTPException(400, "Ya fue procesado")

    # Validar stock al momento de convertir
    for line in quote.lines:
        stock = db.query(StockOnHand).filter(
            StockOnHand.variant_id == line.variant_id,
            StockOnHand.branch_id == current_user.branch_id
        ).first()

        if not stock or stock.qty_on_hand < line.quantity:
            raise HTTPException(400, f"Sin stock para {line.description}")

    from app.models.cash import CashSession, CashSessionStatus
    from app.routers.sales import _is_hq_role

    # Hallazgo ALTA (revisión final): el comentario decía "mismo criterio que
    # create_sale" pero solo replicaba la mitad — exigía caja únicamente si
    # el método era efectivo, y perdió la otra mitad ("todo usuario con
    # sucursal necesita turno abierto para operar, cobre o no en efectivo").
    # Con eso, `payment_method=CARD` sin caja abierta producía una venta con
    # `cash_session_id=None` — la venta huérfana que esta rama existe para
    # impedir. Replicamos el criterio completo de create_sale
    # (app/routers/sales.py, guard H-5): se exige caja si el usuario tiene
    # sucursal Y (cobra efectivo O no es rol HQ). Los roles HQ
    # (ADMINISTRADOR/DUEÑO) siguen exentos para lo que no toca el cajón.
    cobra_efectivo = payment_method.upper() == "CASH"
    requiere_caja = bool(current_user.branch_id) and (
        cobra_efectivo or not _is_hq_role(current_user)
    )
    # Igual que create_sale: se busca la sesión abierta siempre que haya
    # sucursal (para adoptarla si existe, aunque no sea obligatoria — p.ej.
    # rol HQ cobrando con tarjeta) y solo se exige (409 si falta) cuando
    # `requiere_caja` es True.
    sesion_activa = None
    if current_user.branch_id:
        sesion_activa = db.query(CashSession).filter(
            CashSession.user_id == current_user.id,
            CashSession.branch_id == current_user.branch_id,
            CashSession.status == CashSessionStatus.OPEN,
        ).first()
        if requiere_caja and sesion_activa is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Debes abrir caja antes de cobrar en efectivo"
                    if cobra_efectivo
                    else "Debes abrir caja antes de registrar ventas"
                ),
            )

    # Convertir a ORDER (Pagado) - Mantiene el documento en el módulo de Cotizaciones/Pedidos
    quote.doc_type = DocumentType.ORDER
    quote.status = DocumentStatus.PAID
    quote.created_at = datetime.now(timezone.utc)
    quote.cash_session_id = sesion_activa.id if sesion_activa else None
    quote.seller_id = current_user.id

    # Mantener serie P (o asignar si era cotización Q)
    # Si ya era ORDER (P), conserva P. Si era QUOTE (Q), cambia a P.
    if quote.series == "Q":
        quote.series = "P"
        quote.folio = get_next_folio(db, branch_id=current_user.branch_id, series="P")
        # Si ya era P, mantenemos el folio actual, solo cambia estado a PAID.

    # Registrar Pago y Movimientos de Stock
    # El pago nace atribuido a la caja de quien cobra, igual que en
    # `create_sale` (app/routers/sales.py). Sin esta linea el pago quedaba en
    # NULL y solo el respaldo por DOCUMENTO lo ubicaba: si mas tarde alguien
    # reprocesaba este pedido por el checkout en otro turno, la reasignacion de
    # `sales_documents.cash_session_id` se llevaba el efectivo de hoy al corte
    # de ese otro turno — exactamente el defecto que la atribucion por pago
    # existe para cerrar.
    new_payment = Payment(
        sales_document_id=quote.id,
        amount=quote.total_amount,
        method=payment_method,
        created_by_id=current_user.id,
        reference=f"Conv. desde {quote.series}-{quote.folio}",
        organization_id=org_id,
        cash_session_id=sesion_activa.id if sesion_activa else None,
    )
    db.add(new_payment)

    for line in quote.lines:
        stock = db.query(StockOnHand).filter(
            StockOnHand.variant_id == line.variant_id,
            StockOnHand.branch_id == current_user.branch_id
        ).first()

        qty_before = stock.qty_on_hand
        stock.qty_on_hand -= Decimal(str(line.quantity))

        db.add(InventoryMovement(
            branch_id=current_user.branch_id,
            variant_id=line.variant_id,
            user_id=current_user.id,
            movement_type=MovementType.SALE_OUT,
            qty_change=-line.quantity,
            qty_before=qty_before,
            qty_after=stock.qty_on_hand,
            organization_id=org_id,
        ))

    db.commit()
    return {"status": "success", "new_folio": f"{quote.series}-{quote.folio}"}

@router.get("/stats/kpi")
def get_quote_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """KPIs for Quotes and Orders."""
    # Base query: Quotes only
    # Filter by user branch? Usually yes.
    base_query = db.query(SalesDocument).filter(
        SalesDocument.doc_type.in_([DocumentType.QUOTE, DocumentType.ORDER]),
        SalesDocument.branch_id == current_user.branch_id
    )

    total_docs = base_query.count()
    total_amount = db.query(func.sum(SalesDocument.total_amount)).filter(
        SalesDocument.doc_type.in_([DocumentType.QUOTE, DocumentType.ORDER]),
        SalesDocument.branch_id == current_user.branch_id
    ).scalar() or 0

    # Pending
    pending_query = base_query.filter(SalesDocument.status == DocumentStatus.PENDING)
    pending_count = pending_query.count()
    pending_amount = db.query(func.sum(SalesDocument.total_amount)).filter(
        SalesDocument.doc_type.in_([DocumentType.QUOTE, DocumentType.ORDER]),
        SalesDocument.branch_id == current_user.branch_id,
        SalesDocument.status == DocumentStatus.PENDING
    ).scalar() or 0

    cancelled_count = base_query.filter(SalesDocument.status == DocumentStatus.CANCELLED).count()

    return {
        "total_count": total_docs,
        "total_amount": float(total_amount),
        "pending_count": pending_count,
        "pending_amount": float(pending_amount),
        "cancelled_count": cancelled_count
    }