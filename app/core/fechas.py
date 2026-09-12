"""Zona horaria del negocio y el "hoy" que de ella se desprende.

Todo lo que el negocio llama "hoy" (el corte de caja, el resumen del día,
la alerta de efectivo fuera de turno) se mide en la hora del local, no en
UTC: una venta de las 23:30 del 5 de agosto pertenece al 5, aunque en UTC
ya sea día 6.

La constante vivía duplicada en `app/routers/cash.py` como `MX_TZ`; aquí
queda una sola vez y configurable, porque el día que Atlas ONE atienda a un
cliente fuera del centro de México basta con mover `BUSINESS_TIMEZONE`.
"""
import logging
import os
from datetime import date, datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

logger = logging.getLogger(__name__)

ZONA_POR_DEFECTO = "America/Mexico_City"
NOMBRE_ZONA_NEGOCIO = os.getenv("BUSINESS_TIMEZONE", ZONA_POR_DEFECTO)

try:
    ZONA_NEGOCIO = ZoneInfo(NOMBRE_ZONA_NEGOCIO)
except Exception:
    # Una errata en BUSINESS_TIMEZONE no puede tumbar el arranque de la API:
    # esto se evalúa al importar, y el import cuelga de media aplicación.
    logger.warning(
        "BUSINESS_TIMEZONE=%r no es una zona horaria válida; se usa %s",
        NOMBRE_ZONA_NEGOCIO, ZONA_POR_DEFECTO,
    )
    NOMBRE_ZONA_NEGOCIO = ZONA_POR_DEFECTO
    ZONA_NEGOCIO = ZoneInfo(ZONA_POR_DEFECTO)


def hoy_negocio(ahora: datetime | None = None) -> date:
    """El día de calendario que el negocio está viviendo en este instante."""
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    return ahora.astimezone(ZONA_NEGOCIO).date()
