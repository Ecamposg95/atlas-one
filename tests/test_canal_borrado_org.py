"""Borrado forzado de una org con datos del canal «Tienda en línea».

`channel_*` no tienen FK a la org (quedarían huérfanos, y `channel_leads` trae
datos personales); `api_key` sí la tiene y sin entrar en la cascada el borrado
fallaba en cuanto la org tenía una llave.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text

from app.models.organization import Branch, BranchType, Organization
from app.models.platform import ApiKey
from app.modules.canal.models import (
    ChannelAvailability, ChannelIdempotency, ChannelLead, ChannelProductMetric,
)

_TABLAS = ("channel_leads", "channel_product_metrics", "channel_idempotency",
           "channel_availability", "api_key")


def test_borrado_forzado_limpia_tablas_del_canal(client, db, auth_superadmin, superadmin):
    ahora = datetime.now(timezone.utc)
    otra = Organization(name="Org con tienda", status="ACTIVE")
    db.add(otra)
    db.flush()
    db.add(Branch(name="Matriz", organization_id=otra.id, branch_type=BranchType.STORE,
                  can_sell=True, is_active=True))
    pid, vid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(ChannelAvailability(organization_id=otra.id, variant_id=vid, product_id=pid,
                               available=True, changed_at=ahora))
    db.add(ChannelProductMetric(organization_id=otra.id, product_id=pid, day=date.today(),
                                source="vista", count=3))
    db.add(ChannelLead(id=str(uuid.uuid4()), organization_id=otra.id, source="whatsapp",
                       phone="5512345678", name="Ana", status="nuevo",
                       occurred_at=ahora, created_at=ahora))
    db.add(ChannelIdempotency(organization_id=otra.id, key="k-1",
                              response_json='{"status": 201, "body": {}}', created_at=ahora))
    db.add(ApiKey(organization_id=otra.id, name="tienda", prefix="atlas_test0000",
                  hashed_key=uuid.uuid4().hex, scopes='["catalog:read"]',
                  created_by=superadmin.id))
    db.commit()
    org_id = otra.id

    r = client.delete(f"/api/platform/organizations/{org_id}?force=true", headers=auth_superadmin)
    assert r.status_code in (200, 204), r.text
    borrados = r.json()["deleted"]
    for tabla in _TABLAS:
        assert borrados.get(tabla) == 1, (tabla, borrados)
        quedan = db.execute(text(f"SELECT COUNT(*) FROM {tabla} WHERE organization_id = :o"),
                            {"o": org_id}).scalar()
        assert quedan == 0, tabla
    db.expire_all()
    assert db.get(Organization, org_id) is None
