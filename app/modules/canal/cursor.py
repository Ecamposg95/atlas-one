"""Cursor opaco de paginación del canal: base64url de JSON ``[ts, id]``."""
import base64
import json
from datetime import datetime, timezone

from fastapi import HTTPException


def codificar_cursor(ts: datetime, id: str) -> str:
    raw = json.dumps([ts.isoformat(), id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decodificar_cursor(s: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        ts, id_ = json.loads(raw)
        if not isinstance(ts, str) or not isinstance(id_, str):
            raise ValueError
        dt = datetime.fromisoformat(ts)
    except Exception:  # noqa: BLE001 — cualquier basura es un 400
        raise HTTPException(400, "Cursor inválido")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt, id_
