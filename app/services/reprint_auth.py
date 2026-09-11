"""Autorizacion para reimprimir un ticket (PIN de supervisor).

Hallazgo §6 de `docs/audits/2026-09-01-comparacion-atlas-rmazh.md`: la
reimpresion no pedia nada. Es un control anti-fraude clasico — sin el, un
cajero reimprime un ticket y lo entrega como comprobante de una venta que no
ocurrio.

A diferencia del origen, aqui NO hay columna `reprint_pin_hash`: el "PIN" es la
contrasena de un usuario con rol gerencial de la misma organizacion, validada
con la misma funcion que el login (`app.core.security.verify_pin`). No se
guarda nada nuevo en la base. Consecuencia directa: como lo que se teclea es
una contrasena real, el limite anti fuerza-bruta de abajo no es un adorno.

LIMITACION CONOCIDA del limite: el contador vive en un dict en memoria del
proceso. Se pierde en cada redespliegue (un reinicio "perdona" los intentos
acumulados) y con N workers el limite efectivo es N*3. Es aceptable hoy —un
solo proceso en Railway— pero si esto escala a varias instancias tiene que
mudarse a la base o a Redis.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import verify_pin
from app.modules.users.models import Role, User, UserOrganization

# Roles que pueden autorizar una reimpresion. Mismo conjunto que ya usa
# app/routers/cash.py para las salidas de efectivo altas (ROLES_SALIDA_ALTA).
ROLES_GERENCIALES = (Role.ADMINISTRADOR, Role.DUEÑO, Role.GERENTE)

# Ventana en la que el cajero puede reimprimir SU PROPIA venta sin PIN. El
# fraude que este control ataca es entregar un ticket viejo (o ajeno) como
# comprobante de una venta que no ocurrio; volver a sacar el ticket de la venta
# que uno acaba de cobrar es el caso del papel atascado, no un fraude. Sin esta
# excepcion el boton "Reimprimir ultimo ticket" del POS pediria PIN en cada
# atasco de impresora.
VENTANA_VENTA_PROPIA_MINUTOS = 10

MAX_INTENTOS = 3
VENTANA_SEGUNDOS = 15 * 60
BLOQUEO_SEGUNDOS = 15 * 60

# (organization_id, user_id) -> marcas de tiempo de los intentos fallidos
# dentro de la ventana vigente. Se podan al consultarse.
_INTENTOS_FALLIDOS: dict[tuple[int, int], list[float]] = {}


def _nombre_rol(rol) -> str:
    return str(rol.value) if hasattr(rol, "value") else str(rol)


def es_rol_gerencial(user: User) -> bool:
    """Un gerente ya tiene la autoridad; su sesion es la autorizacion."""
    return _nombre_rol(getattr(user, "role", None)) in {_nombre_rol(r) for r in ROLES_GERENCIALES}


def es_venta_propia_reciente(sale, user: User) -> bool:
    """La venta la cobro este mismo usuario hace menos de la ventana."""
    if getattr(sale, "seller_id", None) != getattr(user, "id", None):
        return False
    creada = getattr(sale, "created_at", None)
    if creada is None:
        return False
    if creada.tzinfo is None:
        # SQLite devuelve marcas sin zona; se asumen UTC, como las guarda el
        # server_default de SalesDocument.
        creada = creada.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - creada <= timedelta(minutes=VENTANA_VENTA_PROPIA_MINUTOS)


def _supervisores_activos(db: Session, org_id: int) -> list[User]:
    """Usuarios con rol gerencial activos en la organizacion."""
    return (
        db.query(User)
        .join(UserOrganization, UserOrganization.user_id == User.id)
        .filter(
            UserOrganization.organization_id == org_id,
            UserOrganization.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
            User.role.in_(ROLES_GERENCIALES),
        )
        .all()
    )


def verificar_pin_supervisor(db: Session, org_id: int, pin: str) -> Optional[User]:
    """Devuelve el supervisor cuyo PIN coincide, o None.

    Compara contra TODOS los supervisores activos de la organizacion. La
    respuesta no revela cual existe ni cual hizo match: solo el resultado.
    """
    if not pin:
        return None
    for supervisor in _supervisores_activos(db, org_id):
        if not supervisor.password_hash:
            continue
        try:
            if verify_pin(pin, supervisor.password_hash):
                return supervisor
        except Exception:
            # Hash con formato inesperado: ese usuario simplemente no hace
            # match; no debe tumbar la peticion.
            continue
    return None


def _vigentes(marcas: list[float], ahora: float) -> list[float]:
    return [t for t in marcas if ahora - t < VENTANA_SEGUNDOS]


def bloqueo_restante(org_id: int, user_id: int) -> Optional[int]:
    """Segundos que faltan para poder reintentar, o None si no hay bloqueo."""
    ahora = time.time()
    clave = (org_id, user_id)
    marcas = _vigentes(_INTENTOS_FALLIDOS.get(clave, []), ahora)
    if not marcas:
        _INTENTOS_FALLIDOS.pop(clave, None)
        return None
    _INTENTOS_FALLIDOS[clave] = marcas
    if len(marcas) < MAX_INTENTOS:
        return None
    restante = int(BLOQUEO_SEGUNDOS - (ahora - max(marcas)))
    return restante if restante > 0 else None


def registrar_intento_fallido(org_id: int, user_id: int) -> None:
    ahora = time.time()
    clave = (org_id, user_id)
    _INTENTOS_FALLIDOS[clave] = _vigentes(_INTENTOS_FALLIDOS.get(clave, []), ahora) + [ahora]


def limpiar_intentos(org_id: int, user_id: int) -> None:
    """Un acierto borra el historial de fallos de ese usuario."""
    _INTENTOS_FALLIDOS.pop((org_id, user_id), None)
