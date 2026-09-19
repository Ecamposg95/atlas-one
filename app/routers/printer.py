from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Tuple
from app.core.database import get_db
from app.models import SalesDocument, User, SalesLineItem, ProductVariant, SaleReturn, SaleReturnItem
from app.models.sales import DocumentStatus
from app.models.print_job import PrintJob, PrintJobStatus
from app.models.cash_audit import CashAuditEvent
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.pos_printer import PosPrinter
from app.routers.sales import _assert_sale_branch_access
import base64
import io
import logging
import traceback
import zipfile
from pathlib import Path

router = APIRouter()

logger = logging.getLogger(__name__)


class ReprintRequest(BaseModel):
    """Cuerpo opcional de la reimpresion. Un usuario con rol gerencial no manda
    nada; un cajero manda el `pin` (la contrasena) de un supervisor para que lo
    autorice en el momento."""
    pin: Optional[str] = None


def _cambio_del_ticket(sale: SalesDocument, total_paid: float) -> float:
    """Cambio entregado al cliente, para el renglon CAM del ticket.

    Se prefiere SIEMPRE `sales_documents.change_given`: es el numero que
    `create_sale` le dijo al cajero y el que ya cuadro contra el cajon. La
    resta `sum(pagos) - total_amount` NO sirve cuando hay comision de tarjeta,
    porque `total_amount` excluye la comision mientras que el `Payment` de CARD
    la incluye: una venta 100% tarjeta imprimia la comision entera como si
    fuera cambio entregado.

    El fallback (ventas viejas sin `change_given`) hace la misma resta pero
    descontando la comision congelada, que es la formula correcta.
    """
    guardado = getattr(sale, "change_given", None)
    if guardado is not None:
        return max(0.0, float(guardado))
    comision = float(getattr(sale, "card_surcharge_amount", 0) or 0)
    return max(0.0, total_paid - float(sale.total_amount) - comision)


def _assert_reimprimible(sale: SalesDocument) -> None:
    """C-18: una venta CANCELLED ya no representa un cobro. Servir su ticket
    limpio es exactamente el insumo del fraude por reciclaje de comprobantes:
    cancelar la venta borraba el cargo, pero no el papel."""
    estado = sale.status.value if hasattr(sale.status, "value") else str(sale.status)
    if estado == DocumentStatus.CANCELLED.value:
        raise HTTPException(
            status_code=409,
            detail="Esta venta esta cancelada: su ticket ya no se puede reimprimir.",
        )


def _auditar_impresion(
    db: Session, *, evento: str, sale: SalesDocument, current_user: User,
    org_id: int, via: str, supervisor: Optional[User], confirmar: bool = False,
) -> None:
    """Deja el rastro de quien emitio (o intento emitir) un ticket.

    El PrintJob guarda los bytes y la impresora, no quien lo pidio ni quien lo
    autorizo, asi que sin esto el control del PIN no se puede investigar
    despues. FAILSAFE como el resto de `audit_cash_event`: un fallo de
    auditoria nunca tumba la impresion.

    `confirmar=True` hace commit: el intento fallido termina en un 403 y sin
    commit propio la fila se iria con el rollback de la transaccion.
    """
    from app.services.cash_audit import audit_cash_event

    try:
        audit_cash_event(
            db,
            event_type=evento,
            organization_id=org_id,
            branch_id=sale.branch_id,
            user_id=current_user.id,
            amount=sale.total_amount,
            related_table="sales_documents",
            related_id=str(sale.id),
            payload={
                "via": via,
                "authorized_by_user_id": supervisor.id if supervisor else None,
                "authorized_by_username": supervisor.username if supervisor else None,
                "folio": f"{sale.series}-{sale.folio}" if sale.folio else None,
            },
        )
        if confirmar:
            db.commit()
    except Exception:
        logger.exception("REPRINT_AUDIT_FAILED sale=%s", getattr(sale, "id", None))


