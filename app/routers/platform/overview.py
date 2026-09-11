"""Tablero de plataforma: el día de una organización y la tira "Atención hoy".

- ``GET /api/platform/organizations/{org_id}/overview`` — UNA organización:
  sus sucursales y sus totales. Ningún KPI mezcla dinero de dos clientes.
- ``GET /api/platform/attention-today`` — los pendientes del día de TODAS las
  organizaciones (excepción documentada a la regla de `organization_id`:
  quien los atiende es el mismo superadmin). No suma dinero entre ellas.

El guard `require_platform_admin` (SUPERADMIN o SUPPORT) lo aplica el paquete.
Solo lectura. Caché en proceso de 60 s por (organización, fecha) para no
recalcular en cada auto-refresh del tablero.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.fechas import ZONA_NEGOCIO
from app.routers.platform.stats import _cached
from app.schemas.platform_overview import AttentionTodayRead, OrgOverviewRead
from app.services.org_overview import compute_attention_today, compute_org_overview

router = APIRouter()

_TTL_SECONDS = 60
_MAX_DIAS = 400


def _resolver_dia(date_str: Optional[str]) -> date:
    hoy = datetime.now(ZONA_NEGOCIO).date()
    if date_str is None:
        return hoy
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="date debe ser YYYY-MM-DD")
    # Sin cota, `date` es una llave de caché sin fondo — cualquier fecha
    # arbitraria (pasada o futura) abre una entrada nueva en `_cache`.
    if abs((day - hoy).days) > _MAX_DIAS:
        raise HTTPException(status_code=422, detail="date fuera de rango")
    return day


@router.get("/organizations/{org_id}/overview", response_model=OrgOverviewRead)
def get_org_overview(
    org_id: int,
    date_str: Optional[str] = Query(None, alias="date",
                                    description="YYYY-MM-DD en hora del negocio; default hoy"),
    db: Session = Depends(get_db),
):
    day = _resolver_dia(date_str)
    key = f"org_overview:{org_id}:{day.isoformat()}"
    payload = _cached(key, lambda: compute_org_overview(db, organization_id=org_id, day=day),
                      ttl_seconds=_TTL_SECONDS)
    if payload is None:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    return OrgOverviewRead.model_validate(payload)


@router.get("/attention-today", response_model=AttentionTodayRead)
def get_attention_today(
    date_str: Optional[str] = Query(None, alias="date",
                                    description="YYYY-MM-DD en hora del negocio; default hoy"),
    db: Session = Depends(get_db),
):
    day = _resolver_dia(date_str)
    key = f"attention_today:{day.isoformat()}"
    payload = _cached(key, lambda: compute_attention_today(db, day=day), ttl_seconds=_TTL_SECONDS)
    return AttentionTodayRead.model_validate(payload)
