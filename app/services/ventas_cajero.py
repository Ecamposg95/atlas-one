"""Regla única de lo que la cajera puede ver de las ventas: solo las de HOY
(día calendario de America/Mexico_City) de SU sucursal. Aplica igual al
VENDEDOR (rol de mostrador con menú corto, 2026-11-20). Los demás roles no
cambian. Lo consumen la lista, el detalle y la impresión de `sales.py`.

De caja (`cajera_a_ciegas`): mientras la tienda tenga el conteo ciego encendido
(`organization.conteo_ciego`), el servidor tampoco le manda lo que la pantalla
esconde. Lo consumen `cash.py`, `printer.py` y el tablero de sucursal."""
from datetime import datetime, time, timezone
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


def venta_visible_para_cajero(sale, user) -> bool:
    """True solo si la venta es de la sucursal de la cajera (sin NULL) y de hoy."""
    if sale.branch_id is None or sale.branch_id != user.branch_id:
        return False
    creada = sale.created_at
    if creada is None:
        return False
    if creada.tzinfo is None:       # SQLite devuelve naive: es UTC
        creada = creada.replace(tzinfo=timezone.utc)
    inicio, fin = rango_hoy_mx()
    return inicio <= creada <= fin
