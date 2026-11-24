from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict


class DashboardUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    branch_name: str
    role: str = ""


class DashboardShift(BaseModel):
    is_open: bool
    session_id: Optional[int] = None
    opened_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None


class TopProduct(BaseModel):
    name: str
    units: Decimal


class DashboardToday(BaseModel):
    # None = oculto a la cajera con el turno abierto (conteo ciego).
    sales_total: Optional[Decimal] = None
    sales_count: int
    avg_ticket: Optional[Decimal] = None
    returns_total: Optional[Decimal] = None
    returns_count: int
    goal: Optional[Decimal] = None
    goal_progress_pct: Optional[float] = None
    payment_methods: Optional[Dict[str, Decimal]] = None
    top_products: Optional[List[TopProduct]] = None


AlertKind = Literal["low_stock", "no_branch_price", "quote_expiring", "cash_variance"]


class DashboardAlert(BaseModel):
    kind: AlertKind
    count: Optional[int] = None      # used for low_stock, no_branch_price, quote_expiring
    amount: Optional[Decimal] = None # used for cash_variance
    deeplink: str


class BranchDashboardRead(BaseModel):
    user: DashboardUser
    shift: DashboardShift
    today: DashboardToday
    alerts: List[DashboardAlert]
    closing_visible: bool
