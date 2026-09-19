"""Autorizacion para reimprimir un ticket (PIN de supervisor).

Hallazgo §6 de `docs/audits/2026-09-01-comparacion-atlas-rmazh.md`: la
reimpresion no pedia nada. Es un control anti-fraude clasico — sin el, un
cajero reimprime un ticket y lo entrega como comprobante de una venta que no
ocurrio.

Lo que se teclea se prueba contra dos hashes de los usuarios con rol gerencial
de la misma organizacion, ambos con la misma funcion que el login
(`app.core.security.verify_pin`):

  1. `users.reprint_pin_hash` — el PIN numerico propio que el dueno fija desde
     el panel de Usuarios. Es lo que el mostrador usa a diario.
  2. `users.password_hash` — el camino historico, cuando esta columna no
     existia. Se conserva porque es la unica llave de quien no se puso PIN.

Consecuencia directa del punto 2: como lo que se teclea puede ser una
contrasena real, el limite anti fuerza-bruta de abajo no es un adorno.

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
#
# `time.monotonic()`, NO `time.time()`: estas marcas solo se comparan entre si
# dentro del mismo proceso (nunca se serializan ni se comparan contra un
# timestamp externo), asi que lo correcto es el reloj monotono. Con
# `time.time()` un salto del reloj de pared (NTP, resincronizacion del
# hypervisor de WSL2, cambio de hora manual) puede hacer que `_vigentes` vea
# `ahora - marca >= VENTANA_SEGUNDOS` para una marca recien puesta y la borre
# de golpe, desactivando el bloqueo a mitad de una prueba (o en produccion).
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
    delta = datetime.now(timezone.utc) - creada
    # `delta` nunca deberia ser negativo (la venta no puede haberse creado en
    # el futuro); si lo es, es un desfase del reloj de pared entre la lectura
    # que guardo `created_at` y esta — visto en la practica con lecturas
    # puntuales de CLOCK_REALTIME que saltan varias horas y se corrigen solas.
    # Tratar ese caso como "NO reciente" es la lectura segura: esta excepcion
    # exime del PIN, asi que un desfase de reloj nunca debe ampliarla.
    return timedelta(0) <= delta <= timedelta(minutes=VENTANA_VENTA_PROPIA_MINUTOS)


def _supervisores_activos(db: Session, org_id: int, branch_id: Optional[int] = None) -> list[User]:
    """Usuarios con rol gerencial activos en la organizacion.

    Con `branch_id` devuelve solo los de esa sucursal. El caller los prueba
    primero y despues el resto de la organizacion: cada candidato cuesta un
    bcrypt, y en el caso normal —el gerente de la sucursal autorizando— no hay
    por que verificar el PIN contra los gerentes de las otras 28 sucursales.
    """
    q = (
        db.query(User)
        .join(UserOrganization, UserOrganization.user_id == User.id)
        .filter(
            UserOrganization.organization_id == org_id,
            UserOrganization.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
            User.role.in_(ROLES_GERENCIALES),
        )
    )
    if branch_id is not None:
        q = q.filter(User.branch_id == branch_id)
    return q.all()


def _primer_match(pin: str, candidatos: list[User], campo: str = "password_hash") -> Optional[User]:
    """Primer supervisor de la lista cuyo hash `campo` coincide, o None.

    `campo` es `reprint_pin_hash` (el PIN propio, si lo configuro) o
    `password_hash` (el camino historico). Quien no tenga ese hash se salta sin
    gastar un bcrypt.
    """
    for supervisor in candidatos:
        hash_guardado = getattr(supervisor, campo, None)
        if not hash_guardado:
            continue
        try:
            if verify_pin(pin, hash_guardado):
                return supervisor
        except Exception:
            # Hash con formato inesperado: ese usuario simplemente no hace
            # match; no debe tumbar la peticion.
            continue
    return None


def verificar_pin_supervisor(
    db: Session, org_id: int, pin: str, branch_id: Optional[int] = None
) -> Optional[User]:
    """Devuelve el supervisor cuyo PIN coincide, o None. Corta en el primero.

    Dos pasos, en este orden: los supervisores de la sucursal de la venta y,
    si ninguno coincide, el resto de la organizacion. El segundo paso NO esta
    condicionado a que la sucursal no tenga gerente propio: el dueno suele
    estar en HQ o sin sucursal asignada, y con esa condicion dejaria de poder
    autorizar en cualquier sucursal que si tenga gerente. Lo que el orden
    ahorra es el bcrypt de los gerentes de las otras 28 sucursales en el caso
    normal, que es el gerente de la sucursal autorizando.

    Dentro de cada lista se prueba PRIMERO el `reprint_pin_hash` de quien lo
    tenga y DESPUES el `password_hash`. El PIN propio es lo que el dueno
    configura desde el panel de Usuarios y lo que el mostrador teclea a diario;
    la contrasena sigue sirviendo para quien no se puso PIN (era el unico
    camino antes de la columna) y no se puede quitar sin romper esas
    organizaciones.

    La respuesta no revela cual supervisor existe ni cual hizo match: solo el
    resultado.
    """
    if not pin:
        return None

    de_sucursal: list[User] = (
        _supervisores_activos(db, org_id, branch_id) if branch_id is not None else []
    )
    for campo in ("reprint_pin_hash", "password_hash"):
        encontrado = _primer_match(pin, de_sucursal, campo)
        if encontrado is not None:
            return encontrado

    ya_probados = {u.id for u in de_sucursal}
    resto = [u for u in _supervisores_activos(db, org_id) if u.id not in ya_probados]
    for campo in ("reprint_pin_hash", "password_hash"):
        encontrado = _primer_match(pin, resto, campo)
        if encontrado is not None:
            return encontrado
    return None


def _vigentes(marcas: list[float], ahora: float) -> list[float]:
    return [t for t in marcas if ahora - t < VENTANA_SEGUNDOS]


def bloqueo_restante(org_id: int, user_id: int) -> Optional[int]:
    """Segundos que faltan para poder reintentar, o None si no hay bloqueo."""
    ahora = time.monotonic()
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
    ahora = time.monotonic()
    clave = (org_id, user_id)
    _INTENTOS_FALLIDOS[clave] = _vigentes(_INTENTOS_FALLIDOS.get(clave, []), ahora) + [ahora]


def limpiar_intentos(org_id: int, user_id: int) -> None:
    """Un acierto borra el historial de fallos de ese usuario."""
    _INTENTOS_FALLIDOS.pop((org_id, user_id), None)
