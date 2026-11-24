"""Reglas del cobro de suscripciones (megaplan F3, primera versión manual).

Todo lo que escribe deja fila en `platform_audit_log` y NO hace commit: el
router confirma la transacción. Nada de aquí bloquea accesos: `suspendida`
es informativa.

"Hoy" es el día de México (`hoy_mx`) y se puede inyectar en cada función.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.platform import PlatformAuditLog
from app.modules.suscripciones.models import (
    AL_CORRIENTE, ANUAL, CANCELADO, CORTESIA, ESTADOS, ESTADOS_MANUALES, MENSUAL, METODOS,
    ORIGEN_MANUAL, PAGADO, PENDIENTE, PERIODICIDADES, POR_VENCER, SUSPENDIDA, VENCIDA,
    CargoSuscripcion, PagoSuscripcion, Suscripcion,
)
from app.services import plans
from app.services.metricas_ventas import hoy_mx

# Con cuántos días de anticipación una suscripción pasa a "por vencer".
DIAS_AVISO = 7
CENTAVO = Decimal("0.01")
CERO = Decimal("0.00")


class ErrorSuscripcion(ValueError):
    """Regla de negocio rota; el router la traduce a HTTP con `status`."""

    def __init__(self, mensaje: str, status: int = 422):
        super().__init__(mensaje)
        self.status = status


def _hoy(hoy: Optional[date]) -> date:
    return hoy or hoy_mx()


def _dinero(valor) -> Decimal:
    return Decimal(str(valor if valor is not None else 0)).quantize(CENTAVO)


def _bitacora(db: Session, actor_id: Optional[int], accion: str, org_id: int, detalle: dict) -> None:
    db.add(PlatformAuditLog(
        actor_user_id=actor_id,
        action=accion,
        entity_type="SUSCRIPCION",
        entity_id=str(org_id),
        payload=json.dumps(detalle, default=str, ensure_ascii=False),
    ))


# ───────────────────────── Funciones puras ─────────────────────────

@dataclass(frozen=True)
class CargoResumen:
    """Lo mínimo de un cargo que necesita el cálculo de estado."""
    estado: str
    vence_el: date


def calcular_estado(
    *,
    estado_guardado: Optional[str],
    precio: Decimal,
    proxima_renovacion: date,
    cargos: Iterable[CargoResumen],
    hoy: date,
    dias_aviso: int = DIAS_AVISO,
) -> str:
    """Estado de la suscripción a partir de fechas y cargos. Pura.

    1. Lo manual (`suspendida`, `cortesia`) gana: solo se quita a mano.
    2. Precio pactado 0: no hay nada que cobrar → `al_corriente`.
    3. Con cargos pendientes mandan sus vencimientos: alguno ya pasó →
       `vencida`; el más próximo cae dentro del aviso → `por_vencer`.
    4. Sin cargos pendientes manda la próxima renovación: ya pasó y nadie ha
       pagado ese periodo → `vencida`; dentro del aviso → `por_vencer`.
    """
    if estado_guardado in ESTADOS_MANUALES:
        return estado_guardado
    if precio <= 0:
        return AL_CORRIENTE
    limite = hoy + timedelta(days=dias_aviso)
    vencimientos = [c.vence_el for c in cargos if c.estado == PENDIENTE]
    if vencimientos:
        primero = min(vencimientos)
        if primero < hoy:
            return VENCIDA
        return POR_VENCER if primero <= limite else AL_CORRIENTE
    if proxima_renovacion < hoy:
        return VENCIDA
    if proxima_renovacion <= limite:
        return POR_VENCER
    return AL_CORRIENTE


def siguiente_corte(desde: date, periodicidad: str, dia_corte: int) -> date:
    """Primer día del periodo siguiente: un mes (o doce) después, en el día de corte."""
    meses = 12 if periodicidad == ANUAL else 1
    indice = desde.year * 12 + (desde.month - 1) + meses
    return date(indice // 12, indice % 12 + 1, max(1, min(int(dia_corte), 28)))


def precio_mensual(precio: Decimal, periodicidad: str) -> Decimal:
    """Precio pactado llevado a mes (el anual se divide entre doce)."""
    if periodicidad == ANUAL:
        return (precio / Decimal(12)).quantize(CENTAVO)
    return _dinero(precio)


def pagado_de(cargo: CargoSuscripcion) -> Decimal:
    return sum((_dinero(p.importe) for p in cargo.pagos), CERO)


def saldo_de(cargo: CargoSuscripcion) -> Decimal:
    if cargo.estado != PENDIENTE:
        return CERO
    return max(_dinero(cargo.importe) - pagado_de(cargo), CERO)


# ───────────────────────── Lecturas ─────────────────────────

def obtener(db: Session, org_id: int) -> Optional[Suscripcion]:
    return db.query(Suscripcion).filter(Suscripcion.organization_id == org_id).first()


def cargos_de(db: Session, org_id: int) -> List[CargoSuscripcion]:
    return (
        db.query(CargoSuscripcion)
        .filter(CargoSuscripcion.organization_id == org_id)
        .order_by(CargoSuscripcion.periodo_desde.desc())
        .all()
    )


def estado_de(sus: Suscripcion, cargos: Iterable[CargoSuscripcion], hoy: Optional[date] = None) -> str:
    return calcular_estado(
        estado_guardado=sus.estado,
        precio=_dinero(sus.precio_mxn),
        proxima_renovacion=sus.proxima_renovacion,
        cargos=[CargoResumen(c.estado, c.vence_el) for c in cargos],
        hoy=_hoy(hoy),
    )


def _refrescar_estado(db: Session, sus: Suscripcion, hoy: Optional[date] = None) -> str:
    """Guarda la foto del estado tras una escritura."""
    db.flush()
    sus.estado = estado_de(sus, cargos_de(db, sus.organization_id), hoy)
    return sus.estado


# ───────────────────────── Suscripción ─────────────────────────

_CAMPOS_TEXTO = ("notas", "rfc", "razon_social", "correo_facturacion")


def guardar_suscripcion(
    db: Session, org: Organization, datos: dict, actor_id: Optional[int], hoy: Optional[date] = None,
) -> Tuple[Suscripcion, bool]:
    """Alta o edición. `datos` trae solo lo que se quiere cambiar.

    En el alta: plan = el de la organización, precio = el de lista del plan,
    periodicidad mensual, inicio hoy, corte el día del inicio (tope 28) y
    primera renovación en la fecha de inicio (se cobra por adelantado).

    Cambiar el plan pasa por `plans.asignar_plan`, que también mueve
    `organization.plan`; el precio pactado solo cambia si viene en `datos`.
    """
    hoy = _hoy(hoy)
    sus = obtener(db, org.id)
    creada = sus is None
    antes: Dict[str, object] = {}

    periodicidad = datos.get("periodicidad")
    if periodicidad is not None and periodicidad not in PERIODICIDADES:
        raise ErrorSuscripcion(f"Periodicidad desconocida {periodicidad!r}. Válidas: {', '.join(PERIODICIDADES)}")
    dia_corte = datos.get("dia_corte")
    if dia_corte is not None and not 1 <= int(dia_corte) <= 28:
        raise ErrorSuscripcion("El día de corte va del 1 al 28.")
    estado = datos.get("estado")
    if estado is not None and estado not in ESTADOS:
        raise ErrorSuscripcion(f"Estado desconocido {estado!r}. Válidos: {', '.join(ESTADOS)}")
    precio = datos.get("precio_mxn")
    if precio is not None and _dinero(precio) < 0:
        raise ErrorSuscripcion("El precio pactado no puede ser negativo.")

    plan_nuevo = datos.get("plan")
    plan_anterior = org.plan
    if plan_nuevo is not None and plan_nuevo != org.plan:
        try:
            plans.asignar_plan(org, plan_nuevo)
        except plans.PlanDesconocido as e:
            raise ErrorSuscripcion(str(e), status=400)

    if creada:
        clave = plan_nuevo or plans.obtener_plan(org.plan).clave
        inicio = datos.get("fecha_inicio") or hoy
        sus = Suscripcion(
            organization_id=org.id,
            plan=clave,
            precio_mxn=_dinero(precio) if precio is not None else _dinero(plans.obtener_plan(clave).precio_mxn),
            periodicidad=periodicidad or MENSUAL,
            dia_corte=int(dia_corte) if dia_corte is not None else min(inicio.day, 28),
            fecha_inicio=inicio,
            proxima_renovacion=datos.get("proxima_renovacion") or inicio,
            estado=AL_CORRIENTE,
        )
        db.add(sus)
    else:
        antes = {
            "plan": sus.plan, "precio_mxn": str(sus.precio_mxn), "periodicidad": sus.periodicidad,
            "dia_corte": sus.dia_corte, "proxima_renovacion": str(sus.proxima_renovacion), "estado": sus.estado,
        }
        if plan_nuevo is not None:
            sus.plan = plan_nuevo
        if precio is not None:
            sus.precio_mxn = _dinero(precio)
        if periodicidad is not None:
            sus.periodicidad = periodicidad
        if dia_corte is not None:
            sus.dia_corte = int(dia_corte)
        for campo in ("fecha_inicio", "proxima_renovacion"):
            if datos.get(campo) is not None:
                setattr(sus, campo, datos[campo])

    for campo in _CAMPOS_TEXTO:
        if campo in datos:
            valor = (datos[campo] or "").strip() or None
            setattr(sus, campo, valor.upper() if campo == "rfc" and valor else valor)

    if estado is not None:
        # Uno manual se queda; uno automático solo quita lo manual y se recalcula.
        sus.estado = estado if estado in ESTADOS_MANUALES else AL_CORRIENTE
    _refrescar_estado(db, sus, hoy)

    despues = {
        "plan": sus.plan, "precio_mxn": str(sus.precio_mxn), "periodicidad": sus.periodicidad,
        "dia_corte": sus.dia_corte, "proxima_renovacion": str(sus.proxima_renovacion), "estado": sus.estado,
    }
    _bitacora(db, actor_id, "SUSCRIPCION_ALTA" if creada else "SUSCRIPCION_EDICION", org.id,
              {"antes": antes, "despues": despues} if not creada else despues)
    if plan_nuevo is not None and plan_nuevo != plan_anterior:
        _bitacora(db, actor_id, "SUSCRIPCION_CAMBIO_PLAN", org.id,
                  {"antes": plan_anterior, "despues": plan_nuevo})
    return sus, creada


def reflejar_plan_de_org(db: Session, org: Organization) -> None:
    """El plan se cambió por el PUT de organizaciones: la suscripción lo sigue.
    El precio pactado NO se toca (lo decide plataforma en la suscripción)."""
    sus = obtener(db, org.id)
    if sus is not None and sus.plan != org.plan and plans.es_plan_valido(org.plan):
        sus.plan = org.plan


# ───────────────────────── Cargos ─────────────────────────

def generar_cargo(
    db: Session,
    sus: Suscripcion,
    actor_id: Optional[int],
    *,
    periodo_desde: Optional[date] = None,
    importe: Optional[Decimal] = None,
    vence_el: Optional[date] = None,
    hoy: Optional[date] = None,
) -> Tuple[CargoSuscripcion, bool]:
    """Cargo del periodo. Idempotente: un cargo por organización y periodo.

    Por omisión cobra el periodo que empieza en la próxima renovación; como esa
    fecha solo avanza al pagar, repetir la llamada devuelve el mismo cargo.
    Para cobrar por adelantado un periodo posterior se manda `periodo_desde`.

    Devuelve `(cargo, creado)`. Si el cargo del periodo ya existe se devuelve
    sin tocarlo; si estaba cancelado (y por tanto sin pagos) se reabre.
    """
    desde = periodo_desde or sus.proxima_renovacion
    monto = _dinero(importe if importe is not None else sus.precio_mxn)
    if monto <= 0:
        raise ErrorSuscripcion("El importe del cargo debe ser mayor que cero.")
    hasta = siguiente_corte(desde, sus.periodicidad, sus.dia_corte) - timedelta(days=1)
    vence = vence_el or desde

    def _existente() -> Optional[CargoSuscripcion]:
        return (
            db.query(CargoSuscripcion)
            .filter(CargoSuscripcion.organization_id == sus.organization_id,
                    CargoSuscripcion.periodo_desde == desde)
            .first()
        )

    cargo = _existente()
    if cargo is not None and cargo.estado != CANCELADO:
        return cargo, False

    detalle = {"periodo_desde": desde, "periodo_hasta": hasta, "importe": str(monto), "vence_el": vence}
    if cargo is not None:
        cargo.estado = PENDIENTE
        cargo.importe = monto
        cargo.vence_el = vence
        cargo.periodo_hasta = hasta
        cargo.cancelado_at = None
        cargo.motivo_cancelacion = None
        detalle["reabierto"] = True
    else:
        cargo = CargoSuscripcion(
            organization_id=sus.organization_id, suscripcion_id=sus.id,
            periodo_desde=desde, periodo_hasta=hasta, importe=monto, vence_el=vence, estado=PENDIENTE,
        )
        try:
            # SAVEPOINT: si otra petición ganó la carrera, la restricción única
            # la frena sin tirar la transacción y devolvemos el que ya quedó.
            with db.begin_nested():
                db.add(cargo)
                db.flush()
        except IntegrityError:
            ganador = _existente()
            if ganador is None:
                raise
            return ganador, False

    detalle["cargo_id"] = cargo.id
    _refrescar_estado(db, sus, hoy)
    _bitacora(db, actor_id, "SUSCRIPCION_CARGO", sus.organization_id, detalle)
    return cargo, True


def registrar_pago(
    db: Session,
    cargo: CargoSuscripcion,
    actor_id: Optional[int],
    *,
    importe: Decimal,
    metodo: str,
    fecha_pago: Optional[date] = None,
    referencia: Optional[str] = None,
    notas: Optional[str] = None,
    hoy: Optional[date] = None,
) -> PagoSuscripcion:
    """Pago parcial o total contra un cargo pendiente.

    Al cubrir el importe el cargo queda `pagado` y la próxima renovación avanza
    al día siguiente del fin del periodo (nunca retrocede).
    """
    hoy = _hoy(hoy)
    if metodo not in METODOS:
        raise ErrorSuscripcion(f"Método desconocido {metodo!r}. Válidos: {', '.join(METODOS)}")
    if cargo.estado != PENDIENTE:
        raise ErrorSuscripcion(f"El cargo está {cargo.estado}; no admite pagos.", status=409)
    monto = _dinero(importe)
    if monto <= 0:
        raise ErrorSuscripcion("El importe del pago debe ser mayor que cero.")
    saldo = saldo_de(cargo)
    if monto > saldo:
        raise ErrorSuscripcion(f"El pago (${monto}) es mayor al saldo del cargo (${saldo}).")
    fecha = fecha_pago or hoy
    if fecha > hoy:
        raise ErrorSuscripcion("La fecha del pago no puede ser futura.")

    pago = PagoSuscripcion(
        organization_id=cargo.organization_id, cargo_id=cargo.id, importe=monto, fecha_pago=fecha,
        metodo=metodo, referencia=(referencia or "").strip() or None, notas=(notas or "").strip() or None,
        registrado_por_user_id=actor_id, origen=ORIGEN_MANUAL,
    )
    db.add(pago)
    db.flush()
    db.refresh(cargo)

    sus = cargo.suscripcion
    liquidado = saldo - monto <= 0
    if liquidado:
        cargo.estado = PAGADO
        cargo.pagado_at = datetime.now(timezone.utc)
        siguiente = cargo.periodo_hasta + timedelta(days=1)
        if siguiente > sus.proxima_renovacion:
            sus.proxima_renovacion = siguiente
    _refrescar_estado(db, sus, hoy)
    _bitacora(db, actor_id, "SUSCRIPCION_PAGO", cargo.organization_id, {
        "cargo_id": cargo.id, "pago_id": pago.id, "importe": str(monto), "metodo": metodo,
        "referencia": pago.referencia, "fecha_pago": fecha, "liquidado": liquidado,
    })
    return pago


def cancelar_cargo(
    db: Session, cargo: CargoSuscripcion, actor_id: Optional[int],
    motivo: Optional[str] = None, hoy: Optional[date] = None,
) -> CargoSuscripcion:
    """Cancela un cargo pendiente sin pagos. No hay reembolsos en esta versión."""
    if cargo.estado == CANCELADO:
        return cargo
    if cargo.estado == PAGADO or cargo.pagos:
        raise ErrorSuscripcion("El cargo ya tiene pagos registrados; no se puede cancelar.", status=409)
    cargo.estado = CANCELADO
    cargo.cancelado_at = datetime.now(timezone.utc)
    cargo.motivo_cancelacion = (motivo or "").strip()[:255] or None
    _refrescar_estado(db, cargo.suscripcion, hoy)
    _bitacora(db, actor_id, "SUSCRIPCION_CARGO_CANCELADO", cargo.organization_id, {
        "cargo_id": cargo.id, "periodo_desde": cargo.periodo_desde,
        "importe": str(cargo.importe), "motivo": cargo.motivo_cancelacion,
    })
    return cargo


# ───────────────────────── Cartera (plataforma) ─────────────────────────

@dataclass
class FilaCartera:
    suscripcion: Suscripcion
    organizacion: Organization
    estado: str
    saldo_vencido: Decimal
    saldo_por_vencer: Decimal


@dataclass
class Cartera:
    filas: List[FilaCartera]
    cartera_vencida: Decimal
    por_vencer: Decimal
    ingreso_mensual_recurrente: Decimal
    por_estado: Dict[str, int]
    sin_suscripcion: int


def cartera(db: Session, hoy: Optional[date] = None) -> Cartera:
    """Todas las suscripciones con su estado calculado y los totales de plataforma.

    - cartera vencida: saldo de cargos pendientes cuyo vencimiento ya pasó.
    - por vencer: saldo de cargos pendientes que aún no vencen.
    - ingreso mensual recurrente: precios pactados (llevados a mes) de las
      suscripciones al corriente o por vencer.
    """
    hoy = _hoy(hoy)
    pares = (
        db.query(Suscripcion, Organization)
        .join(Organization, Organization.id == Suscripcion.organization_id)
        .order_by(Organization.name)
        .all()
    )
    pendientes: Dict[int, List[CargoSuscripcion]] = {}
    for c in db.query(CargoSuscripcion).filter(CargoSuscripcion.estado == PENDIENTE).all():
        pendientes.setdefault(c.organization_id, []).append(c)

    filas: List[FilaCartera] = []
    total_vencido = total_por_vencer = mrr = CERO
    por_estado = {e: 0 for e in ESTADOS}
    for sus, org in pares:
        cargos = pendientes.get(org.id, [])
        estado = estado_de(sus, cargos, hoy)
        vencido = sum((saldo_de(c) for c in cargos if c.vence_el < hoy), CERO)
        por_vencer = sum((saldo_de(c) for c in cargos if c.vence_el >= hoy), CERO)
        filas.append(FilaCartera(sus, org, estado, vencido, por_vencer))
        total_vencido += vencido
        total_por_vencer += por_vencer
        por_estado[estado] += 1
        if estado in (AL_CORRIENTE, POR_VENCER):
            mrr += precio_mensual(_dinero(sus.precio_mxn), sus.periodicidad)

    total_orgs = db.query(Organization).count()
    return Cartera(
        filas=filas, cartera_vencida=total_vencido, por_vencer=total_por_vencer,
        ingreso_mensual_recurrente=mrr, por_estado=por_estado,
        sin_suscripcion=max(total_orgs - len(pares), 0),
    )


__all__ = [
    "AL_CORRIENTE", "POR_VENCER", "VENCIDA", "SUSPENDIDA", "CORTESIA",
    "CargoResumen", "ErrorSuscripcion", "calcular_estado", "siguiente_corte", "precio_mensual",
    "pagado_de", "saldo_de", "obtener", "cargos_de", "estado_de", "guardar_suscripcion",
    "reflejar_plan_de_org", "generar_cargo", "registrar_pago", "cancelar_cargo", "cartera",
]
