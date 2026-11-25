from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from typing import List, Dict, Any, Optional
from datetime import date
from app.core.database import get_db
from app.schemas.returns import AutorizarConPin, SaleReturn, SaleReturnCreate, SaleReturnSummary
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

    # Roles de sucursal: solo devuelven ventas de la suya. La cajera, además,
    # solo dentro del plazo de la tienda. Se lanza antes del try (su except lo
    # volvería 500).
    from app.services import devoluciones as dev
    from app.services.ventas_cajero import es_cajero
    _assert_venta_devolvible(db, sale, current_user)
    de_caja = es_cajero(current_user)

    if return_in.reason_code is not None:
        if return_in.reason_code not in dev.MOTIVOS:
            raise HTTPException(status_code=400, detail="Motivo de devolución desconocido.")
        return_in.reason = dev.texto_motivo(return_in.reason_code, return_in.reason)

    mi_turno = dev.sesion_abierta_de(db, current_user.id, current_user.branch_id)
    if de_caja:
        # El dinero regresa por donde entró: efectivo solo si se pagó en efectivo.
        permitidos = dev.metodos_de_reembolso(sale)
        if str(return_in.refund_method.value) not in permitidos:
            raise HTTPException(
                status_code=400,
                detail="El reembolso va por el mismo método con que se pagó el ticket ("
                       + ", ".join(permitidos) + "). Para otro método pide al gerente.",
            )
        if return_in.refund_method.value == "CASH" and mi_turno is None:
            raise HTTPException(
                status_code=409,
                detail="Abre tu caja antes de devolver en efectivo: el dinero sale de tu turno.",
            )
        # El dinero sale del turno de quien devuelve, no del que mande la pantalla.
        return_in.cash_session_id = mi_turno
    elif return_in.cash_session_id is None:
        return_in.cash_session_id = mi_turno

    try:
        creada = crud_returns.create_return(
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

    # La caja devuelve sola hasta el monto que fije la tienda (0 = nunca).
    # Arriba de eso queda PENDING: el gerente la autoriza con su PIN en la
    # misma caja (`/{id}/autorizar`) o la aprueba después.
    if de_caja:
        libre = dev.monto_libre(db, org_id)
        if libre > 0 and creada.total_refunded <= libre:
            return_id = creada.id
            try:
                return crud_returns.approve_return(
                    db, return_id, current_user.id, organization_id=org_id,
                    autorizacion=dev.AUT_POLITICA,
                )
            except ValueError:
                # No se pudo aprobar sola (p. ej. monto alto en efectivo):
                # queda pendiente, como cualquier otra.
                db.rollback()
                from app.models.returns import SaleReturn as SRModel
                return db.query(SRModel).filter(SRModel.id == return_id).first()
    return creada


def _assert_venta_devolvible(db: Session, sale, current_user: User) -> None:
    """Ámbito de la devolución: roles de sucursal, solo ventas de la suya; la
    caja, además, solo dentro del plazo de la tienda."""
    from app.routers.sales import _is_hq_role
    from app.services.ventas_cajero import dias_ventas_caja, es_cajero, venta_visible_para_cajero
    if not _is_hq_role(current_user) and sale.branch_id != current_user.branch_id:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if es_cajero(current_user) and not venta_visible_para_cajero(sale, current_user, db):
        dias = dias_ventas_caja(db, current_user)
        plazo = "Solo puedes devolver ventas de hoy." if dias == 0 else (
            f"Esta venta tiene más de {dias} días: ya pasó el plazo de devolución en caja."
        )
        raise HTTPException(status_code=403, detail=f"{plazo} Pide al gerente.")


@router.get("/motivos")
def motivos_de_devolucion(current_user: User = Depends(get_current_user)):
    """Catálogo de motivos (code, label y si por omisión la pieza regresa a stock)."""
    from app.services.devoluciones import catalogo_motivos
    return catalogo_motivos()


@router.get("/sale/{sale_id}/piezas")
def piezas_devolvibles(
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Lo que la caja necesita para devolver un ticket: por pieza, cuánto se
    vendió, cuánto ya se devolvió y cuánto queda; los métodos de reembolso
    permitidos; si hay una solicitud pendiente; y el monto que la caja puede
    devolver sin gerente."""
    from sqlalchemy.orm import joinedload
    from app.models.returns import SaleReturn as SRModel
    from app.models.sales import SalesDocument
    from app.services import devoluciones as dev
    from app.services.ventas_cajero import es_cajero

    sale = db.query(SalesDocument).options(joinedload(SalesDocument.payments)).filter(
        SalesDocument.id == sale_id, SalesDocument.organization_id == org_id,
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    _assert_venta_devolvible(db, sale, current_user)

    pendiente = db.query(SRModel.id, SRModel.total_refunded).filter(
        SRModel.sale_id == sale.id, SRModel.organization_id == org_id, SRModel.status == "PENDING",
    ).first()
    metodos = dev.metodos_de_reembolso(sale)
    return {
        "sale": {
            "id": sale.id, "series": sale.series, "folio": sale.folio,
            "created_at": sale.created_at, "customer_name": sale.customer_name,
            "total_amount": sale.total_amount,
            "status": str(getattr(sale.status, "value", sale.status)),
        },
        "piezas": dev.piezas_del_ticket(db, sale),
        "metodos": metodos,
        "pendiente": {"id": pendiente[0], "total": pendiente[1]} if pendiente else None,
        "motivos": dev.catalogo_motivos(),
        # Solo la caja tiene tope; a un rol gerencial no le aplica.
        "monto_libre": dev.monto_libre(db, org_id) if es_cajero(current_user) else None,
        "es_caja": es_cajero(current_user),
    }


@router.post("/{return_id}/autorizar", response_model=SaleReturn)
def autorizar_con_pin(
    return_id: str,
    cuerpo: AutorizarConPin,
    force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Autoriza una devolución pendiente EN LA CAJA con el PIN de un gerente
    (el mismo PIN de supervisor de la reimpresión, con su mismo límite de
    intentos). Queda aprobada a nombre del gerente; el efectivo sale del turno
    de la caja que la registró."""
    from app.models.returns import SaleReturn as SRModel
    from app.routers.sales import _is_hq_role
    from app.services import devoluciones as dev
    from app.services.reprint_auth import (
        bloqueo_restante, limpiar_intentos, registrar_intento_fallido, verificar_pin_supervisor,
    )

    existente = db.query(SRModel).filter(SRModel.id == return_id, SRModel.organization_id == org_id).first()
    if not existente or (not _is_hq_role(current_user) and existente.branch_id != current_user.branch_id):
        raise HTTPException(status_code=404, detail="Devolución no encontrada")
    if existente.status != "PENDING":
        raise HTTPException(status_code=400, detail="La devolución ya no está pendiente.")

    restante = bloqueo_restante(org_id, current_user.id)
    if restante is not None:
        raise HTTPException(
            status_code=423,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {restante} segundos.",
        )
    supervisor = verificar_pin_supervisor(db, org_id, cuerpo.pin, branch_id=existente.branch_id)
    if not supervisor:
        registrar_intento_fallido(org_id, current_user.id)
        raise HTTPException(status_code=403, detail={"code": "PIN_INCORRECTO", "message": "PIN incorrecto"})
    limpiar_intentos(org_id, current_user.id)

    try:
        return crud_returns.approve_return(
            db, return_id, supervisor.id, organization_id=org_id, force=force,
            autorizacion=dev.AUT_PIN,
        )
    except crud_returns.CashSessionClosedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    from app.models.sales import SalesDocument
    from sqlalchemy.orm import joinedload, selectinload
    venta = db.query(SalesDocument).filter(
        SalesDocument.id == sale_id, SalesDocument.organization_id == org_id,
    ).first()
    if venta is not None:      # sin venta la lista sale vacía, como antes
        _assert_venta_devolvible(db, venta, current_user)
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
    """Lista devoluciones de la organización. Fechas en día de México (una sola
    fecha = ese día); sin fechas, todo el historial (la pantalla pondrá el rango
    en la Fase 3). Ámbito: roles de oficina ven toda la org o la sucursal
    pedida; los demás la suya."""
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

    if start_date or end_date:
        periodo = mv.periodo_de_query(start_date, end_date)
        query = query.filter(mv.dia_mx(SaleReturn.created_at) >= periodo.inicio,
                             mv.dia_mx(SaleReturn.created_at) <= periodo.fin)

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