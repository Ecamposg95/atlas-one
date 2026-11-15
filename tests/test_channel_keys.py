"""Llaves de servidor del canal "Tienda en línea" (scopes, rate limit, módulo)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter, Depends

from app.core.security import channel_keys
from app.core.security.channel_keys import (
    MODULO_CANAL, ChannelContext, invalidar_cache_canal, require_channel_key,
)
from app.models.modules import Module, OrganizationModule
from app.models.platform import ApiKey
from app.modules.platform.api_keys import generate_api_key


@pytest.fixture(autouse=True)
def _limpiar_estado():
    invalidar_cache_canal()
    channel_keys.reiniciar_rate_limit()
    yield
    invalidar_cache_canal()
    channel_keys.reiniciar_rate_limit()


@pytest.fixture()
def ruta(app):
    """Ruta de prueba protegida por la llave. Va en el índice 0 para ganarle al
    catch-all de la SPA y se retira al terminar; vive bajo /api/ porque, con
    frontend/dist presente, los manejadores de 403/404 devuelven el index.html
    a cualquier ruta fuera de /api/."""
    router = APIRouter(dependency_overrides_provider=app)  # usa la BD de prueba

    @router.get("/api/_t/canal")
    def _canal(ctx: ChannelContext = Depends(require_channel_key("catalog:read"))):
        return {"org": ctx.organization_id, "key": ctx.key_id}

    nueva = router.routes[0]
    app.router.routes.insert(0, nueva)
    yield "/api/_t/canal"
    app.router.routes.remove(nueva)


def _emitir(db, org, scopes):
    full, prefix, hashed = generate_api_key()
    row = ApiKey(organization_id=org.id, name="t", prefix=prefix,
                 hashed_key=hashed, scopes=json.dumps(scopes))
    db.add(row)
    db.flush()
    return full, row


def _encender(db, org, activo=True):
    if db.query(Module).filter(Module.key == MODULO_CANAL).first() is None:
        db.add(Module(key=MODULO_CANAL, name="Tienda en línea"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key=MODULO_CANAL, is_enabled=activo))
    db.flush()
    invalidar_cache_canal(org.id)


def _bearer(k):
    return {"Authorization": f"Bearer {k}"}


def test_llave_valida(client, db, org, ruta):
    _encender(db, org)
    k, _ = _emitir(db, org, ["catalog:read"])
    r = client.get(ruta, headers=_bearer(k))
    assert r.status_code == 200 and r.json()["org"] == org.id
    r = client.get(ruta, headers={"X-Api-Key": k})
    assert r.status_code == 200 and r.json()["org"] == org.id


def test_sin_llave(client, db, org, ruta):
    _encender(db, org)
    assert client.get(ruta).status_code == 401


def test_llave_revocada(client, db, org, ruta):
    _encender(db, org)
    k, row = _emitir(db, org, ["catalog:read"])
    row.revoked_at = datetime.now(timezone.utc)
    db.flush()
    assert client.get(ruta, headers=_bearer(k)).status_code == 401


def test_llave_desconocida(client, db, org, ruta):
    _encender(db, org)
    assert client.get(ruta, headers=_bearer("atlas_deadbeef_" + "0" * 32)).status_code == 401


def test_sin_scope(client, db, org, ruta):
    _encender(db, org)
    k, _ = _emitir(db, org, ["leads:write"])
    assert client.get(ruta, headers=_bearer(k)).status_code == 403


def test_jwt_de_usuario_en_canal(client, db, org, ruta, auth_admin):
    _encender(db, org)
    assert client.get(ruta, headers=auth_admin).status_code == 401


def test_llave_en_ruta_de_usuario(client, db, org):
    _encender(db, org)
    k, _ = _emitir(db, org, ["catalog:read"])
    assert client.get("/api/products/", headers=_bearer(k)).status_code == 401


def test_modulo_apagado(client, db, org, ruta):
    k, _ = _emitir(db, org, ["catalog:read"])
    assert client.get(ruta, headers=_bearer(k)).status_code == 404
    _encender(db, org, activo=False)
    assert client.get(ruta, headers=_bearer(k)).status_code == 404


def test_rate_limit(client, db, org, ruta):
    _encender(db, org)
    k, _ = _emitir(db, org, ["catalog:read"])
    k2, _ = _emitir(db, org, ["catalog:read"])
    for _i in range(120):
        assert client.get(ruta, headers=_bearer(k)).status_code == 200
    r = client.get(ruta, headers=_bearer(k))
    assert r.status_code == 429 and "retry-after" in r.headers
    assert client.get(ruta, headers=_bearer(k2)).status_code == 200


def test_last_used_una_vez_por_minuto(client, db, org, ruta, monkeypatch):
    _encender(db, org)
    k, row = _emitir(db, org, ["catalog:read"])
    t0 = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(channel_keys, "_ahora", lambda: t0)
    client.get(ruta, headers=_bearer(k))
    db.refresh(row)
    primero = row.last_used_at
    assert primero is not None
    monkeypatch.setattr(channel_keys, "_ahora", lambda: t0 + timedelta(seconds=10))
    client.get(ruta, headers=_bearer(k))
    db.refresh(row)
    assert row.last_used_at == primero
    monkeypatch.setattr(channel_keys, "_ahora", lambda: t0 + timedelta(seconds=61))
    client.get(ruta, headers=_bearer(k))
    db.refresh(row)
    assert row.last_used_at != primero


def test_crear_llave_scope_invalido(client, org, auth_superadmin):
    r = client.post("/api/platform/api-keys", headers=auth_superadmin,
                    json={"organization_id": org.id, "name": "x", "scopes": ["todo"]})
    assert r.status_code == 422
    r = client.post("/api/platform/api-keys", headers=auth_superadmin,
                    json={"organization_id": org.id, "name": "x", "scopes": ["catalog:read"]})
    assert r.status_code == 201
