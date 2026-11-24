"""Cobro de suscripciones: API de plataforma y lectura de la tienda.

- `plataforma_router` va bajo `/api/platform`: lee SUPERADMIN y SUPPORT,
  escribe solo SUPERADMIN.
- `tienda_router` va bajo `/api/suscripcion`: solo ADMINISTRADOR y DUEÑO de la
  organización activa, solo lectura.

Plan: docs/superpowers/plans/2026-11-24-f3-cobro-de-suscripciones.md
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin
from app.models.organization import Organization
from app.models.users import User
from app.modules.platform.dependencies import require_platform_admin, require_superadmin
from app.modules.suscripciones import services
from app.modules.suscripciones.models import (
    ESTADOS, ESTADOS_MANUALES, PENDIENTE, CargoSuscripcion, Suscripcion,
)
from app.modules.suscripciones.schemas import (
    CancelarCargoEntrada, CargoEntrada, CargoRead, FilaSuscripcion, GenerarCargoRead,
    ListaSuscripciones, MiSuscripcion, PagoEntrada, PagoRead, PlanTienda, SuscripcionDetalle,
    SuscripcionEntrada, SuscripcionRead, TotalesSuscripciones, UsoTienda,
)
from app.services import plans

plataforma_router = APIRouter(dependencies=[Depends(require_platform_admin)])
tienda_router = APIRouter()


# ───────────── Armado de respuestas ─────────────

def _pago_read(p, *, interno: bool) -> PagoRead:
    quien = None
    if interno and p.registrado_por is not None:
        quien = p.registrado_por.full_name or p.registrado_por.username
    return PagoRead(
        id=p.id, importe=p.importe, fecha_pago=p.fecha_pago, metodo=p.metodo, referencia=p.referencia,
        notas=p.notas if interno else None, registrado_por=quien, created_at=p.created_at,
    )


def _cargo_read(c: CargoSuscripcion, *, interno: bool) -> CargoRead:
    hoy = services.hoy_mx()
    return CargoRead(
        id=c.id, periodo_desde=c.periodo_desde, periodo_hasta=c.periodo_hasta, importe=c.importe,
        pagado=services.pagado_de(c), saldo=services.saldo_de(c), vence_el=c.vence_el, estado=c.estado,
        vencido=c.estado == PENDIENTE and c.vence_el < hoy,
        pagado_at=c.pagado_at, cancelado_at=c.cancelado_at,
        motivo_cancelacion=c.motivo_cancelacion if interno else None,
        pagos=[_pago_read(p, interno=interno) for p in c.pagos],
    )


def _suscripcion_read(sus: Suscripcion, cargos: List[CargoSuscripcion], *, interno: bool) -> SuscripcionRead:
    plan = plans.obtener_plan(sus.plan)
    return SuscripcionRead(
        id=sus.id, organization_id=sus.organization_id, plan=sus.plan, plan_nombre=plan.nombre,
        precio_mxn=sus.precio_mxn, precio_lista_mxn=Decimal(plan.precio_mxn), periodicidad=sus.periodicidad,
        dia_corte=sus.dia_corte, fecha_inicio=sus.fecha_inicio, proxima_renovacion=sus.proxima_renovacion,
        estado=services.estado_de(sus, cargos), estado_manual=sus.estado in ESTADOS_MANUALES,
        notas=sus.notas if interno else None,
        rfc=sus.rfc, razon_social=sus.razon_social, correo_facturacion=sus.correo_facturacion,
    )


def _detalle(db: Session, org: Organization) -> SuscripcionDetalle:
    sus = services.obtener(db, org.id)
    cargos = services.cargos_de(db, org.id)
    return SuscripcionDetalle(
        organization_id=org.id, organizacion=org.name, plan_organizacion=org.plan,
        suscripcion=_suscripcion_read(sus, cargos, interno=True) if sus else None,
        cargos=[_cargo_read(c, interno=True) for c in cargos],
    )


def _org_o_404(db: Session, org_id: int) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    return org


def _cargo_o_404(db: Session, cargo_id: int) -> CargoSuscripcion:
    cargo = db.query(CargoSuscripcion).filter(CargoSuscripcion.id == cargo_id).first()
    if cargo is None:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    return cargo


def _http(e: services.ErrorSuscripcion) -> HTTPException:
    # Los servicios validan ANTES de escribir: al llegar aquí no hay nada a
    # medias y la sesión se cierra sin commit.
    return HTTPException(status_code=e.status, detail=str(e))


# ───────────── Plataforma ─────────────

@plataforma_router.get("/suscripciones", response_model=ListaSuscripciones)
def listar_suscripciones(
    estado: Optional[str] = Query(None, description="al_corriente | por_vencer | vencida | suspendida | cortesia"),
    q: Optional[str] = Query(None, description="Texto en el nombre de la organización"),
    db: Session = Depends(get_db),
):
    """Cartera completa. Los totales son de TODA la cartera; los filtros solo recortan la lista."""
    if estado is not None and estado not in ESTADOS:
        raise HTTPException(status_code=400, detail=f"Estado desconocido {estado!r}. Válidos: {', '.join(ESTADOS)}")
    c = services.cartera(db)
    texto = (q or "").strip().lower()
    items = []
    for f in c.filas:
        if estado and f.estado != estado:
            continue
        if texto and texto not in (f.organizacion.name or "").lower():
            continue
        items.append(FilaSuscripcion(
            organization_id=f.organizacion.id, organizacion=f.organizacion.name, plan=f.suscripcion.plan,
            plan_nombre=plans.obtener_plan(f.suscripcion.plan).nombre, precio_mxn=f.suscripcion.precio_mxn,
            periodicidad=f.suscripcion.periodicidad, proxima_renovacion=f.suscripcion.proxima_renovacion,
            estado=f.estado, saldo_vencido=f.saldo_vencido, saldo_por_vencer=f.saldo_por_vencer,
        ))
    return ListaSuscripciones(
        totales=TotalesSuscripciones(
            cartera_vencida=c.cartera_vencida, por_vencer=c.por_vencer,
            ingreso_mensual_recurrente=c.ingreso_mensual_recurrente,
            por_estado=c.por_estado, sin_suscripcion=c.sin_suscripcion,
        ),
        items=items,
    )


@plataforma_router.get("/organizations/{org_id}/suscripcion", response_model=SuscripcionDetalle)
def detalle_suscripcion(org_id: int, db: Session = Depends(get_db)):
    """Suscripción (o `null` si aún no se da de alta), con cargos y pagos."""
    return _detalle(db, _org_o_404(db, org_id))


@plataforma_router.put("/organizations/{org_id}/suscripcion", response_model=SuscripcionDetalle)
def guardar_suscripcion(
    org_id: int, datos: SuscripcionEntrada,
    db: Session = Depends(get_db), actor: User = Depends(require_superadmin),
):
    """Alta o edición. Cambiar `plan` también cambia `organization.plan`."""
    org = _org_o_404(db, org_id)
    try:
        services.guardar_suscripcion(db, org, datos.model_dump(exclude_unset=True), actor.id)
    except services.ErrorSuscripcion as e:
        raise _http(e)
    db.commit()
    return _detalle(db, org)


@plataforma_router.post("/organizations/{org_id}/suscripcion/cargos", response_model=GenerarCargoRead)
def generar_cargo(
    org_id: int, response: Response, datos: Optional[CargoEntrada] = None,
    db: Session = Depends(get_db), actor: User = Depends(require_superadmin),
):
    """Cargo del periodo. 201 si se creó; 200 si el del periodo ya existía (idempotente)."""
    org = _org_o_404(db, org_id)
    sus = services.obtener(db, org.id)
    if sus is None:
        raise HTTPException(status_code=409, detail="La organización no tiene suscripción. Dala de alta primero.")
    datos = datos or CargoEntrada()
    try:
        cargo, creado = services.generar_cargo(
            db, sus, actor.id, periodo_desde=datos.periodo_desde, importe=datos.importe, vence_el=datos.vence_el,
        )
    except services.ErrorSuscripcion as e:
        raise _http(e)
    db.commit()
    response.status_code = 201 if creado else 200
    return GenerarCargoRead(creado=creado, cargo=_cargo_read(cargo, interno=True))


@plataforma_router.post("/suscripciones/cargos/{cargo_id}/pagos", response_model=SuscripcionDetalle, status_code=201)
def registrar_pago(
    cargo_id: int, datos: PagoEntrada,
    db: Session = Depends(get_db), actor: User = Depends(require_superadmin),
):
    """Pago parcial o total. Al cubrir el cargo lo marca pagado y avanza la renovación."""
    cargo = _cargo_o_404(db, cargo_id)
    try:
        services.registrar_pago(
            db, cargo, actor.id, importe=datos.importe, metodo=datos.metodo,
            fecha_pago=datos.fecha_pago, referencia=datos.referencia, notas=datos.notas,
        )
    except services.ErrorSuscripcion as e:
        raise _http(e)
    db.commit()
    return _detalle(db, _org_o_404(db, cargo.organization_id))


@plataforma_router.post("/suscripciones/cargos/{cargo_id}/cancelar", response_model=SuscripcionDetalle)
def cancelar_cargo(
    cargo_id: int, datos: Optional[CancelarCargoEntrada] = None,
    db: Session = Depends(get_db), actor: User = Depends(require_superadmin),
):
    """Cancela un cargo pendiente sin pagos."""
    cargo = _cargo_o_404(db, cargo_id)
    try:
        services.cancelar_cargo(db, cargo, actor.id, (datos.motivo if datos else None))
    except services.ErrorSuscripcion as e:
        raise _http(e)
    db.commit()
    return _detalle(db, _org_o_404(db, cargo.organization_id))


# ───────────── Tienda (solo lectura) ─────────────

@tienda_router.get("/mia", response_model=MiSuscripcion)
def mi_suscripcion(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_active_organization),
    current_user: User = Depends(get_current_user),
):
    """Plan, uso contra topes, estado e historial de cargos y pagos de MI organización."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Solo administradores y dueños pueden ver el plan y los pagos.")
    org = _org_o_404(db, org_id)
    plan = plans.obtener_plan(org.plan)
    uso = plans.uso(db, org.id)
    sus = services.obtener(db, org.id)
    cargos = services.cargos_de(db, org.id)
    return MiSuscripcion(
        plan=PlanTienda(
            clave=plan.clave, nombre=plan.nombre, precio_lista_mxn=Decimal(plan.precio_mxn),
            max_usuarios=plan.max_usuarios, max_sucursales_venta=plan.max_sucursales_venta,
        ),
        uso=UsoTienda(usuarios_activos=uso.usuarios_activos, sucursales_venta=uso.sucursales_venta),
        suscripcion=_suscripcion_read(sus, cargos, interno=False) if sus else None,
        cargos=[_cargo_read(c, interno=False) for c in cargos],
    )
