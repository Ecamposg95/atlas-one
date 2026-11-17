"""Regla única de lo que la cajera puede ver de las ventas: solo las de HOY
(día calendario de America/Mexico_City) de SU sucursal. Los demás roles no
cambian. Lo consumen la lista, el detalle y la impresión de `sales.py`."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from app.models.users import Role
from app.services import metricas_ventas as mv

MX_TZ = ZoneInfo("America/Mexico_City")


def es_cajero(user) -> bool:
    return user.role == Role.CAJERO


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
