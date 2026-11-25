"""Regla única de lo que la cajera puede ver de las ventas: las de SU sucursal
dentro del plazo de la tienda (`organization.dias_ventas_caja`, 30 días por
omisión; 0 = solo hoy), contado en días calendario de America/Mexico_City.
Nunca totales ni resúmenes. Aplica igual al VENDEDOR (rol de mostrador con menú
corto, 2026-11-20). Los demás roles no cambian. Lo consumen la lista, el
detalle y la impresión de `sales.py`, y las devoluciones (`returns.py`).

`rango_hoy_mx` sigue existiendo para lo que SÍ es solo de hoy: sus turnos de
caja y el último ticket.

De caja (`cajera_a_ciegas`): mientras la tienda tenga el conteo ciego encendido
(`organization.conteo_ciego`), el servidor tampoco le manda lo que la pantalla
esconde. Lo consumen `cash.py`, `printer.py` y el tablero de sucursal."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.users import Role
from app.services import metricas_ventas as mv

MX_TZ = ZoneInfo("America/Mexico_City")


def es_cajero(user) -> bool:
    return user.role in (Role.CAJERO, Role.VENDEDOR)


def cajera_a_ciegas(db, user) -> bool:
    """True si es cajera y su tienda tiene el conteo ciego encendido (por
    omisión lo está; solo un `False` explícito lo apaga). Apagado, la caja ve
    el esperado con el turno abierto y el servidor no recorta nada."""
    if not es_cajero(user):
        return False
    from app.models import Branch, Organization
    apagado = (
        db.query(Organization.id)
        .join(Branch, Branch.organization_id == Organization.id)
        .filter(Branch.id == user.branch_id, Organization.conteo_ciego.is_(False))
        .first()
    )
    return apagado is None


def rango_hoy_mx() -> tuple[datetime, datetime]:
    """Inicio y fin (inclusive) de hoy en México, con zona horaria."""
    hoy = mv.hoy_mx()
    return (
        datetime.combine(hoy, time.min, tzinfo=MX_TZ),
        datetime.combine(hoy, time.max, tzinfo=MX_TZ),
    )


DIAS_VENTAS_CAJA_OMISION = 30
DIAS_VENTAS_CAJA_MAX = 3650


def dias_ventas_caja(db, user) -> int:
    """Días hacia atrás que la caja puede consultar (y devolver). Sale de la
    organización de la sucursal del usuario; sin dato, 30."""
    if db is None or getattr(user, "branch_id", None) is None:
        return DIAS_VENTAS_CAJA_OMISION
    from app.models import Branch, Organization
    fila = (
        db.query(Organization.dias_ventas_caja)
        .join(Branch, Branch.organization_id == Organization.id)
        .filter(Branch.id == user.branch_id)
        .first()
    )
    if fila is None or fila[0] is None:
        return DIAS_VENTAS_CAJA_OMISION
    return max(0, min(int(fila[0]), DIAS_VENTAS_CAJA_MAX))


def rango_visible_cajero(db, user) -> tuple[datetime, datetime]:
    """Inicio (00:00 de hace N días) y fin (hoy 23:59:59) de lo que la caja ve."""
    inicio_hoy, fin_hoy = rango_hoy_mx()
    return inicio_hoy - timedelta(days=dias_ventas_caja(db, user)), fin_hoy


def venta_visible_para_cajero(sale, user, db=None) -> bool:
    """True solo si la venta es de la sucursal de la cajera (sin NULL) y cae
    dentro del plazo de la tienda. `db` es opcional: si no viene se usa la
    sesión del propio objeto."""
    if sale.branch_id is None or sale.branch_id != user.branch_id:
        return False
    creada = sale.created_at
    if creada is None:
        return False
    if creada.tzinfo is None:       # SQLite devuelve naive: es UTC
        creada = creada.replace(tzinfo=timezone.utc)
    if db is None:
        from sqlalchemy.orm import object_session
        db = object_session(sale) or object_session(user)
    inicio, fin = rango_visible_cajero(db, user)
    return inicio <= creada <= fin
