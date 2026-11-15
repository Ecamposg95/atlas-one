"""``GET /api/reports/tienda-en-linea`` — lectura mínima del canal en Reportes."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.security.channel_keys import canal_activo
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin
from app.models import Product, User
from app.modules.canal.models import ChannelLead, ChannelProductMetric

router = APIRouter()
MX = ZoneInfo("America/Mexico_City")


@router.get("/tienda-en-linea")
def reporte_tienda_en_linea(
    desde: date = Query(...),
    hasta: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    if not _is_admin(current_user):
        raise HTTPException(403, "Solo administración ve el reporte de la tienda en línea")
    if not canal_activo(db, org_id):
        raise HTTPException(404, "Canal no disponible")
    if hasta < desde:
        raise HTTPException(422, "La fecha final no puede ser anterior a la inicial")

    consultas = func.sum(ChannelProductMetric.count).label("consultas")
    filas = (
        db.query(ChannelProductMetric.product_id, Product.name, consultas)
        .join(Product, Product.id == ChannelProductMetric.product_id)
        .filter(ChannelProductMetric.organization_id == org_id,
                Product.organization_id == org_id,
                ChannelProductMetric.day >= desde, ChannelProductMetric.day <= hasta)
        .group_by(ChannelProductMetric.product_id, Product.name)
        .order_by(consultas.desc(), Product.name)
        .limit(10).all()
    )
    ini = datetime.combine(desde, time.min, tzinfo=MX).astimezone(timezone.utc)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=MX).astimezone(timezone.utc)
    prospectos = (
        db.query(func.count(ChannelLead.id))
        .filter(ChannelLead.organization_id == org_id,
                ChannelLead.occurred_at >= ini, ChannelLead.occurred_at < fin)
        .scalar() or 0
    )
    return {
        "piezas": [{"product_id": p, "name": n, "consultas": int(c)} for p, n, c in filas],
        "prospectos": int(prospectos),
    }
