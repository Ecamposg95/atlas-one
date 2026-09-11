"""Append-only audit log for cash movements (F3 of cash hardening plan).

Every monetary event in the cash domain — sale created, payment recorded,
refund approved, manual movement, session opened/closed, invariant failed —
inserts a row here. Never UPDATE, never DELETE.

Querying `WHERE session_id = X ORDER BY ts` reconstructs the full life of
a session for debugging discrepancies in minutes (target: replace ad-hoc psql).
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


# Event-type vocabulary. Keep flat enums (str), not Enum types, so adding
# a new event in a hotfix doesn't need a DB migration.
class CashAuditEvent:
    SALE_CREATED      = "SALE_CREATED"
    PAYMENT_RECORDED  = "PAYMENT_RECORDED"
    REFUND_APPROVED   = "REFUND_APPROVED"
    REFUND_REJECTED   = "REFUND_REJECTED"
    MANUAL_INFLOW     = "MANUAL_INFLOW"
    MANUAL_OUTFLOW    = "MANUAL_OUTFLOW"
    SESSION_OPENED    = "SESSION_OPENED"
    SESSION_CLOSED    = "SESSION_CLOSED"
    INVARIANT_FAILED  = "INVARIANT_FAILED"
    CLOSURE_WARNING   = "CLOSURE_WARNING"
    # Reimpresion de tickets (auditoria Rmazh §6). No mueven efectivo, pero el
    # fraude que el PIN ataca —entregar una copia como comprobante de una venta
    # que no ocurrio— se investiga con el mismo hilo: quien, cuando, que venta.
    TICKET_REPRINTED   = "TICKET_REPRINTED"
    REPRINT_PIN_FAILED = "REPRINT_PIN_FAILED"


class CashAuditLog(Base):
    __tablename__ = "cash_audit_log"

    id                     = Column(Integer, primary_key=True, autoincrement=True)
    ts                     = Column(DateTime(timezone=True), nullable=False,
                                    server_default=func.now())
    session_id             = Column(Integer, ForeignKey("cash_sessions.id"),
                                    nullable=True, index=True)
    organization_id        = Column(Integer, nullable=False, index=True)
    branch_id              = Column(Integer, nullable=True)
    user_id                = Column(Integer, nullable=True)

    event_type             = Column(String(40), nullable=False, index=True)
    amount                 = Column(Numeric(12, 2), nullable=True)

    # FK-like pointer to the source row, but as soft string (audit may
    # outlive cascading deletes if any are added later).
    related_table          = Column(String(40), nullable=True)
    related_id             = Column(String(64), nullable=True)

    # Free-form context: before/after, supervisor_id, reason, override
    # flags, breakdown snapshot, invariant code, etc.
    payload_json           = Column(JSONB, nullable=True)

    # Snapshot of breakdown.expected at the moment of the event.
    expected_running_total = Column(Numeric(12, 2), nullable=True)


Index("ix_cash_audit_log_session_ts", CashAuditLog.session_id, CashAuditLog.ts)
