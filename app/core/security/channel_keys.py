"""Llaves de servidor del canal "Tienda en línea" (eleven.boutique, etc.).

Autentica una llave ``atlas_<prefijo>_<secreto>`` (Bearer o ``X-Api-Key``),
exige un scope, que el módulo ``tienda_en_linea`` esté encendido para la org
de la llave y aplica un tope de 120 llamadas por minuto por llave.

Una llave nunca vale en rutas de usuario (esas usan JWT) ni un JWT aquí.
"""
from __future__ import annotations

import collections
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db

CHANNEL_SCOPES = ("catalog:read", "leads:write")
MODULO_CANAL = "tienda_en_linea"

LIMITE_POR_MINUTO = 120
VENTANA_SEG = 60
_CACHE_CANAL_SEG = 60
_LAST_USED_CADA = timedelta(seconds=60)


@dataclass(frozen=True)
class ChannelContext:
    organization_id: int
    key_id: int
    scopes: frozenset[str]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ── Cache de "módulo encendido" (60 s) ───────────────────────────────────────
_cache_canal: dict[int, tuple[float, bool]] = {}
_cache_lock = threading.Lock()


def canal_activo(db: Session, org_id: int) -> bool:
    """¿La org tiene encendido el módulo `tienda_en_linea`? Cache de 60 s."""
    ahora = time.monotonic()
    with _cache_lock:
        hit = _cache_canal.get(org_id)
        if hit and ahora - hit[0] < _CACHE_CANAL_SEG:
            return hit[1]
    from app.models.modules import OrganizationModule

    fila = (
        db.query(OrganizationModule)
        .filter(
            OrganizationModule.organization_id == org_id,
            OrganizationModule.module_key == MODULO_CANAL,
            OrganizationModule.is_enabled.is_(True),
        )
        .first()
    )
    activo = fila is not None
    with _cache_lock:
        _cache_canal[org_id] = (ahora, activo)
    return activo


def invalidar_cache_canal(org_id: Optional[int] = None) -> None:
    """Olvida el estado del módulo de una org (o de todas si `org_id` es None)."""
    with _cache_lock:
        if org_id is None:
            _cache_canal.clear()
        else:
            _cache_canal.pop(org_id, None)


# ── Rate limit: ventana deslizante de 60 s por llave ─────────────────────────
_buckets: dict[int, collections.deque[float]] = {}
_rl_lock = threading.Lock()


def reiniciar_rate_limit() -> None:
    """Vacía los contadores (para pruebas)."""
    with _rl_lock:
        _buckets.clear()


def _consumir(key_id: int) -> Optional[int]:
    """Cuenta una llamada. Devuelve None si pasa o los segundos a esperar."""
    ahora = time.monotonic()
    with _rl_lock:
        dq = _buckets.setdefault(key_id, collections.deque())
        while dq and ahora - dq[0] >= VENTANA_SEG:
            dq.popleft()
        if len(dq) >= LIMITE_POR_MINUTO:
            return max(1, int(VENTANA_SEG - (ahora - dq[0])) + 1)
        dq.append(ahora)
    return None


# ── Dependencia ──────────────────────────────────────────────────────────────
def _extraer_llave(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or "").strip() or None


def _no_autorizado() -> HTTPException:
    return HTTPException(401, "Llave de API inválida o ausente",
                         headers={"WWW-Authenticate": "Bearer"})


def _normalizar(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def require_channel_key(scope: str) -> Callable[..., ChannelContext]:
    """Dependencia FastAPI: valida llave, scope, módulo y rate limit."""

    def _dep(request: Request, db: Session = Depends(get_db)) -> ChannelContext:
        from app.models.platform import ApiKey
        from app.modules.platform.api_keys import hash_api_key

        raw = _extraer_llave(request)
        if not raw or not raw.startswith("atlas_"):
            raise _no_autorizado()

        row = (
            db.query(ApiKey)
            .filter(ApiKey.hashed_key == hash_api_key(raw), ApiKey.revoked_at.is_(None))
            .first()
        )
        if row is None:
            raise _no_autorizado()

        try:
            parsed = json.loads(row.scopes) if row.scopes else []
        except ValueError:
            parsed = []
        scopes = frozenset(s for s in parsed if isinstance(s, str))
        if scope not in scopes:
            raise HTTPException(403, f"La llave no tiene el scope {scope}")

        if not canal_activo(db, row.organization_id):
            raise HTTPException(404, "Canal no disponible")

        espera = _consumir(row.id)
        if espera is not None:
            raise HTTPException(429, "Demasiadas solicitudes",
                                headers={"Retry-After": str(espera)})

        # last_used solo cada ≥60 s: no escribimos (ni hacemos commit) por request.
        ahora = _ahora()
        ultimo = _normalizar(row.last_used_at) if row.last_used_at else None
        if ultimo is None or ahora - ultimo >= _LAST_USED_CADA:
            try:
                row.last_used_at = ahora
                if request.client:
                    row.last_used_ip = request.client.host
                db.commit()
            except Exception:
                db.rollback()

        return ChannelContext(row.organization_id, row.id, scopes)

    return _dep
