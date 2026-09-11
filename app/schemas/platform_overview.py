"""Respuestas del tablero de plataforma (spec 2026-09-09 §4, adaptada).

`OrgOverviewRead` es el día de UNA organización; `AttentionTodayRead` es la
tira de pendientes que sí cruza a todas.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class OverviewMix(BaseModel):
    cash: float
    card: float
    transfer: float
    other: float
    cash_pct: Optional[float] = None
    card_pct: Optional[float] = None
    transfer_pct: Optional[float] = None
    other_pct: Optional[float] = None


class OverviewCash(BaseModel):
    status: Literal["OPEN", "CLOSED", "NONE"]
    open_sessions: int
    open_hours: Optional[float] = None
    last_close_at: Optional[str] = None
    last_difference: Optional[float] = None
    last_session_id: Optional[int] = None


class OverviewReturns(BaseModel):
    pending_count: int
    pending_amount: float
    oldest_pending_days: Optional[int] = None
    approved_today_count: int
    approved_today_amount: float


class BranchOverviewRow(BaseModel):
    id: int
    name: str
    org_id: int
    org_name: str
    sales_today: float
    sales_yesterday: float
    sales_same_weekday_last_week: float
    delta_yesterday_pct: Optional[float] = None
    delta_last_week_pct: Optional[float] = None
    tickets_today: int
    avg_ticket: Optional[float] = None
    mix: OverviewMix
    cash: OverviewCash
    returns: OverviewReturns
    cancellations_today_count: int
    cancellations_today_amount: float


class OverviewTotals(BaseModel):
    units: int
    sales_today: float
    tickets_today: int
    avg_ticket: Optional[float] = None
    open_sessions: int
    units_with_open_session: int
    returns_pending_count: int
    returns_pending_amount: float
    cancellations_today_count: int
    mix: OverviewMix


class OrgOverviewRead(BaseModel):
    organization_id: int
    organization_name: str
    date: str
    generated_at: str
    totals: OverviewTotals
    rows: List[BranchOverviewRow]


class AttentionItem(BaseModel):
    id: int
    name: str
    org_id: int
    org_name: str
    value: Optional[float] = None
    detail: str


class AttentionCounts(BaseModel):
    """Cuántos pendientes hay DE VERDAD en cada lista. Las listas vienen
    recortadas (tope global y reparto entre organizaciones), así que el chip
    necesita este conteo para decir "10 de 23" en vez de mentir con "10"."""
    no_cut: int
    cut_difference: int
    oldest_returns: int
    cancelled_today: int


class AttentionTodayRead(BaseModel):
    date: str
    generated_at: str
    counts: AttentionCounts
    no_cut: List[AttentionItem]
    cut_difference: List[AttentionItem]
    oldest_returns: List[AttentionItem]
    cancelled_today: List[AttentionItem]
