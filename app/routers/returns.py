from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from typing import List, Dict, Any, Optional
from datetime import date
from app.core.database import get_db
from app.schemas.returns import SaleReturn, SaleReturnCreate, SaleReturnSummary
from app.crud import returns as crud_returns
from app.core.security import get_current_user
from app.models.users import User
from app.core.tenant_context import get_current_active_organization

router = APIRouter()


@router.get("/stats")
def get_returns_stats(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_active_organization),
):
    """KPIs del módulo de devoluciones."""
    from app.models.returns import SaleReturn as SR
    from app.models.sales import SalesDocument, DocumentStatus

    today = date.today()
    month_start = today.replace(day=1)

    base = db.query(SR).filter(SR.organization_id == org_id)

    pending_count = base.filter(SR.status == "PENDING").count()
    approved_count = base.filter(SR.status == "APPROVED").count()

    total_refunded_month = db.query(
        func.coalesce(func.sum(SR.total_refunded), 0)
    ).filter(
        SR.organization_id == org_id,
        SR.status == "APPROVED",
        cast(SR.created_at, Date) >= month_start,
    ).scalar()

    # Tasa de devolución: devoluciones aprobadas este mes / ventas este mes
    sales_count = db.query(func.count(SalesDocument.id)).filter(
        SalesDocument.organization_id == org_id,
        SalesDocument.status == DocumentStatus.PAID,
        cast(SalesDocument.created_at, Date) >= month_start,
    ).scalar() or 0

    returns_month = base.filter(
        cast(SR.created_at, Date) >= month_start,
    ).count()

    return_rate = round((returns_month / sales_count * 100), 1) if sales_count > 0 else 0.0

    return {
        "pending_count": pending_count,
        "approved_count": approved_count,
        "total_refunded_month": round(float(total_refunded_month), 2),
        "return_rate": return_rate,
        "returns_month": returns_month,
    }

@router.post("", response_model=SaleReturn, include_in_schema=False)
@router.post("/", response_model=SaleReturn)
def create_new_return(
    return_in: SaleReturnCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Crea una solicitud de devolución (Estado: PENDING). Requiere aprobación de supervisor.
    """
    # Verify original sale belongs to current org before delegating to CRUD
    from app.models.sales import SalesDocument
    sale = db.query(SalesDocument).filter(
        SalesDocument.id == return_in.sale_id,
        SalesDocument.organization_id == org_id
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    try:
        return crud_returns.create_return(
            db=db,
            return_in=return_in,
            user_id=current_user.id,
            branch_id=current_user.branch_id,
            organization_id=org_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/sale/{sale_id}", response_model=List[SaleReturn])
def get_returns_for_sale(
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Obtiene todas las devoluciones asociadas a un ticket específico.
    """
    from app.models.returns import SaleReturn as SRModel, SaleReturnItem
    from sqlalchemy.orm import joinedload, selectinload
    return db.query(SRModel).options(
        joinedload(SRModel.sale),
        joinedload(SRModel.user),
        joinedload(SRModel.branch),
        joinedload(SRModel.supervisor),
        selectinload(SRModel.items).joinedload(SaleReturnItem.variant),
    ).filter(
        SRModel.sale_id == sale_id,
        SRModel.organization_id == org_id,
    ).all()

@router.get("/")
def list_returns(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    branch_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    paginate: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Lista devoluciones de la organización. Fechas en día de México; sin
    fechas, los últimos 30 días, salvo `status=PENDING` (lo pendiente no caduca).
    Ámbito: roles de oficina ven toda la org o la sucursal pedida; los demás la suya."""
    from app.models.returns import SaleReturn, SaleReturnItem
    from sqlalchemy.orm import joinedload, selectinload
    from app.services import metricas_ventas as mv

    query = db.query(SaleReturn).options(
        joinedload(SaleReturn.sale),
        joinedload(SaleReturn.user),
        joinedload(SaleReturn.branch),
        joinedload(SaleReturn.supervisor),
        selectinload(SaleReturn.items).joinedload(SaleReturnItem.variant)
    ).filter(SaleReturn.organization_id == org_id)

    ambito = mv.resolver_ambito(current_user, org_id, branch_id)
    if not ambito.toda_la_org:
        query = query.filter(SaleReturn.branch_id == ambito.branch_id)

    if status:
        query = query.filter(SaleReturn.status == status)

    if start_date is None and end_date is None and status != "PENDING":
        periodo = mv.periodo_preset("30d")
        start_date, end_date = periodo.inicio, periodo.fin
    elif start_date is None or end_date is None:
        # Con una sola fecha, la que falta copia a la otra (mismo criterio que /sales/stats).
        if start_date is not None or end_date is not None:
            start_date = start_date or end_date
            end_date = end_date or start_date
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date no puede ser anterior a start_date")
    if start_date:
        query = query.filter(mv.dia_mx(SaleReturn.created_at) >= start_date)
    if end_date:
        query = query.filter(mv.dia_mx(SaleReturn.created_at) <= end_date)

    from app.schemas.returns import SaleReturn as SaleReturnSchema
    ordered = query.order_by(SaleReturn.created_at.desc())
    if paginate:
        total = ordered.count()
        raw = ordered.offset(skip).limit(limit).all()
        return {"items": [SaleReturnSchema.model_validate(r) for r in raw], "total": total, "skip": skip, "limit": limit}
    return [SaleReturnSchema.model_validate(r) for r in ordered.offset(skip).limit(limit).all()]

@router.get("/{return_id}", response_model=SaleReturn)
def get_return_by_id(
    return_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    from app.models.returns import SaleReturn, SaleReturnItem
    from sqlalchemy.orm import joinedload, selectinload
    db_return = db.query(SaleReturn).options(
        joinedload(SaleReturn.sale),
        joinedload(SaleReturn.user),
        joinedload(SaleReturn.branch),
        joinedload(SaleReturn.supervisor),
        selectinload(SaleReturn.items).joinedload(SaleReturnItem.variant)
    ).filter(SaleReturn.id == return_id, SaleReturn.organization_id == org_id).first()

    if not db_return:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")
    return db_return

@router.post("/{return_id}/approve", response_model=SaleReturn)
def approve_return_endpoint(
    return_id: str,
    force: bool = Query(False, description="Override fat-finger guard for large CASH refunds (>$10k). UI must confirm twice."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    if str(current_user.role.value) not in ["ADMINISTRADOR", "DUEÑO", "GERENTE"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para aprobar devoluciones")

    # Verify the return belongs to the current org before acting on it
    from app.models.returns import SaleReturn as SRModel
    existing = db.query(SRModel).filter(
        SRModel.id == return_id,
        SRModel.organization_id == org_id
    ).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")

    try:
        return crud_returns.approve_return(
            db, return_id, current_user.id,
            organization_id=org_id, force=force,
        )
    except crud_returns.CashSessionClosedError as e:
        # 409 Conflict: estado de la caja, no input inválido.
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{return_id}/reject", response_model=SaleReturn)
def reject_return_endpoint(
    return_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    if str(current_user.role.value) not in ["ADMINISTRADOR", "DUEÑO", "GERENTE"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para rechazar devoluciones")

    from app.models.returns import SaleReturn as SRModel
    existing = db.query(SRModel).filter(
        SRModel.id == return_id,
        SRModel.organization_id == org_id
    ).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")

    try:
        return crud_returns.reject_return(
            db, return_id, current_user.id, organization_id=org_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))