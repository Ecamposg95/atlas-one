# app/routers/cash.py
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from decimal import Decimal
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# La zona del negocio vive en un solo lugar (app/core/fechas.py); aquí se
# conserva el nombre MX_TZ porque lo usan decenas de líneas de este módulo.
from app.core.fechas import ZONA_NEGOCIO as MX_TZ

from app.core.database import get_db
from app.models import CashSession, CashSessionStatus, Payment, PaymentMethod, SalesDocument, DocumentStatus, CashMovement
from app.schemas.cash import CashSessionCreate, CashSessionRead, CashSessionClose, CashMovementCreate, CashMovementRead, CashSessionCloseGuided, OpeningBalanceCorrection
from app.core.security import get_current_user
from app.models import User
from app.models.users import Role
from app.core.tenant_context import get_current_active_organization

router = APIRouter()

# Umbral por encima del cual una salida de efectivo exige rol GERENTE+.
# Espeja el patron que ya existe para reembolsos en efectivo
# (app/crud/returns.py:28, LARGE_CASH_REFUND_THRESHOLD).
LARGE_CASH_OUTFLOW_THRESHOLD = Decimal("2000")
MIN_REASON_LENGTH = 10
ROLES_SALIDA_ALTA = {"ADMINISTRADOR", "DUEÑO", "GERENTE"}


def _lock_cash_session_query(query):
    """Aplica FOR UPDATE a la consulta de CashSession antes de leerla.

    Ronda de correcciones 1 (hallazgo Importante): sin este bloqueo, dos
    salidas concurrentes contra la misma sesion (mismo cajero operando
    varias terminales — ver `open_session` arriba) pueden leer el mismo
    `disponible` en `_validar_salida` antes de que ninguna haga commit,
    pasar ambas el chequeo de 409 y dejar la caja en negativo, que es
    justo lo que esta tarea promete impedir.

    Mismo patron que `app/crud/returns.py:144` (`with_for_update()` sobre
    la fila antes de decidir) y `app/modules/kitchen/services.py::_lock_ticket`.
    El bloqueo cubre el intervalo desde esta lectura hasta el commit que
    hace el endpoint tras insertar el `CashMovement`, porque es la misma
    sesion de SQLAlchemy/transaccion. No hace falta condicionarlo por
    dialecto (a diferencia del advisory lock de `app/utils/folios.py`):
    `with_for_update()` es un no-op silencioso en SQLite (no lanza error,
    solo no serializa — igual que documenta `_lock_ticket`), y sí bloquea
    la fila en Postgres, que es donde corre producción.
    """
    return query.with_for_update()


def _validar_salida(db: Session, session: CashSession, current_user: User, amount: Decimal, reason: str) -> None:
    """Guardas de una salida de efectivo. Lanza HTTPException si no procede.

    Orden de las validaciones (importa para el resultado):
    1) motivo (422) — siempre, es la mas barata.
    2) saldo disponible (409) — una salida que deja la caja en negativo es
       un error de estado, independiente de quien la pida.
    3) umbral por rol (403) — solo aplica si el monto SI cabe en la caja;
       de lo contrario un cajero pidiendo un monto alto e insuficiente
       recibiria "no autorizado" en vez de "no hay ese efectivo", que es
       el error real. Ver tests/test_cash_outflow_guards.py::
       test_no_puede_dejar_la_caja_en_negativo (monto 5000 sobre fondo de
       100: es a la vez > umbral y > disponible, y debe ganar el 409).
    """
    motivo = (reason or "").strip()
    if len(motivo) < MIN_REASON_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Describe el motivo de la salida (al menos {MIN_REASON_LENGTH} caracteres).",
        )
    from app.services.cash_reconciliation import compute_expected_cash
    disponible = Decimal(str(compute_expected_cash(db, session).expected))
    if amount > disponible:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La caja tiene {disponible} disponible; no se puede sacar {amount}."
            ),
        )
    if amount > LARGE_CASH_OUTFLOW_THRESHOLD:
        rol = str(getattr(current_user.role, "value", current_user.role))
        if rol not in ROLES_SALIDA_ALTA:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Una salida mayor a {LARGE_CASH_OUTFLOW_THRESHOLD} requiere "
                    f"autorizacion de un gerente o el dueño."
                ),
            )

@router.get("/status", response_model=Optional[CashSessionRead])
def get_current_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Devuelve la sesión abierta actual del usuario, o null si no hay."""
    session = db.query(CashSession).filter(
        CashSession.user_id == current_user.id,
        CashSession.branch_id == current_user.branch_id,
        CashSession.status == CashSessionStatus.OPEN
    ).first()
    return session

@router.get("/history", response_model=List[CashSessionRead])
def read_cash_history(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Historial de cortes de caja de la sucursal (ATS-7: solo usuarios con sucursal asignada)"""
    if not current_user.branch_id:
        # Usuarios HQ no operan caja; redirigir a reportes por sucursal
        raise HTTPException(403, "Los usuarios HQ no tienen historial de caja. Consulte los reportes por sucursal.")
    return db.query(CashSession).filter(
        CashSession.branch_id == current_user.branch_id
    ).order_by(CashSession.opened_at.desc()).offset(skip).limit(limit).all()

