"""Single insertion point for cash_audit_log rows (F3 of cash hardening plan).

`audit_cash_event(...)` is FAILSAFE: if writing the audit row raises (DB
schema drift, transient error), the calling business operation must NOT
roll back. We log the exception and proceed.

Cómo se cumple ese "failsafe": el insert va dentro de un SAVEPOINT
(`db.begin_nested()`). Sin él, un flush fallido deja la sesión en
pending-rollback y el `commit()` del llamador revienta con
`PendingRollbackError` — es decir, el audit tumbaría la operación de negocio
que promete no tocar. El savepoint acota el daño: se deshace solo el insert
del audit y la transacción padre sigue viva y confirmable.

Callers pass a `db` session; we add+flush but do NOT commit — the parent
transaction's commit covers it. If the parent rolls back, the audit row
goes with it (same transaction, atomic with the business event).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.cash_audit import CashAuditLog

logger = logging.getLogger(__name__)


def audit_cash_event(
    db: Session,
    *,
    event_type: str,
    organization_id: int,
    session_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    user_id: Optional[int] = None,
    amount: Optional[Decimal | float | int] = None,
    related_table: Optional[str] = None,
    related_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    expected_running_total: Optional[Decimal | float | int] = None,
) -> Optional[CashAuditLog]:
    """Insert one audit row. Never raises (returns None on failure)."""
    try:
        # SAVEPOINT: si el insert falla, se deshace SOLO él. La transacción de
        # negocio del llamador queda limpia y su commit sigue funcionando.
        with db.begin_nested():
            row = CashAuditLog(
                event_type=event_type,
                organization_id=organization_id,
                session_id=session_id,
                branch_id=branch_id,
                user_id=user_id,
                amount=Decimal(str(amount)) if amount is not None else None,
                related_table=related_table,
                related_id=str(related_id) if related_id is not None else None,
                payload_json=payload or None,
                expected_running_total=(
                    Decimal(str(expected_running_total))
                    if expected_running_total is not None else None
                ),
            )
            db.add(row)
            db.flush()
        return row
    except Exception:
        logger.exception(
            "AUDIT_INSERT_FAILED: event_type=%s session_id=%s related_id=%s",
            event_type, session_id, related_id,
        )
        # Don't propagate. Audit is best-effort; the business txn must survive.
        return None