def _autorizar_impresion(
    db: Session, current_user: User, org_id: int, req: Optional[ReprintRequest],
    sale: SalesDocument,
) -> Optional[User]:
    """Gate compartido por los tres endpoints que emiten un ticket de venta
    (hallazgo §6 de la auditoria Rmazh). Devuelve el supervisor que autorizo, o
    None si no hizo falta PIN. Nunca deja pasar a alguien sin autoridad ni PIN.

    Va en los TRES y no solo en las reimpresiones: `print-ticket` acepta un
    `order_id` cualquiera, asi que gatear unicamente `reprint-ticket` dejaria el
    mismo ticket a un POST de distancia."""
    from app.services.reprint_auth import (
        bloqueo_restante,
        es_rol_gerencial,
        es_venta_propia_reciente,
        limpiar_intentos,
        registrar_intento_fallido,
        verificar_pin_supervisor,
    )

    # La venta propia reciente se evalua PRIMERO, antes que el rol: un gerente o
    # un dueno tambien cobran en caja, y con el orden invertido cada venta suya
    # dejaba una fila TICKET_REPRINTED. Eso no es auditoria, es una copia del
    # libro de ventas. La impresion normal del POS tras cobrar no se audita; el
    # PrintJob ya deja el rastro de ese caso.
    if es_venta_propia_reciente(sale, current_user):
        return None

    if es_rol_gerencial(current_user):
        _auditar_impresion(
            db, evento=CashAuditEvent.TICKET_REPRINTED, sale=sale,
            current_user=current_user, org_id=org_id, via="rol_gerencial",
            supervisor=None,
        )
        logger.info(
            "TICKET_REPRINTED: org_id=%s user_id=%s sale_id=%s via=rol_gerencial",
            org_id, current_user.id, sale.id,
        )
        return None

    restante = bloqueo_restante(org_id, current_user.id)
    if restante is not None:
        raise HTTPException(
            status_code=423,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {restante} segundos.",
        )

    pin = req.pin if req else None
    if not pin:
        # 428 (Precondition Required) y no 401: el cajero SI esta autenticado,
        # lo que falta es una autorizacion puntual. Un 401 dispararia el cierre
        # de sesion global del interceptor de axios, que es justo el mecanismo
        # de seguridad que no queremos debilitar con excepciones por ruta.
        raise HTTPException(status_code=428, detail="Se requiere el PIN de un supervisor")

    supervisor = verificar_pin_supervisor(db, org_id, pin, branch_id=sale.branch_id)
    if not supervisor:
        registrar_intento_fallido(org_id, current_user.id)
        _auditar_impresion(
            db, evento=CashAuditEvent.REPRINT_PIN_FAILED, sale=sale,
            current_user=current_user, org_id=org_id, via="pin",
            supervisor=None, confirmar=True,
        )
        logger.warning(
            "REPRINT_PIN_FAILED: org_id=%s user_id=%s username=%s sale_id=%s",
            org_id, current_user.id, current_user.username, sale.id,
        )
        # `detail` estructurado: el 403 de "Sin acceso a esta venta" y el del
        # PIN son indistinguibles por codigo, y el front necesita saber cual es
        # para decidir si deja reintentar en el modal o cierra con aviso.
        raise HTTPException(
            status_code=403,
            detail={"code": "PIN_INCORRECTO", "message": "PIN incorrecto"},
        )

    limpiar_intentos(org_id, current_user.id)
    _auditar_impresion(
        db, evento=CashAuditEvent.TICKET_REPRINTED, sale=sale,
        current_user=current_user, org_id=org_id, via="pin", supervisor=supervisor,
    )
    logger.info(
        "TICKET_REPRINTED: org_id=%s user_id=%s sale_id=%s via=pin autorizo_user_id=%s",
        org_id, current_user.id, sale.id, supervisor.id,
    )
    return supervisor


def _resolve_printer(
    current_user: User,
    organization,
    *,
    override_printer_name: Optional[str] = None,
    override_width: Optional[int] = None,
) -> Tuple[PosPrinter, Optional[str]]:
    """Resolve printer config para construir bytes ESC/POS.

    Track 4 (POS bug-fix): el printer.printer_name solo se usa como **hint**
    para `paper_width_mm`. La impresión real ocurre 100% en el agente local
    de cada PC (cada cajero puede tener N PCs con N impresoras distintas);
    el server-side print mode quedó deprecado.

    Los overrides permiten que "Probar impresora" refleje la selección que el
    cajero tiene en pantalla aunque todavía no la haya guardado en la sucursal.

    Returns (PosPrinter instance, raw target name preserved for response only).
    """
    target = None
    if override_printer_name:
        target = override_printer_name
    elif current_user.branch and current_user.branch.printer_name:
        target = current_user.branch.printer_name
    elif organization and organization.printer_name:
        target = organization.printer_name
    p_name = target or "POS-80"
    if override_width in (58, 80):
        width = override_width
    else:
        branch_width = getattr(current_user.branch, 'paper_width_mm', None) if current_user.branch else None
        width = branch_width if branch_width in (58, 80) else (58 if "58" in p_name else 80)
    return PosPrinter(printer_name=p_name, paper_width_mm=width), target