@router.post("/open", response_model=CashSessionRead)
def open_session(
    session_in: CashSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 2. Validar Sucursal primero (necesitamos branch_id para el guard)
    if not current_user.branch_id:
        raise HTTPException(400, "Tu usuario no tiene una sucursal asignada. Contacte al administrador.")

    # 1. Idempotente: si ya hay sesión OPEN del usuario en esta sucursal,
    # retornarla en lugar de error. Esto soporta el modelo "1 cajero opera
    # 1-3 PCs simultáneamente, todas comparten la misma sesión de caja
    # porque el efectivo va a una sola caja física" (Track 1 bug-fix).
    active = db.query(CashSession).filter(
        CashSession.user_id == current_user.id,
        CashSession.branch_id == current_user.branch_id,
        CashSession.status == CashSessionStatus.OPEN
    ).first()
    if active:
        # Antes esto devolvia 200 con la sesion existente y descartaba en
        # silencio el opening_balance recibido. El cajero que corregia un fondo
        # mal capturado veia "listo" sin que nada cambiara, y su unico recurso
        # era registrar una entrada de efectivo falsa (Task 5).
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ya tienes una caja abierta con fondo {active.opening_balance}. "
                f"Para corregirlo usa PATCH /cash/sessions/{active.id}/opening-balance."
            ),
        )

    # 3. Crear Sesión — organization_id derivado del branch para cumplir multi-tenancy
    from app.models.organization import Branch as _Branch
    branch = db.query(_Branch).filter(_Branch.id == current_user.branch_id).first()
    if not branch:
        raise HTTPException(400, "Sucursal inválida.")
    new_session = CashSession(
        organization_id=branch.organization_id,
        branch_id=current_user.branch_id,
        user_id=current_user.id,
        status=CashSessionStatus.OPEN,
        opening_balance=session_in.opening_balance,
        opened_at=datetime.now(timezone.utc)
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    logger.info(
        "CASH_OPEN: session_id=%s user_id=%s username=%s branch_id=%s opening_balance=%s",
        new_session.id, current_user.id, current_user.username,
        current_user.branch_id, session_in.opening_balance
    )
    return new_session


@router.patch("/sessions/{session_id}/opening-balance", response_model=CashSessionRead)
def corregir_saldo_inicial(
    session_id: int,
    payload: OpeningBalanceCorrection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Corrige el fondo declarado al abrir, mientras la caja siga limpia.

    Es un cambio de estado declarado y auditado, no una transaccion: si ya hay
    ventas o movimientos, cambiar el fondo reescribiria la historia y la
    correccion deja de ser correccion. Esta es la unica via legitima para
    arreglar un fondo mal capturado (Task 5) — antes el unico recurso del
    cajero era inventar una "entrada de efectivo".
    """
    session = _lock_cash_session_query(db.query(CashSession).filter(
        CashSession.id == session_id,
        CashSession.organization_id == org_id,
    )).first()
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    if session.status != CashSessionStatus.OPEN:
        raise HTTPException(status_code=409, detail="La caja ya está cerrada.")

    # Hallazgo MEDIA-ALTA (revisión final): antes esta ruta solo filtraba por
    # organization_id, así que cualquier usuario de la organización —incluido
    # uno de otra sucursal— podía corregir el fondo del turno de otra
    # persona. Misma regla que ya aplica `/sessions/{id}/close-guided` (línea
    # ~419): el dueño del turno, o un rol con visibilidad gerencial
    # (ROLES_SALIDA_ALTA = ADMINISTRADOR/DUEÑO/GERENTE).
    if session.user_id != current_user.id and current_user.role not in ROLES_SALIDA_ALTA:
        raise HTTPException(
            status_code=403,
            detail="Solo el dueño del turno o un GERENTE/ADMINISTRADOR/DUEÑO puede corregir el fondo.",
        )

    tiene_movimientos = db.query(CashMovement).filter(
        CashMovement.session_id == session.id).count() > 0
    tiene_ventas = db.query(SalesDocument).filter(
        SalesDocument.cash_session_id == session.id).count() > 0
    if tiene_movimientos or tiene_ventas:
        raise HTTPException(
            status_code=409,
            detail=(
                "La caja ya tiene movimientos o ventas: el fondo no se puede "
                "corregir. Registra un ajuste con autorización."
            ),
        )

    anterior = session.opening_balance
    session.opening_balance = payload.opening_balance

    # No existe un evento dedicado a "correccion de fondo" en CashAuditEvent;
    # reutilizamos SESSION_OPENED (el evento mas cercano semanticamente:
    # redeclara el estado con el que arranca la sesion). La etiqueta que
    # muestra la pantalla de auditoria (PlatformCashAudit.tsx) para este
    # evento seguira diciendo "Caja abierta" sin importar el payload, asi
    # que la unica forma de que una correccion no se confunda con una
    # apertura real es que el texto de `reason` lo diga por si solo — esa
    # pantalla (TimelineRow) solo renderiza `ev.payload?.reason`, no
    # `motivo` (Ronda de correcciones 1, hallazgo Importante). Usamos la
    # misma clave que ya usan MANUAL_INFLOW/MANUAL_OUTFLOW para que el
    # dato llegue a la UI sin tocarla, y conservamos antes/despues/
    # correccion aparte para consultas programaticas sobre el audit log.
    reason_legible = (
        f"Corrección de fondo inicial: {anterior} → {payload.opening_balance}. "
        f"Motivo: {payload.reason}"
    )
    from app.services.cash_audit import audit_cash_event
    from app.models.cash_audit import CashAuditEvent
    audit_cash_event(
        db,
        event_type=CashAuditEvent.SESSION_OPENED,
        organization_id=session.organization_id,
        session_id=session.id,
        branch_id=session.branch_id,
        user_id=current_user.id,
        amount=payload.opening_balance,
        related_table="cash_sessions",
        related_id=str(session.id),
        payload={
            "reason": reason_legible,
            "correccion": True,
            "antes": str(anterior),
            "despues": str(payload.opening_balance),
            "motivo": payload.reason,
        },
    )
    db.commit()
    db.refresh(session)
    return session


def _apply_close_to_session(
    db: Session,
    session: CashSession,
    current_user: User,
    closing_balance: Decimal,
    notes: Optional[str],
) -> CashSessionRead:
    if closing_balance is None or closing_balance < 0:
        raise HTTPException(400, "El saldo de cierre debe ser mayor o igual a cero.")

    # H-7: Bloquear cierre si quedan tickets pausados sin convertir asociados
    # a esta sesión. ParkedTicket no tiene cash_session_id, así que se infiere
    # via (user_id, branch_id, created_at >= session.opened_at). Active =
    # deleted_at IS NULL AND (expires_at IS NULL OR expires_at > now), igual
    # que `list_parked_tickets` en sales.py.
    from app.models import ParkedTicket
    now_check = datetime.now(timezone.utc)
    pending_parked = db.query(ParkedTicket).filter(
        ParkedTicket.user_id == session.user_id,
        ParkedTicket.branch_id == session.branch_id,
        ParkedTicket.created_at >= session.opened_at,
        ParkedTicket.deleted_at == None,  # noqa: E711
        ((ParkedTicket.expires_at == None) | (ParkedTicket.expires_at > now_check)),  # noqa: E711
    ).count()
    if pending_parked > 0:
        raise HTTPException(
            409,
            f"Hay {pending_parked} tickets pausados sin convertir. "
            "Reanude o descarte antes de cerrar turno."
        )

    # Fórmula de `expected` consolidada en `app/services/cash_reconciliation.py`.
    # Misma fuente que `get_session_audit_data` (UI dashboard) — el cajero ve
    # exactamente el número que se persiste como `difference`.
    from app.services.cash_reconciliation import compute_expected_cash, compute_closure_warnings
    breakdown = compute_expected_cash(db, session)
    diff = Decimal(str(closing_balance)) - breakdown.expected

    # F2: structured warnings (non-blocking — cajero ya decidió contar) +
    # logged for audit. Se devuelven en la respuesta HTTP (ver el
    # `CashSessionRead` que arma cada endpoint /close) para que la UI las
    # muestre. db/session habilitan W4 (SALES_WITHOUT_SESSION).
    closure_warnings = compute_closure_warnings(
        breakdown, Decimal(str(closing_balance)), db=db, session=session,
    )
    if closure_warnings:
        for w in closure_warnings:
            # .get(): no todas las alertas traen actual/threshold (p.ej.
            # SALES_WITHOUT_SESSION, que no compara contra un umbral numérico).
            logger.warning(
                "CASH_CLOSE_WARNING: session_id=%s code=%s severity=%s actual=%s threshold=%s",
                session.id, w["code"], w["severity"], w.get("actual"), w.get("threshold"),
            )

    # Actualizar y Cerrar
    now_utc = datetime.now(timezone.utc)
    session.status = CashSessionStatus.CLOSED
    session.closed_at = now_utc
    session.closing_balance = closing_balance
    session.total_cash_sales = breakdown.net_cash
    session.total_change_given = breakdown.change_given
    session.difference = diff
    session.notes = notes

    # F3: audit row BEFORE commit so it's atomic with the close.
    from app.services.cash_audit import audit_cash_event
    from app.models.cash_audit import CashAuditEvent
    audit_cash_event(
        db,
        event_type=CashAuditEvent.SESSION_CLOSED,
        organization_id=session.organization_id,
        session_id=session.id,
        branch_id=session.branch_id,
        user_id=current_user.id,
        amount=Decimal(str(closing_balance)),
        related_table="cash_sessions",
        related_id=str(session.id),
        expected_running_total=breakdown.expected,
        payload={
            "closing_balance": float(closing_balance),
            "expected": float(breakdown.expected),
            "difference": float(diff),
            "warnings": closure_warnings,
            "breakdown": {
                "opening": float(breakdown.opening),
                "gross_cash": float(breakdown.gross_cash),
                "change_given": float(breakdown.change_given),
                "net_cash": float(breakdown.net_cash),
                "manual_inflows": float(breakdown.manual_inflows),
                "manual_outflows": float(breakdown.manual_outflows),
                "refund_cash_outflows": float(breakdown.refund_cash_outflows),
            },
        },
    )

    db.commit()
    db.refresh(session)

    logger.info(
        "CASH_CLOSE: session_id=%s user_id=%s username=%s branch_id=%s "
        "closing_balance=%s expected=%s difference=%s",
        session.id, current_user.id, current_user.username,
        current_user.branch_id, closing_balance, breakdown.expected, diff
    )
    # Defecto del brief original: `close_session` declaraba response_model=
    # CashSessionRead pero devolvía el ORM `session` crudo, que no tiene
    # campo `warnings` — closure_warnings se calculaba y solo quedaba en el
    # audit payload de arriba, nunca llegaba al cajero. Se construye la
    # respuesta explícitamente para que sí viaje en el HTTP response.
    return CashSessionRead.model_validate(session).model_copy(
        update={"warnings": closure_warnings}
    )


@router.post("/close", response_model=CashSessionRead)
def close_session(
    close_data: CashSessionClose,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Buscar sesión activa de esta sucursal (ATS-3: branch_id evita cerrar sesión equivocada)
    session = db.query(CashSession).filter(
        CashSession.user_id == current_user.id,
        CashSession.branch_id == current_user.branch_id,
        CashSession.status == CashSessionStatus.OPEN
    ).first()
    if not session:
        raise HTTPException(400, "No hay sesión abierta para cerrar.")
    return _apply_close_to_session(db, session, current_user, close_data.closing_balance, close_data.notes)


@router.post("/sessions/{session_id}/close-guided", response_model=CashSessionRead)
def close_session_guided(
    session_id: int,
    payload: CashSessionCloseGuided,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization_id: int = Depends(get_current_active_organization),
):
    from app.models.organization import Branch
    session = (
        db.query(CashSession)
        .join(Branch, Branch.id == CashSession.branch_id)
        .filter(
            CashSession.id == session_id,
            Branch.organization_id == organization_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.closed_at is not None:
        raise HTTPException(status_code=409, detail="session already closed")
    if session.user_id != current_user.id and current_user.role != Role.GERENTE:
        raise HTTPException(status_code=403, detail="only the shift owner or branch GERENTE can close")
    return _apply_close_to_session(db, session, current_user, payload.counted_cash, payload.notes)

# --------------------------------------------------------------------------
# MOVIMIENTOS DE CAJA (Entrada / Salida)
# --------------------------------------------------------------------------

@router.post("/movements", response_model=CashMovementRead)
def register_cash_movement(
    payload: CashMovementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Registra una entrada (IN) o salida (OUT) de efectivo en la sesión activa."""
    query = db.query(CashSession).filter(
        CashSession.id == payload.session_id,
        CashSession.user_id == current_user.id,
        CashSession.status == CashSessionStatus.OPEN
    )
    # Bloqueo de fila solo para salidas (OUT): es la rama que decide un
    # saldo disponible y luego escribe — la que puede correr en carrera.
    # `payload.type` ya esta disponible aqui, antes de tocar la BD.
    if payload.type == "OUT":
        query = _lock_cash_session_query(query)
    session = query.first()

    if not session:
        raise HTTPException(status_code=404, detail="Sesión de caja no encontrada o cerrada")

    if payload.type not in ("IN", "OUT"):
        raise HTTPException(status_code=400, detail="Tipo debe ser 'IN' o 'OUT'")

    # Track 1: bloquear montos no positivos. Antes aceptaba 0 y negativos.
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")

    # Task 3: una salida (OUT) por esta ruta recibe las mismas guardas que
    # /outflow (motivo, saldo disponible, umbral por rol). Una entrada (IN)
    # solo valida el motivo, igual que /inflow.
    if payload.type == "OUT":
        _validar_salida(db, session, current_user, payload.amount, payload.concept)
    else:
        motivo_in = (payload.concept or "").strip()
        if len(motivo_in) < MIN_REASON_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"Describe el motivo de la entrada (al menos {MIN_REASON_LENGTH} caracteres).",
            )

    movement = CashMovement(
        session_id=session.id,
        type=payload.type,
        amount=payload.amount,
        reason=payload.concept or ("Entrada de efectivo" if payload.type == "IN" else "Salida de efectivo"),
        created_by_user_id=current_user.id,
    )
    db.add(movement)
    db.flush()
    # Task 4: esta ruta era la unica de las tres que no dejaba rastro en el
    # audit log (/inflow y /outflow ya lo hacian). Mismo patron que ambas.
    from app.services.cash_audit import audit_cash_event
    from app.models.cash_audit import CashAuditEvent
    audit_cash_event(
        db,
        event_type=CashAuditEvent.MANUAL_OUTFLOW if payload.type == "OUT" else CashAuditEvent.MANUAL_INFLOW,
        organization_id=session.organization_id,
        session_id=session.id,
        branch_id=session.branch_id,
        user_id=current_user.id,
        amount=payload.amount,
        related_table="cash_movements",
        related_id=str(movement.id),
        payload={"reason": movement.reason},
    )
    db.commit()
    db.refresh(movement)
    return movement

def get_session_audit_data(db: Session, session_id: int):
    """
    Centraliza el cálculo de métricas financieras para una sesión de caja.
    Utilizado por la UI, Ticket Térmico y PDF.
    """
    session = db.query(CashSession).filter(CashSession.id == session_id).first()
    if not session:
        return None

    # Fetch Organization
    from app.models.organization import Organization
    org = db.query(Organization).filter(Organization.id == session.branch.organization_id).first()
    org_name = org.name if org else "Atlas ERP"
    session_org_id = session.branch.organization_id

    # Filtro de ventas asociado a la sesión (con fallback legacy) — viene del
    # mismo helper que usa `_apply_close_to_session` para garantizar que el
    # esperado mostrado en UI = esperado persistido al cerrar.
    from app.services.cash_reconciliation import (
        compute_expected_cash,
        session_sales_filter,
        CASH_INCLUDED_STATUSES,
        SALES_REPORT_STATUSES,
    )

    _session_filter = session_sales_filter(session)
    close_limit = session.closed_at or datetime.now(timezone.utc)

    # 1. Desglose detallado por Métodos de Pago (Pagadas + Devueltas).
    # CASH_INCLUDED_STATUSES aquí: esto suma `Payment.amount`, lo realmente
    # cobrado por método, no `total_amount`. NO incluye PENDING (venta a
    # crédito con abono) — ver el comentario junto a la definición de
    # CASH_INCLUDED_STATUSES en app/services/cash_reconciliation.py: hoy un
    # abono en efectivo de una venta a crédito no aparece en ningún corte,
    # hueco latente y aceptado mientras ningún cliente use crédito.
    # Incluimos REFUNDED_PARTIAL/TOTAL por la misma razón de siempre: las
    # Payment rows reflejan la entrada física al cajón en su momento, y los
    # refunds salen como CashMovement OUT separados. Excluirlas aquí "borra"
    # la entrada original mientras se sigue restando el OUT → expected_cash
    # negativo en días con devoluciones.
    payment_stats = db.query(
        Payment.method,
        func.count(Payment.id).label("count"),
        func.sum(Payment.amount).label("total")
    ).join(SalesDocument).filter(
        _session_filter,
        SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
    ).group_by(Payment.method).all()

    methods_map = {p.method: {"total": float(p.total), "count": p.count} for p in payment_stats}

    # 2. Impuestos y Subtotal (NETOS post-refund).
    # SALES_REPORT_STATUSES aquí (NO PENDING): esto suma `tax_amount`/
    # `subtotal` del SalesDocument completo, no lo realmente cobrado. Para
    # PAID/REFUNDED_* es seguro porque `approve_return` reescribe esos campos
    # al valor neto tras la devolución — incluir REFUNDED_* da el revenue neto
    # real del día (PAID-only perdería la contribución parcial de ventas
    # devueltas). PENDING no tiene ese ajuste: su tax_amount/subtotal es el de
    # la venta completa, deuda incluida — incluirlo aquí infla estos totales
    # con impuestos de dinero que todavía no se cobra.
    invoice_stats = db.query(
        func.sum(SalesDocument.tax_amount).label("taxes"),
        func.sum(SalesDocument.subtotal).label("subtotal")
    ).filter(
        _session_filter,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
    ).first()

    total_taxes = float(invoice_stats.taxes or 0)
    total_subtotal = float(invoice_stats.subtotal or 0)

    # 3b. Devoluciones aprobadas en esta sesión (para UI / counts; el efecto
    # monetario sobre `expected` se calcula vía CashMovement OUT en el helper).
    from sqlalchemy.orm import joinedload
    from app.models.returns import SaleReturn as SaleReturnModel
    # `joinedload(sale)`: el detalle del corte lee `r.sale` de cada devolución
    # para armar el folio — sin esto son N consultas extra por corte.
    session_returns = db.query(SaleReturnModel).options(
        joinedload(SaleReturnModel.sale)
    ).filter(
        SaleReturnModel.cash_session_id == session.id,
        SaleReturnModel.status == "APPROVED"
    ).all()

    total_returns_count = len(session_returns)
    total_returns_amount = float(sum(r.total_refunded for r in session_returns))

    # Corte con historia: el conteo y el total no dicen QUÉ se devolvió. El
    # folio de la venta original es lo que permite rastrearla, la marca de
    # efectivo separa las que afectan el arqueo de las que no, y la hora dice
    # CUÁNDO salió el dinero del cajón.
    #
    # La hora es la de APROBACIÓN, no la de creación de la solicitud — son
    # eventos distintos, y lo que le importa al lector del corte es el
    # segundo. Fuente PRIMARIA: `cash_audit_log` (append-only, nunca se hace
    # UPDATE sobre él). `approve_return` (app/crud/returns.py) escribe un
    # REFUND_APPROVED con `related_table="sale_returns"` y
    # `related_id=db_return.id` en el mismo commit que la aprobación.
    #
    # `AuditMixin.updated_at` NO sirve como fuente primaria aunque su
    # `onupdate` se dispare de forma confiable AL APROBAR: el problema es que
    # no se dispara *sólo* ahí. `app/routers/platform/users.py` hace
    # `db.query(SaleReturn).filter(SaleReturn.supervisor_id == user_id)
    # .update({"supervisor_id": None}, synchronize_session=False)` al borrar
    # un usuario, SIN filtro de status — ese UPDATE masivo pisa `updated_at`
    # de devoluciones APROBADAS HISTÓRICAS con la hora del borrado, y una
    # reimpresión de un corte viejo mostraría esa hora. El audit log, al ser
    # insert-only, no puede driftear.
    #
    # Cadena de fuentes: audit log → `updated_at` (failsafe: `audit_cash_event`
    # se traga sus excepciones, la fila puede faltar; `session_returns` ya está
    # filtrada a APPROVED, así que `updated_at` es la aprobación) → `created_at`
    # (hora de la SOLICITUD, el último recurso).
    from app.models.cash_audit import CashAuditLog, CashAuditEvent
    _approved_ts_by_return_id = {}
    for _rid, _ts in db.query(CashAuditLog.related_id, CashAuditLog.ts).filter(
        CashAuditLog.session_id == session.id,
        CashAuditLog.organization_id == session_org_id,
        CashAuditLog.event_type == CashAuditEvent.REFUND_APPROVED,
        CashAuditLog.related_table == "sale_returns",
    ).all():
        if _rid is None or _ts is None:
            continue
        # Más de un evento para el mismo return_id no debería existir
        # (`approve_return` es idempotente: una 2ª aprobación devuelve el
        # registro sin re-auditar), pero si lo hubiera se conserva el MÁS
        # TEMPRANO — el primero es la aprobación real.
        if _rid not in _approved_ts_by_return_id or _ts < _approved_ts_by_return_id[_rid]:
            _approved_ts_by_return_id[_rid] = _ts

    # Sólo los cuatro valores de `PaymentMethod` (app/models/sales.py):
    # `SaleReturn.refund_method` es `Enum(PaymentMethod)`, así que no puede
    # tomar otro. Un método desconocido (dato viejo) cae en "other" en vez de
    # perderse — `by_method` tiene que sumar EXACTAMENTE `total`, ni un peso
    # más ni uno menos: es un desglose, no una segunda fuente.
    _by_method_totals = {"cash": 0.0, "card": 0.0, "transfer": 0.0, "other": 0.0}
    # `(_event_time, item)` para poder ordenar por la hora REAL del evento al
    # final: la PK de `sale_returns` es un UUID aleatorio y Postgres devuelve
    # las filas en el orden físico del heap (que cambia con cada UPDATE), así
    # que sin ORDER BY dos reimpresiones del MISMO corte pueden listar las
    # devoluciones en orden distinto. El orden no se puede pedir en SQL
    # porque la hora sale del audit log, no de una columna de esta tabla.
    _returns_sortable = []
    _session_day = (
        session.opened_at if session.opened_at.tzinfo
        else session.opened_at.replace(tzinfo=timezone.utc)
    ).astimezone(MX_TZ).date()
    for r in session_returns:
        _audit_ts = _approved_ts_by_return_id.get(r.id)
        if _audit_ts is not None:
            _event_time = _audit_ts
        elif r.updated_at is not None:
            _event_time = r.updated_at
        else:
            _event_time = r.created_at or session.opened_at
        if _event_time.tzinfo is None:
            _event_time = _event_time.replace(tzinfo=timezone.utc)

        _sale = r.sale
        _folio = None
        if _sale is not None:
            _serie = getattr(_sale, "series", None)
            _num = getattr(_sale, "folio", None)
            if _num:
                _folio = f"{_serie}-{_num}" if _serie else str(_num)

        _method_value = (
            r.refund_method.value if hasattr(r.refund_method, "value")
            else str(r.refund_method or "CASH")
        )
        _method_key = _method_value.lower()
        if _method_key not in _by_method_totals:
            _method_key = "other"
        _by_method_totals[_method_key] += float(r.total_refunded or 0)

        _event_mx = _event_time.astimezone(MX_TZ)
        # Una devolución aprobada en OTRA fecha (ruta `[POST-CLOSE]` de
        # `approve_return`: el gerente aprueba hoy una devolución cuya caja
        # cerró ayer) imprimiría una hora suelta como si fuera de esta
        # jornada. `cross_day` deja constancia y el ticket la marca.
        _cross_day = _event_mx.date() != _session_day
        # `is_cash` sale del MISMO `_method_key` que alimenta `by_method`: si
        # se derivaran por separado, una fila legada con `refund_method` NULL
        # caería en el bucket "cash" (por el `or "CASH"` de arriba) pero se
        # imprimiría sin la marca de efectivo — el renglón contradiría al
        # subtotal que él mismo alimentó.
        _returns_sortable.append((_event_time, {
            "time": _event_mx.strftime("%H:%M"),
            "date": _event_mx.strftime("%d/%m"),
            "cross_day": _cross_day,
            "folio": _folio or "-",
            "amount": float(r.total_refunded or 0),
            "is_cash": _method_key == "cash",
            "method": _method_key,
        }))

    # Orden estable y cronológico: el detalle es un relato, y un relato que
    # cambia de orden entre dos impresiones del mismo corte no se puede
    # auditar. Desempate por folio para que dos eventos con la misma marca de
    # tiempo tampoco bailen.
    _returns_sortable.sort(key=lambda it: (it[0], it[1]["folio"]))
    _returns_list = [item for _ts, item in _returns_sortable]

    # 4. Cálculo de KPIs
    # Ventas Totales NETAS post-refund — sale.total_amount está actualizado
    # por approve_return. Incluir REFUNDED_* para que el ticket muestre el
    # revenue real del día (PAID-only saltearía las ventas con devoluciones).
    # SALES_REPORT_STATUSES (NO PENDING): una venta a crédito con abono
    # parcial todavía no es ingreso reconocido por el total completo. Nota:
    # hoy `payment_stats` arriba tampoco incluye PENDING (ver
    # CASH_INCLUDED_STATUSES) — ambas tuplas coinciden por ahora, ver el
    # comentario de esa tupla para por qué no deben fusionarse.
    total_sales_query = db.query(func.sum(SalesDocument.total_amount)).filter(
        _session_filter,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
    ).scalar()
    grand_total_sales = float(total_sales_query or 0)

    # Tickets: sí cuentan ventas con devolución parcial (sigue siendo un ticket
    # vendido). REFUNDED_TOTAL técnicamente es venta cancelada pero el cliente
    # SÍ recorrió el flujo de checkout — para fines de "tickets atendidos" en
    # el corte cuenta como ticket. Coherente con grand_total_sales. PENDING NO
    # cuenta: el cliente todavía no terminó de pagar, no es un ticket cerrado.
    total_tickets = db.query(func.count(SalesDocument.id)).filter(
        _session_filter,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
    ).scalar() or 0
    avg_ticket = grand_total_sales / total_tickets if total_tickets > 0 else 0

    # Actividad más reciente
    last_payment = db.query(Payment.created_at).join(SalesDocument).filter(
        SalesDocument.seller_id == session.user_id,
        SalesDocument.branch_id == session.branch_id,
        Payment.created_at >= session.opened_at,
        Payment.created_at <= close_limit
    ).order_by(desc(Payment.created_at)).first()

    last_activity = last_payment[0] if last_payment else session.opened_at

    # 5. Reconciliación canónica — single source of truth.
    breakdown = compute_expected_cash(db, session)
    total_inflows = breakdown.manual_inflows
    total_outflows = breakdown.manual_outflows
    total_cash_refunds = breakdown.refund_cash_outflows
    manual_movements = breakdown.manual_movements
    expected_cash = breakdown.expected

    # Ajustar efectivo bruto → neto (restar cambio entregado) en methods_map.
    if PaymentMethod.CASH in methods_map:
        methods_map[PaymentMethod.CASH]["total"] = float(breakdown.net_cash)

    # Format Activity (Local)
    last_act_mx = last_activity.astimezone(MX_TZ) if last_activity.tzinfo else last_activity.replace(tzinfo=timezone.utc).astimezone(MX_TZ)

    return {
        "session": {
            "id": session.id,
            "opened_at": session.opened_at.astimezone(MX_TZ) if session.opened_at.tzinfo else session.opened_at.replace(tzinfo=timezone.utc).astimezone(MX_TZ),
            "closed_at": session.closed_at.astimezone(MX_TZ) if session.closed_at and session.closed_at.tzinfo else (session.closed_at.replace(tzinfo=timezone.utc).astimezone(MX_TZ) if session.closed_at else None),
            "opening_balance": float(session.opening_balance),
            "closing_balance": float(session.closing_balance or 0),
            "last_activity": last_act_mx,
            "user_name": session.user.full_name or session.user.username,
            "branch_name": session.branch.name if session.branch else "Principal",
            "organization_name": org_name
        },
        "payments": {
            "cash":         methods_map.get(PaymentMethod.CASH,     {"total": 0.0, "count": 0}),
            "card":         methods_map.get(PaymentMethod.CARD,     {"total": 0.0, "count": 0}),
            "transfer":     methods_map.get(PaymentMethod.TRANSFER, {"total": 0.0, "count": 0}),
            # Use string keys for methods not in the imported PaymentMethod enum
            "store_credit": methods_map.get("STORE_CREDIT",         {"total": 0.0, "count": 0}),
            "check":        methods_map.get("CHECK",                {"total": 0.0, "count": 0}),
            "others":       methods_map.get(PaymentMethod.OTHER,    {"total": 0.0, "count": 0}),
        },
        "movements": {
            "inflows": float(total_inflows),
            "outflows": float(total_outflows),
            "list": [
                {
                    "time": (m.created_at.astimezone(MX_TZ) if m.created_at.tzinfo else m.created_at.replace(tzinfo=timezone.utc).astimezone(MX_TZ)).strftime('%H:%M'),
                    "type": m.type,
                    "amount": float(m.amount),
                    "reason": m.reason
                } for m in manual_movements
            ]
        },
        "returns": {
            "count":        total_returns_count,
            "total":        total_returns_amount,
            "cash_refunds": float(total_cash_refunds),
            "list":         _returns_list,
            "by_method":    _by_method_totals,
        },
        "kpis": {
            "total_sales": float(grand_total_sales),
            "total_tickets": total_tickets,
            "avg_ticket": float(avg_ticket),
            "total_taxes": total_taxes,
            "subtotal": total_subtotal
        },
        "expected": {
            "cash_physical": float(expected_cash),
            "total_system": float(
                Decimal(str(grand_total_sales))
                + Decimal(str(session.opening_balance or 0))
                + total_inflows
                - total_outflows
                - total_cash_refunds
            )
        },
        "reconciliation": {
            "reported": float(session.closing_balance or 0),
            # Recalcular difference vivo (no leer session.difference persistido).
            # Sesiones cerradas antes del fix de devoluciones tienen `difference`
            # persistido con el cálculo viejo (REFUNDED_* excluidas) → el ticket
            # reimpreso mostraba `expected` correcto pero `difference` viejo y
            # la matemática (reported - expected ≠ difference) confundía al
            # cajero. El campo persistido queda como histórico de auditoría.
            "difference": float(
                Decimal(str(session.closing_balance or 0)) - expected_cash
            ),
            "diff_percent": float(((session.closing_balance or 0) / expected_cash - 1) * 100) if expected_cash > 0 else 0
        }
    }

@router.get("/summary")
def get_cash_summary(
    session_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Resumen detallado de la caja (UI Dashboard).

    Sin `session_id`: usa la sesión OPEN del usuario en su sucursal.
    Con `session_id`: devuelve la sesión específica si pertenece a la
    sucursal del usuario (cualquier estado). Permite consultar el resumen
    del turno cerrado del día sin reabrirlo.
    """
    if session_id is not None:
        session = db.query(CashSession).filter(
            CashSession.id == session_id,
            CashSession.branch_id == current_user.branch_id,
        ).first()
        if not session:
            raise HTTPException(404, "Sesión no encontrada en esta sucursal.")
    else:
        session = db.query(CashSession).filter(
            CashSession.user_id == current_user.id,
            CashSession.branch_id == current_user.branch_id,
            CashSession.status == CashSessionStatus.OPEN
        ).first()
        if not session:
            raise HTTPException(400, "No hay sesión abierta.")

    return get_session_audit_data(db, session.id)

@router.post("/inflow")
def register_inflow(
    amount: float,
    reason: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if amount <= 0:
        raise HTTPException(400, "El monto debe ser mayor a cero.")
    session = db.query(CashSession).filter(
        CashSession.user_id == current_user.id,
        CashSession.branch_id == current_user.branch_id,
        CashSession.status == CashSessionStatus.OPEN
    ).first()
    if not session:
        raise HTTPException(400, "No hay sesión de caja abierta.")

    # Task 3: una entrada solo exige un motivo real (sin umbral de rol ni
    # validacion de saldo — eso aplica a las salidas, no a las entradas).
    motivo_in = (reason or "").strip()
    if len(motivo_in) < MIN_REASON_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Describe el motivo de la entrada (al menos {MIN_REASON_LENGTH} caracteres).",
        )

    new_move = CashMovement(
        session_id=session.id,
        type="IN",
        amount=Decimal(str(amount)),
        reason=motivo_in,
        created_at=datetime.now(timezone.utc),
        created_by_user_id=current_user.id,
    )
    db.add(new_move)
    db.flush()
    # F3: audit row
    from app.services.cash_audit import audit_cash_event
    from app.models.cash_audit import CashAuditEvent
    audit_cash_event(
        db, event_type=CashAuditEvent.MANUAL_INFLOW,
        organization_id=session.organization_id,
        session_id=session.id, branch_id=session.branch_id,
        user_id=current_user.id, amount=Decimal(str(amount)),
        related_table="cash_movements", related_id=str(new_move.id),
        payload={"reason": new_move.reason},
    )
    db.commit()
    return {"message": "Entrada registrada", "amount": amount}

@router.post("/outflow")
def register_outflow(
    amount: float,
    reason: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if amount <= 0:
        raise HTTPException(400, "El monto debe ser mayor a cero.")
    # Bloqueo de fila: toda /outflow decide sobre `disponible` y escribe.
    session = _lock_cash_session_query(db.query(CashSession).filter(
        CashSession.user_id == current_user.id,
        CashSession.branch_id == current_user.branch_id,
        CashSession.status == CashSessionStatus.OPEN
    )).first()
    if not session:
        raise HTTPException(400, "No hay sesión de caja abierta.")

    monto = Decimal(str(amount))
    _validar_salida(db, session, current_user, monto, reason)

    new_move = CashMovement(
        session_id=session.id,
        type="OUT",
        amount=monto,
        reason=reason.strip(),
        created_at=datetime.now(timezone.utc),
        created_by_user_id=current_user.id,
    )
    db.add(new_move)
    db.flush()
    # F3: audit row
    from app.services.cash_audit import audit_cash_event
    from app.models.cash_audit import CashAuditEvent
    audit_cash_event(
        db, event_type=CashAuditEvent.MANUAL_OUTFLOW,
        organization_id=session.organization_id,
        session_id=session.id, branch_id=session.branch_id,
        user_id=current_user.id, amount=Decimal(str(amount)),
        related_table="cash_movements", related_id=str(new_move.id),
        payload={"reason": new_move.reason},
    )
    db.commit()
    return {"message": "Salida registrada", "amount": amount}

# --------------------------------------------------------------------------
# REPORTES DE CORTE (PDF & TICKET)
# --------------------------------------------------------------------------
from fastapi import Response
from app.utils.pdf_generator import generate_cash_cut_pdf

def _verify_session_access(db: Session, session_id: int, current_user: User) -> CashSession:
    """Verifica que el usuario tiene acceso a la sesion de caja (misma org, mismo branch si aplica)."""
    from app.models.users import UserOrganization
    session = db.query(CashSession).filter(CashSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    # Verificar organizacion via membership (User no tiene organization_id directo)
    user_org = db.query(UserOrganization.organization_id).filter(
        UserOrganization.user_id == current_user.id,
        UserOrganization.is_active == True
    ).first()
    if not user_org or session.branch.organization_id != user_org.organization_id:
        raise HTTPException(403, "No tienes acceso a esta sesión")
    if current_user.branch_id and session.branch_id != current_user.branch_id:
        raise HTTPException(403, "No tienes acceso a esta sesión")
    return session

@router.get("/{session_id}/audit-log")
def get_session_audit_log(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """F3: full event timeline for a cash session.

    ADMIN/DUEÑO/GERENTE-only. Returns chronological list of events with
    payload for inspection (replaces ad-hoc psql for discrepancy debugging).
    """
    if str(current_user.role.value) not in ("ADMINISTRADOR", "DUEÑO", "GERENTE"):
        raise HTTPException(403, "Solo administradores pueden consultar el audit log")
    session = _verify_session_access(db, session_id, current_user)
    from app.models.cash_audit import CashAuditLog
    rows = db.query(CashAuditLog).filter(
        CashAuditLog.session_id == session_id,
    ).order_by(CashAuditLog.id.asc()).all()
    return {
        "session_id": session_id,
        "branch_id": session.branch_id,
        "events": [
            {
                "id": r.id,
                "ts": r.ts.astimezone(MX_TZ).isoformat() if r.ts and r.ts.tzinfo
                       else (r.ts.replace(tzinfo=timezone.utc).astimezone(MX_TZ).isoformat() if r.ts else None),
                "event_type": r.event_type,
                "amount": float(r.amount) if r.amount is not None else None,
                "user_id": r.user_id,
                "related_table": r.related_table,
                "related_id": r.related_id,
                "payload": r.payload_json,
                "expected_running_total": (
                    float(r.expected_running_total)
                    if r.expected_running_total is not None else None
                ),
            }
            for r in rows
        ],
    }


@router.get("/{session_id}/pdf")
def get_cash_cut_pdf(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _verify_session_access(db, session_id, current_user)
    audit_data = get_session_audit_data(db, session_id)
    if not audit_data:
        raise HTTPException(404, "Sesión no encontrada")

    pdf_bytes = generate_cash_cut_pdf(audit_data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Corte_{session_id}.pdf"}
    )

@router.get("/{session_id}/ticket")
def get_cash_cut_ticket(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retorna un JSON estructurado para que el Frontend (JS) lo formatee
    y lo mande a la impresora térmica (ESC/POS).
    """
    _verify_session_access(db, session_id, current_user)
    audit_data = get_session_audit_data(db, session_id)
    if not audit_data:
        raise HTTPException(404, "Sesión no encontrada")

    return audit_data


@router.get("/branch-summary")
def get_branch_cash_summary(
    branch_id: int = None,
    date: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Corte global de sucursal: consolida todos los cortes individuales de cajeros
    para una sucursal y fecha dada. Solo ADMINISTRADOR/DUEÑO/GERENTE.
    """
    from app.models.organization import Branch
    from datetime import date as date_type

    if current_user.role not in ("ADMINISTRADOR", "DUEÑO", "GERENTE"):
        raise HTTPException(403, "Solo administradores, dueños o gerentes pueden ver el corte global.")

    target_branch = branch_id or current_user.branch_id
    if not target_branch:
        raise HTTPException(400, "No se especificó sucursal.")

    branch = db.query(Branch).filter(Branch.id == target_branch, Branch.organization_id == org_id).first()
    if not branch:
        raise HTTPException(404, "Sucursal no encontrada.")

    # Parse date or use today (Mexico City timezone)
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, "Formato de fecha inválido. Use YYYY-MM-DD.")
    else:
        target_date = datetime.now(MX_TZ).date()

    # Build UTC range for the target date in MX timezone
    from datetime import time as time_type
    day_start_mx = datetime.combine(target_date, time_type.min, tzinfo=MX_TZ)
    day_end_mx = datetime.combine(target_date, time_type.max, tzinfo=MX_TZ)
    day_start_utc = day_start_mx.astimezone(timezone.utc)
    day_end_utc = day_end_mx.astimezone(timezone.utc)

    # All sessions for this branch on this date
    sessions = db.query(CashSession).filter(
        CashSession.branch_id == target_branch,
        CashSession.opened_at >= day_start_utc,
        CashSession.opened_at <= day_end_utc,
    ).order_by(CashSession.opened_at.desc()).all()

    if not sessions:
        return {
            "branch_id": target_branch,
            "branch_name": branch.name,
            "date": str(target_date),
            "sessions_count": 0,
            "cashiers": [],
            "totals": {
                "sales": 0, "tickets": 0, "cash": 0, "card": 0, "transfer": 0,
                "inflows": 0, "outflows": 0, "cash_refunds": 0,
                "opening_total": 0, "closing_total": 0, "difference_total": 0,
            }
        }

    # Consolidate each session
    cashiers = []
    totals = {
        "sales": Decimal(0), "tickets": 0, "cash": Decimal(0),
        "card": Decimal(0), "transfer": Decimal(0),
        "inflows": Decimal(0), "outflows": Decimal(0),
        "cash_refunds": Decimal(0),
        "opening_total": Decimal(0), "closing_total": Decimal(0),
        "difference_total": Decimal(0),
    }

    # Canonical reconciliation — single source of truth para todos los cálculos.
    # Antes este loop replicaba la fórmula con sutiles divergencias:
    #   - sales_total/ticket_count filtraban PAID-only mientras payment_stats
    #     usaba CASH_INCLUDED_STATUSES → ventas con devolución desaparecían
    #     del agregado pero seguían sumando en pagos.
    #   - difference se leía de s.difference persistido (stale del cálculo
    #     viejo en sesiones cerradas antes del fix de devoluciones).
    # Ahora todo deriva de compute_expected_cash + session_sales_filter.
    #
    # sales_total/ticket_count (SALES_REPORT_STATUSES) y payment_stats
    # (CASH_INCLUDED_STATUSES) hoy son la misma tupla — PENDING quedó fuera
    # de ambas (crédito no soportado hoy, ver el comentario junto a
    # `CASH_INCLUDED_STATUSES` en app/services/cash_reconciliation.py). Se
    # mantienen como dos tuplas separadas a propósito, no fusionadas: son
    # dos preguntas distintas ("dinero en el cajón" vs. "venta ya
    # reconocida como ingreso") que solo coinciden hoy porque PENDING no
    # entra en ninguna de las dos por motivos independientes.
    from app.services.cash_reconciliation import (
        CASH_INCLUDED_STATUSES,
        SALES_REPORT_STATUSES,
        compute_expected_cash,
        session_sales_filter,
    )

    # Perf 2026-05-07: pre-cargar todos los Users de las sesiones en 1 query
    # en lugar de N (uno por sesión dentro del loop).
    _user_ids = list({s.user_id for s in sessions if s.user_id})
    _users_by_id = {
        u.id: u for u in db.query(User).filter(User.id.in_(_user_ids)).all()
    } if _user_ids else {}

    for s in sessions:
        breakdown = compute_expected_cash(db, s)
        sales_filter = session_sales_filter(s)

        sales_total = db.query(func.sum(SalesDocument.total_amount)).filter(
            sales_filter,
            SalesDocument.status.in_(SALES_REPORT_STATUSES),
        ).scalar() or Decimal(0)

        ticket_count = db.query(func.count(SalesDocument.id)).filter(
            sales_filter,
            SalesDocument.status.in_(SALES_REPORT_STATUSES),
        ).scalar() or 0

        payment_stats = db.query(
            Payment.method,
            func.sum(Payment.amount).label("total")
        ).join(SalesDocument).filter(
            sales_filter,
            SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
        ).group_by(Payment.method).all()

        methods = {p.method: Decimal(str(p.total)) for p in payment_stats}
        card_amt = methods.get(PaymentMethod.CARD, Decimal(0))
        transfer_amt = methods.get(PaymentMethod.TRANSFER, Decimal(0))

        # Cash refund consolidado para sucursales (dato faltante hasta ahora).
        from app.models.returns import SaleReturn as SaleReturnModel
        returns_count = db.query(func.count(SaleReturnModel.id)).filter(
            SaleReturnModel.cash_session_id == s.id,
            SaleReturnModel.status == "APPROVED",
        ).scalar() or 0

        # Difference live (no leer s.difference persistido) — coherente con
        # el endpoint single-session y con la UI/ticket actuales.
        live_difference = Decimal(str(s.closing_balance or 0)) - breakdown.expected

        user = _users_by_id.get(s.user_id)

        cashier_data = {
            "session_id": s.id,
            "user_id": s.user_id,
            "username": user.username if user else f"User #{s.user_id}",
            "full_name": user.full_name if user else None,
            "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
            "opened_at": s.opened_at.isoformat() if s.opened_at else None,
            "closed_at": s.closed_at.isoformat() if s.closed_at else None,
            "opening_balance": float(s.opening_balance or 0),
            "closing_balance": float(s.closing_balance or 0),
            "difference": float(live_difference),
            "expected_cash": float(breakdown.expected),
            "sales": float(sales_total),
            "tickets": ticket_count,
            "cash": float(breakdown.net_cash),
            "card": float(card_amt),
            "transfer": float(transfer_amt),
            "change_given": float(breakdown.change_given),
            "inflows": float(breakdown.manual_inflows),
            "outflows": float(breakdown.manual_outflows),
            "cash_refunds": float(breakdown.refund_cash_outflows),
            "returns_count": returns_count,
        }
        cashiers.append(cashier_data)

        totals["sales"] += sales_total
        totals["tickets"] += ticket_count
        totals["cash"] += breakdown.net_cash
        totals["card"] += card_amt
        totals["transfer"] += transfer_amt
        totals["inflows"] += breakdown.manual_inflows
        totals["outflows"] += breakdown.manual_outflows
        totals["cash_refunds"] += breakdown.refund_cash_outflows
        totals["opening_total"] += Decimal(str(s.opening_balance or 0))
        totals["closing_total"] += Decimal(str(s.closing_balance or 0))
        totals["difference_total"] += live_difference

    return {
        "branch_id": target_branch,
        "branch_name": branch.name,
        "date": str(target_date),
        "sessions_count": len(sessions),
        "cashiers": cashiers,
        "totals": {k: float(v) for k, v in totals.items()},
    }
