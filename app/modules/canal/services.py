"""Servicios del canal «Tienda en línea»."""
from sqlalchemy.orm import Session

from app.core.security.channel_keys import invalidar_cache_canal


def al_cambiar_sucursales(db: Session, org_id: int) -> None:
    """Gancho al cambiar las sucursales que alimentan la tienda web: olvida el
    cache del módulo y recalcula la disponibilidad dentro de la misma
    transacción (sin commit; lo hace quien llama)."""
    from app.services.canal_disponibilidad import recalcular_disponibilidad

    invalidar_cache_canal(org_id)
    recalcular_disponibilidad(db, org_id)