def _device_info(request: Request) -> dict:
    """Extrae device_id / fingerprint / client_ip de headers (Track 4)."""
    return {
        "device_id": request.headers.get("X-Device-ID"),
        "device_fingerprint": request.headers.get("X-Device-Fingerprint"),
        "client_ip": request.client.host if request.client else None,
    }


def _record_print_job(db: Session, *, raw_bytes: bytes, printer_name: Optional[str],
                      org_id: int, request: Request) -> PrintJob:
    """Crea un PrintJob con device tracking. Track 4: estado siempre PRINTED
    porque el server no imprime — solo registra que entregó los bytes al
    agente local. Si el agente local falla, el frontend reporta separado."""
    info = _device_info(request)
    job = PrintJob(
        printer_name=printer_name,
        content=base64.b64encode(raw_bytes).decode('utf-8'),
        status=PrintJobStatus.PRINTED,
        organization_id=org_id,
        device_id=info["device_id"],
        device_fingerprint=info["device_fingerprint"],
        client_ip=info["client_ip"],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


class TestPrintRequest(BaseModel):
    """Override opcional desde la UI: el cajero prueba con la impresora/ancho
    que tiene seleccionado en pantalla, sin necesidad de guardar primero."""
    printer_name: Optional[str] = None
    paper_width_mm: Optional[int] = None


@router.post("/test-print")
def test_print_endpoint(
    request: Request,
    payload: Optional[TestPrintRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Track 4: siempre retorna base64. El agente local de cada PC imprime."""
    from app.models.organization import Organization
    organization = db.query(Organization).filter(Organization.id == org_id).first()
    printer, target_printer_name = _resolve_printer(
        current_user,
        organization,
        override_printer_name=payload.printer_name if payload else None,
        override_width=payload.paper_width_mm if payload else None,
    )
    try:
        raw_bytes = printer.build_test_ticket_bytes(organization, branch=current_user.branch)
    except Exception as e:
        raise HTTPException(500, f"Error building test ticket: {str(e)}")
    job = _record_print_job(db, raw_bytes=raw_bytes, printer_name=printer.printer_name,
                            org_id=org_id, request=request)
    return {
        "status": "ready_to_print",
        "job_id": job.id,
        "content_base64": base64.b64encode(raw_bytes).decode('utf-8'),
        "printer_target": target_printer_name,
    }


class PrintRequest(BaseModel):
    order_id: str
    # `mode` ignored — Track 4 deprecó server-side print. Mantenido en el
    # schema para backward-compat con clientes viejos.
    mode: str = "return_base64"
    # Si la venta no es propia-y-reciente, este endpoint cae al mismo gate de
    # PIN que la reimpresión. Opcional para no romper al llamador legítimo
    # (POS.tsx tras cobrar), que nunca lo necesita.
    pin: Optional[str] = None


@router.get("/download-agent")
def download_print_agent(
    platform: str = "windows",  # 'windows' | 'linux' | 'mac'
    current_user: User = Depends(get_current_user)
):
    """Descarga el Agente Local de Impresión como ZIP, filtrado por plataforma."""
    agent_dir = Path(__file__).parent.parent.parent / "tools" / "print_agent"
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail="Agente no encontrado en el servidor.")

    plat = platform.lower()
    if plat not in ("windows", "linux", "mac"):
        raise HTTPException(status_code=400, detail="platform debe ser 'windows', 'linux' o 'mac'")

    ALWAYS_EXCLUDE_DIRS = {"certs", "__pycache__", "venv", "venv_v2"}
    ALWAYS_EXCLUDE_SUFFIXES = {".pyc"}
    ALWAYS_EXCLUDE_FILES: set[str] = set()

    # Launcher por plataforma — los demás se excluyen para no confundir al usuario.
    # Archivos del autoarranque, por plataforma. Cada ZIP lleva SOLO los suyos:
    # una caja no debe recibir un instalador que no puede correr.
    AUTOSTART_LINUX = {
        "instalar-servicio-linux.sh", "atlas-print-agent.service",
        "atlas-print-agent.desktop", "INSTALL_LINUX.txt",
    }
    AUTOSTART_MAC = {
        "instalar-servicio-mac.sh", "com.atlasone.print-agent.plist",
        "INSTALL_MAC.txt",
    }

    if plat == "windows":
        platform_exclude = {
            "impresora_linux.sh", "impresora_mac.sh",
            "requirements_linux.txt", "requirements_mac.txt",
            *AUTOSTART_LINUX, *AUTOSTART_MAC,
        }
    elif plat == "mac":
        platform_exclude = {
            "impresora_win.bat", "impresora_linux.sh",
            "requirements_linux.txt",
            *AUTOSTART_LINUX,
        }
    else:  # linux
        platform_exclude = {
            "impresora_win.bat", "impresora_mac.sh",
            "requirements_mac.txt",
            *AUTOSTART_MAC,
        }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in agent_dir.rglob("*"):
            if not file.is_file():
                continue
            if any(part in ALWAYS_EXCLUDE_DIRS for part in file.parts):
                continue
            if file.suffix in ALWAYS_EXCLUDE_SUFFIXES:
                continue
            if file.name in ALWAYS_EXCLUDE_FILES or file.name in platform_exclude:
                continue
            zf.write(file, file.relative_to(agent_dir.parent))
    buf.seek(0)

    filename = f"atlas_print_agent_{plat}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/printers")
def get_printers(
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """List available printers (Virtual/Cloud). Requires authentication."""
    return PosPrinter.get_available_printers()


@router.post("/print-ticket")
def print_ticket_endpoint(
    req: PrintRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Track 4: genera bytes ESC/POS y los retorna en base64. El agente
    local de la PC del cajero los envía a su impresora física."""
    sale = db.query(SalesDocument).filter(SalesDocument.id == req.order_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if sale.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sin acceso a esta venta")
    _assert_sale_branch_access(sale, current_user)
    _assert_reimprimible(sale)
    _autorizar_impresion(db, current_user, org_id, ReprintRequest(pin=req.pin), sale)

    from app.models.organization import Organization
    organization = db.query(Organization).filter(Organization.id == org_id).first()
    printer, target_printer_name = _resolve_printer(current_user, organization)

    try:
        payments_detail = [{"method": p.method, "amount": float(p.amount), "reference": p.reference or ""} for p in sale.payments]
        has_cash = any((p.method or "").upper() in {"CASH", "EFECTIVO"} for p in sale.payments)
        branch_opens_drawer = bool(getattr(sale.branch, "open_drawer_on_print", False))
        total_paid = sum(float(p.amount) for p in sale.payments)
        raw_bytes = printer.build_ticket_bytes(
            sale=sale,
            cashier=current_user.username,
            organization=organization,
            branch=sale.branch,
            paid=total_paid,
            change=_cambio_del_ticket(sale, total_paid),
            method=sale.payments[0].method if sale.payments else "PENDING",
            is_reprint=False,
            returns=[r for r in sale.returns if r.status == 'APPROVED'],
            payments_detail=payments_detail,
            open_drawer=branch_opens_drawer and has_cash,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    job = _record_print_job(db, raw_bytes=raw_bytes, printer_name=printer.printer_name,
                            org_id=org_id, request=request)
    return {
        "status": "ready_to_print",
        "job_id": job.id,
        "content_base64": base64.b64encode(raw_bytes).decode('utf-8'),
        "printer_target": target_printer_name,
    }


@router.post("/reprint-ticket/{order_id}")
def reprint_ticket_endpoint(
    order_id: str,
    request: Request,
    req: Optional[ReprintRequest] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Reimpresión de un ticket. Exige rol gerencial o PIN de supervisor."""
    from sqlalchemy.orm import joinedload, selectinload
    sale = db.query(SalesDocument).options(
        joinedload(SalesDocument.lines).joinedload(SalesLineItem.variant),
        joinedload(SalesDocument.payments),
        selectinload(SalesDocument.returns).selectinload(SaleReturn.items).joinedload(SaleReturnItem.variant).joinedload(ProductVariant.product),
        joinedload(SalesDocument.branch)
    ).filter(SalesDocument.id == order_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if sale.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sin acceso a esta venta")
    _assert_sale_branch_access(sale, current_user)
    _assert_reimprimible(sale)
    autorizado_por = _autorizar_impresion(db, current_user, org_id, req, sale)

    if hasattr(sale, 'reprint_count'):
        sale.reprint_count += 1
        db.commit()

    from app.models.organization import Organization
    organization = db.query(Organization).filter(Organization.id == org_id).first()
    printer, target_printer_name = _resolve_printer(current_user, organization)

    total_paid = sum(float(p.amount) for p in sale.payments)
    change = _cambio_del_ticket(sale, total_paid)
    method = sale.payments[0].method if sale.payments else "MIXTO"

    try:
        reprint_payments_detail = [{"method": p.method, "amount": float(p.amount), "reference": p.reference or ""} for p in sale.payments]
        raw_bytes = printer.build_ticket_bytes(
            sale=sale, paid=total_paid, change=change, method=method,
            cashier=current_user.username, is_reprint=True,
            organization=organization, branch=sale.branch,
            returns=[r for r in sale.returns if r.status == 'APPROVED'],
            payments_detail=reprint_payments_detail,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error de reimpresión: {str(e)}")

    job = _record_print_job(db, raw_bytes=raw_bytes, printer_name=printer.printer_name,
                            org_id=org_id, request=request)
    return {
        "status": "ready_to_print",
        "job_id": job.id,
        "content_base64": base64.b64encode(raw_bytes).decode('utf-8'),
        "printer_target": target_printer_name,
        "reprint_count": getattr(sale, 'reprint_count', 'N/A'),
        "authorized_by": autorizado_por.username if autorizado_por else None,
    }


@router.post("/reprint-refunded/{order_id}")
def reprint_refunded_endpoint(
    order_id: str,
    request: Request,
    req: Optional[ReprintRequest] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Ticket actualizado tras devoluciones. Mismo gate que reprint-ticket."""
    from sqlalchemy.orm import joinedload, selectinload
    sale = db.query(SalesDocument).options(
        joinedload(SalesDocument.lines).joinedload(SalesLineItem.variant),
        joinedload(SalesDocument.branch),
        selectinload(SalesDocument.returns).selectinload(SaleReturn.items).joinedload(SaleReturnItem.variant).joinedload(ProductVariant.product)
    ).filter(SalesDocument.id == order_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if sale.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sin acceso a esta venta")
    _assert_sale_branch_access(sale, current_user)
    _assert_reimprimible(sale)
    _autorizar_impresion(db, current_user, org_id, req, sale)

    from app.models.organization import Organization
    organization = db.query(Organization).filter(Organization.id == org_id).first()
    printer, target_printer_name = _resolve_printer(current_user, organization)

    try:
        raw_bytes = printer.build_reissued_ticket_bytes(
            sale=sale,
            cashier=current_user.username,
            organization=organization,
            branch=sale.branch,
            returns=[r for r in sale.returns if r.status == 'APPROVED']
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

    job = _record_print_job(db, raw_bytes=raw_bytes, printer_name=printer.printer_name,
                            org_id=org_id, request=request)
    return {
        "status": "ready_to_print",
        "job_id": job.id,
        "content_base64": base64.b64encode(raw_bytes).decode('utf-8'),
        "printer_target": target_printer_name,
    }


class PrintCashCutRequest(BaseModel):
    session_id: int
    # Track 4: `mode` ignorado (deprecated). Siempre return_base64.
    mode: str = "return_base64"


@router.post("/print-cash-cut")
def print_cash_cut_endpoint(
    req: PrintCashCutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Track 4: corte de caja siempre en base64."""
    from app.routers.cash import get_session_audit_data, _verify_session_access
    _verify_session_access(db, req.session_id, current_user)
    audit_data = get_session_audit_data(db, req.session_id)
    if not audit_data:
        raise HTTPException(404, "Sesión no encontrada")

    from app.models.organization import Organization
    organization = db.query(Organization).filter(Organization.id == org_id).first()
    printer, target_printer_name = _resolve_printer(current_user, organization)

    try:
        raw_bytes = printer.build_cash_cut_bytes(audit_data)
    except Exception as e:
        raise HTTPException(500, f"Error impresión: {str(e)}")

    job = _record_print_job(db, raw_bytes=raw_bytes, printer_name=printer.printer_name,
                            org_id=org_id, request=request)
    return {
        "status": "ready_to_print",
        "job_id": job.id,
        "content_base64": base64.b64encode(raw_bytes).decode('utf-8'),
        "printer_target": target_printer_name,
        "session_id": req.session_id,
    }
