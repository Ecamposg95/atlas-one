"""``POST /api/channel/v1/leads`` — clics y formularios de la tienda web.

Sin teléfono = solo métrica anónima por pieza (202). Con teléfono = prospecto
(201) y también cuenta la métrica. `Idempotency-Key` obligatorio: repetirla
devuelve la misma respuesta sin volver a contar.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security.channel_keys import ChannelContext, require_channel_key
from app.modules.canal.leads_schemas import LeadIn, normalizar_telefono
from app.modules.canal.models import ChannelIdempotency, ChannelLead, ChannelProductMetric

router = APIRouter()

MX = ZoneInfo("America/Mexico_City")
RETENCION_IDEMPOTENCIA = timedelta(days=7)


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _cliente_por_telefono(db: Session, org_id: int, phone: str) -> Optional[int]:
    from app.modules.customers.models import Customer

    cand = (
        db.query(Customer)
        .filter(Customer.organization_id == org_id, Customer.phone.isnot(None),
                Customer.phone.like(f"%{phone[-4:]}%"))
        .order_by(Customer.id)
        .all()
    )
    for c in cand:
        if normalizar_telefono(c.phone) == phone:
            return c.id
    return None


def _contar(db: Session, org_id: int, product_ids: list, dia, source: str) -> None:
    """UPSERT atómico del contador: dos clics simultáneos sobre una fila aún
    inexistente no deben perder uno ni tumbar la petición con IntegrityError."""
    if not product_ids:
        return
    if db.connection().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    t = ChannelProductMetric.__table__
    for pid in product_ids:
        stmt = insert(t).values(organization_id=org_id, product_id=pid, day=dia,
                                source=source, count=1)
        db.execute(stmt.on_conflict_do_update(
            index_elements=[t.c.organization_id, t.c.product_id, t.c.day, t.c.source],
            set_={"count": t.c.count + stmt.excluded.count},
        ))


def _responder(status: int, body: dict) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


@router.post("/leads")
def registrar(
    payload: LeadIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    ctx: ChannelContext = Depends(require_channel_key("leads:write")),
    db: Session = Depends(get_db),
):
    from app.models import Product

    org_id = ctx.organization_id
    previa = db.query(ChannelIdempotency).filter_by(
        organization_id=org_id, key=idempotency_key).first()
    if previa is not None:
        guardada = json.loads(previa.response_json)
        return _responder(guardada["status"], guardada["body"])

    ahora = datetime.now(timezone.utc)
    db.query(ChannelIdempotency).filter(
        ChannelIdempotency.created_at < ahora - RETENCION_IDEMPOTENCIA
    ).delete(synchronize_session=False)

    ocurrio = _utc(payload.occurred_at) if payload.occurred_at else ahora
    dia = ocurrio.astimezone(MX).date()

    # Productos de otra org o inexistentes se ignoran (la web no debe reintentar).
    pedidos = list(dict.fromkeys(payload.product_ids))
    validos = []
    if pedidos:
        encontrados = {
            r[0] for r in db.query(Product.id)
            .filter(Product.organization_id == org_id, Product.id.in_(pedidos)).all()
        }
        validos = [p for p in pedidos if p in encontrados]

    _contar(db, org_id, validos, dia, payload.source)

    phone = normalizar_telefono(payload.phone)
    if phone is None:
        status, body = 202, {"recorded": "metric"}
    else:
        lead = ChannelLead(
            id=str(uuid.uuid4()), organization_id=org_id, source=payload.source,
            line=payload.line, name=payload.name, phone=phone, email=payload.email,
            utm=payload.utm.model_dump(exclude_none=True) if payload.utm else None,
            product_ids=validos,
            customer_id=_cliente_por_telefono(db, org_id, phone),
            status="nuevo", occurred_at=ocurrio, created_at=ahora,
        )
        db.add(lead)
        status, body = 201, {"lead_id": lead.id}

    db.add(ChannelIdempotency(organization_id=org_id, key=idempotency_key,
                              response_json=json.dumps({"status": status, "body": body}),
                              created_at=ahora))
    try:
        db.commit()
    except IntegrityError:
        # Carrera: otra petición con la misma clave ganó; devolvemos la suya.
        db.rollback()
        previa = db.query(ChannelIdempotency).filter_by(
            organization_id=org_id, key=idempotency_key).first()
        if previa is None:
            raise
        guardada = json.loads(previa.response_json)
        return _responder(guardada["status"], guardada["body"])
    return _responder(status, body)
