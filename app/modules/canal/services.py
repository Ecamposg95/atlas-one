"""Servicios del canal «Tienda en línea»."""
from sqlalchemy.orm import Session

from app.core.security.channel_keys import invalidar_cache_canal


def al_cambiar_sucursales(db: Session, org_id: int) -> None:
    """Gancho al cambiar las sucursales que alimentan la tienda web. Por ahora
    solo olvida el cache del módulo; la Tarea 5 agrega aquí el recálculo de
    disponibilidad."""
    invalidar_cache_canal(org_id)
