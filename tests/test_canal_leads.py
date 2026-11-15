"""Prospectos y métricas del canal «Tienda en línea» (POST /api/channel/v1/leads)."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import channel_keys
from app.core.security.channel_keys import MODULO_CANAL, invalidar_cache_canal
from app.models import Organization, Product
from app.models.modules import Module, OrganizationModule
from app.models.platform import ApiKey
from app.modules.canal.leads_schemas import normalizar_telefono
from app.modules.canal.models import ChannelIdempotency, ChannelLead, ChannelProductMetric
from app.modules.customers.models import Customer
from app.modules.platform.api_keys import generate_api_key

URL = "/api/channel/v1/leads"


@pytest.fixture(autouse=True)
def _limpiar_estado():
    invalidar_cache_canal()
    channel_keys.reiniciar_rate_limit()
    yield
    invalidar_cache_canal()
    channel_keys.reiniciar_rate_limit()


def _emitir(db, org, scopes):
    full, prefix, hashed = generate_api_key()
    db.add(ApiKey(organization_id=org.id, name="t", prefix=prefix,
                  hashed_key=hashed, scopes=json.dumps(scopes)))
    db.flush()
    return {"Authorization": f"Bearer {full}"}


def _encender(db, org):
    if db.query(Module).filter(Module.key == MODULO_CANAL).first() is None:
        db.add(Module(key=MODULO_CANAL, name="Tienda en línea"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key=MODULO_CANAL, is_enabled=True))
    db.flush()
    invalidar_cache_canal(org.id)


def _prod(db, org, name="Bolsa"):
    p = Product(organization_id=org.id, name=name)
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def ctx(db, org):
    _encender(db, org)
    return _emitir(db, org, ["leads:write"])


def _h(h, key=None):
    return {**h, "Idempotency-Key": key or str(uuid.uuid4())}


def test_normalizar_telefono():
    assert normalizar_telefono("+52 55 1234 5678") == "5512345678"
    assert normalizar_telefono("(55) 1234-5678") == "5512345678"
    assert normalizar_telefono("1234") is None
    assert normalizar_telefono("") is None


def test_sin_telefono_solo_metrica(client, db, org, ctx):
    p = _prod(db, org)
    r = client.post(URL, headers=_h(ctx), json={
        "source": "web_whatsapp_click", "product_ids": [p.id], "line": "boutique",
        "occurred_at": "2026-11-10T03:00:00Z"})  # 9 pm del 9 en México
    assert r.status_code == 202 and r.json() == {"recorded": "metric"}
    assert db.query(ChannelLead).count() == 0
    m = db.query(ChannelProductMetric).one()
    assert (m.product_id, m.source, m.count) == (p.id, "web_whatsapp_click", 1)
    assert str(m.day) == "2026-11-09"


def test_con_telefono_crea_lead_y_metrica(client, db, org, ctx):
    p = _prod(db, org)
    r = client.post(URL, headers=_h(ctx), json={
        "source": "web_form", "product_ids": [p.id], "name": "Ana", "phone": "+52 55 1234 5678",
        "utm": {"source": "ig"}})
    assert r.status_code == 201
    lead = db.query(ChannelLead).one()
    assert r.json() == {"lead_id": lead.id}
    assert lead.phone == "5512345678" and lead.status == "nuevo" and lead.customer_id is None
    assert lead.organization_id == org.id
    assert db.query(ChannelProductMetric).one().count == 1


def test_liga_cliente_existente(client, db, org, ctx):
    c = Customer(organization_id=org.id, name="Ana", phone="55-1234-5678")
    otra = Organization(name="Otra", status="ACTIVE")
    db.add_all([c, otra])
    db.flush()
    db.add(Customer(organization_id=otra.id, name="X", phone="5512345678"))
    db.flush()
    client.post(URL, headers=_h(ctx), json={"source": "web_form", "phone": "5512345678"})
    assert db.query(ChannelLead).one().customer_id == c.id


def test_idempotencia_misma_respuesta_sin_doble_conteo(client, db, org, ctx):
    p = _prod(db, org)
    h = _h(ctx, "clave-1")
    body = {"source": "web_whatsapp_click", "product_ids": [p.id]}
    r1 = client.post(URL, headers=h, json=body)
    r2 = client.post(URL, headers=h, json=body)
    assert (r1.status_code, r1.json()) == (r2.status_code, r2.json())
    assert db.query(ChannelProductMetric).one().count == 1
    body2 = {"source": "web_form", "phone": "5512345678"}
    h2 = _h(ctx, "clave-2")
    a = client.post(URL, headers=h2, json=body2)
    b = client.post(URL, headers=h2, json=body2)
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    assert db.query(ChannelLead).count() == 1


def test_purga_idempotencia_vieja(client, db, org, ctx):
    db.add(ChannelIdempotency(organization_id=org.id, key="vieja", response_json="{}",
                              created_at=datetime.now(timezone.utc) - timedelta(days=8)))
    db.flush()
    client.post(URL, headers=_h(ctx), json={"source": "web_selection"})
    assert db.query(ChannelIdempotency).filter_by(key="vieja").count() == 0


def test_sin_idempotency_key_422(client, ctx):
    r = client.post(URL, headers=ctx, json={"source": "web_selection"})
    assert r.status_code == 422


def test_productos_ajenos_o_inexistentes_se_ignoran(client, db, org, ctx):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajeno = _prod(db, otra, "Ajeno")
    propio = _prod(db, org)
    r = client.post(URL, headers=_h(ctx), json={
        "source": "web_selection", "product_ids": [ajeno.id, str(uuid.uuid4()), propio.id]})
    assert r.status_code == 202
    ms = db.query(ChannelProductMetric).all()
    assert [m.product_id for m in ms] == [propio.id]


def test_scope_insuficiente_403(client, db, org):
    _encender(db, org)
    h = _emitir(db, org, ["catalog:read"])
    assert client.post(URL, headers=_h(h), json={"source": "web_form"}).status_code == 403


def test_metrica_acumula(client, db, org, ctx):
    p = _prod(db, org)
    for _ in range(3):
        client.post(URL, headers=_h(ctx), json={
            "source": "web_whatsapp_click", "product_ids": [p.id],
            "occurred_at": "2026-11-10T18:00:00Z"})
    assert db.query(ChannelProductMetric).one().count == 3


# ── Reporte ──────────────────────────────────────────────────────────────────
def test_reporte_top_y_prospectos(client, db, org, ctx, auth_admin):
    a, b = _prod(db, org, "A"), _prod(db, org, "B")
    for pid, n in ((a.id, 1), (b.id, 3)):
        for _ in range(n):
            client.post(URL, headers=_h(ctx), json={
                "source": "web_whatsapp_click", "product_ids": [pid],
                "occurred_at": "2026-11-10T18:00:00Z"})
    client.post(URL, headers=_h(ctx), json={
        "source": "web_form", "phone": "5512345678", "occurred_at": "2026-11-10T18:00:00Z"})
    r = client.get("/api/reports/tienda-en-linea?desde=2026-11-10&hasta=2026-11-10", headers=auth_admin)
    assert r.status_code == 200
    j = r.json()
    assert j["prospectos"] == 1
    assert [(x["name"], x["consultas"]) for x in j["piezas"]] == [("B", 3), ("A", 1)]
    r = client.get("/api/reports/tienda-en-linea?desde=2026-11-11&hasta=2026-11-12", headers=auth_admin)
    assert r.json() == {"piezas": [], "prospectos": 0}


def test_reporte_solo_admin(client, db, org, auth_cajero_a):
    _encender(db, org)
    r = client.get("/api/reports/tienda-en-linea?desde=2026-11-10&hasta=2026-11-10", headers=auth_cajero_a)
    assert r.status_code == 403


def test_reporte_404_sin_canal(client, db, org, auth_admin):
    r = client.get("/api/reports/tienda-en-linea?desde=2026-11-10&hasta=2026-11-10", headers=auth_admin)
    assert r.status_code == 404


def test_metrica_nueva_usa_upsert_atomico(client, db, org, ctx):
    """Dos clics sobre una fila nueva suman 2 y el código ya no hace SELECT FOR UPDATE."""
    import inspect
    from app.modules.canal import leads_router
    assert "with_for_update" not in inspect.getsource(leads_router)
    p = _prod(db, org)
    body = {"source": "web_selection", "product_ids": [p.id], "occurred_at": "2026-11-10T18:00:00Z"}
    assert client.post(URL, headers=_h(ctx), json=body).status_code == 202
    assert client.post(URL, headers=_h(ctx), json=body).status_code == 202
    assert db.query(ChannelProductMetric).one().count == 2
