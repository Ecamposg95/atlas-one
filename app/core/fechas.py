"""Zona horaria del negocio y el "hoy" que de ella se desprende.

Todo lo que el negocio llama "hoy" (el corte de caja, el resumen del día,
la alerta de efectivo fuera de turno) se mide en la hora del local, no en
UTC: una venta de las 23:30 del 5 de agosto pertenece al 5, aunque en UTC
ya sea día 6.

La constante vivía duplicada en `app/routers/cash.py` como `MX_TZ`; aquí
queda una sola vez y configurable, porque el día que Atlas ONE atienda a un
cliente fuera del centro de México basta con mover `BUSINESS_TIMEZONE`.
"""
import os
from datetime import date, datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

NOMBRE_ZONA_NEGOCIO = os.getenv("BUSINESS_TIMEZONE", "America/Mexico_City")
ZONA_NEGOCIO = ZoneInfo(NOMBRE_ZONA_NEGOCIO)


def hoy_negocio(ahora: datetime | None = None) -> date:
    """El día de calendario que el negocio está viviendo en este instante."""
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    return ahora.astimezone(ZONA_NEGOCIO).date()
