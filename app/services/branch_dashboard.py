from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo

# Día local del cajero (Mexico_City). El boundary "hoy" debe coincidir con la
# percepción del usuario, no con UTC — un turno cerrado a las 7pm CST quedaría
# fuera de "hoy" si midiéramos desde UTC midnight (que es 6pm CST).
MX_TZ = ZoneInfo("America/Mexico_City")


def _today_start_local() -> datetime:
    """Inicio del día en zona local del cajero, como datetime aware UTC para
    poder comparar contra columnas DateTime(tz=UTC)."""
    now_local = datetime.now(MX_TZ)
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_local.astimezone(timezone.utc)


from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.organization import Branch
from app.models.products import ProductBranchStatus, ProductVariant, Product
from app.models.returns import SaleReturn
from app.models.sales import Payment, SalesDocument, SalesLineItem, DocumentStatus, DocumentType
from app.models.users import User
from app.schemas.branch_dashboard import (
    BranchDashboardRead,
    DashboardAlert,
    DashboardShift,
    DashboardToday,
    DashboardUser,
    TopProduct,
)


class BranchDashboardService:
    def __init__(self, db: Session, user: User, organization_id: int, branch_id: int):
        self.db = db
        self.user = user
        self.organization_id = organization_id
        self.branch_id = branch_id

    def build(self) -> BranchDashboardRead:
        return BranchDashboardRead(
            user=self._user_block(),
            shift=self._shift_block(),
            today=self._today_block(),
            alerts=self._alerts_block(),
            closing_visible=self._closing_visible(),
        )

    # ---- blocks ----
    def _user_block(self) -> DashboardUser:
        branch = self.db.query(Branch).filter(Branch.id == self.branch_id).first()
        return DashboardUser(
            name=self.user.full_name or self.user.username,
            branch_name=branch.name if branch else "",
            role=str(self.user.role.value if hasattr(self.user.role, 'value') else self.user.role),
        )

    def _shift_block(self) -> DashboardShift:
        # Select only the columns we need to avoid hitting columns that may not
        # exist in the current schema (CashSession.organization_id is known debt
        # on beta; the column exists in the model but not yet in the DB).
        row = (
            self.db.query(CashSession.id, CashSession.opened_at)
            .filter(
                CashSession.user_id == self.user.id,
                CashSession.branch_id == self.branch_id,
                CashSession.closed_at.is_(None),
            )
            .order_by(CashSession.opened_at.desc())
            .first()
        )
        if not row:
            return DashboardShift(is_open=False)
        session_id, opened_at = row
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        duration = int((datetime.now(timezone.utc) - opened_at).total_seconds() // 60)
        return DashboardShift(
            is_open=True,
            session_id=session_id,
            opened_at=opened_at,
            duration_minutes=duration,
        )

    # ---- helpers ----
    def _today_session(self):
        """Sesión de caja a usar para 'hoy': OPEN actual del usuario en su branch,
        o el último turno cerrado HOY (mismo branch, mismo cajero) como fallback.
        Un turno por día implica que estos KPIs reflejan el día completo.

        El boundary 'hoy' usa zona local del cajero (Mexico_City), no UTC. A las
        2am CST (8am UTC), un turno cerrado a las 7pm del día anterior CST
        (1am UTC del día actual) NO debe contar como 'hoy'."""
        today_start = _today_start_local()
        # 1) OPEN del usuario actual
        s = (
            self.db.query(CashSession)
            .filter(
                CashSession.user_id == self.user.id,
                CashSession.branch_id == self.branch_id,
                CashSession.closed_at.is_(None),
            )
            .order_by(CashSession.opened_at.desc())
            .first()
        )
        if s:
            return s
        # 2) Cerrado HOY local (cualquier cajero del branch — un turno por día)
        return (
            self.db.query(CashSession)
            .filter(
                CashSession.branch_id == self.branch_id,
                CashSession.closed_at.isnot(None),
                CashSession.closed_at >= today_start,
            )
            .order_by(CashSession.closed_at.desc())
            .first()
        )

    def _session_sales_filter(self, session):
        """Filtro de ventas por sesión: cash_session_id == session.id, con
        fallback temporal para ventas legacy (cash_session_id IS NULL)."""
        legacy = (
            (SalesDocument.cash_session_id.is_(None))
            & (SalesDocument.branch_id == session.branch_id)
            & (SalesDocument.seller_id == session.user_id)
            & (SalesDocument.created_at >= session.opened_at)
            & (SalesDocument.created_at <= (session.closed_at or datetime.now(timezone.utc)))
        )
        return (SalesDocument.cash_session_id == session.id) | legacy

    def _today_block(self) -> DashboardToday:
        session = self._today_session()
        branch = self.db.query(Branch).filter(Branch.id == self.branch_id).first()
        goal = branch.daily_sales_goal if branch else None

        if session is None:
            # Sin turno hoy → KPIs en cero (pero conserva goal de la branch)
            return DashboardToday(
                sales_total=Decimal("0"),
                sales_count=0,
                avg_ticket=Decimal("0"),
                returns_total=Decimal("0"),
                returns_count=0,
                goal=goal,
                goal_progress_pct=0.0 if goal else None,
                payment_methods={},
                top_products=[],
            )

        session_filter = self._session_sales_filter(session)

        sales_total, sales_count = self._sum_count(
            self.db.query(
                func.coalesce(func.sum(SalesDocument.total_amount), 0),
                func.count(SalesDocument.id),
            ).filter(
                SalesDocument.organization_id == self.organization_id,
                session_filter,
                SalesDocument.status == DocumentStatus.PAID,
                SalesDocument.doc_type == DocumentType.INVOICE,
            )
        )

        # Returns durante la sesión (por cash_session_id; fallback temporal)
        returns_total, returns_count = self._sum_count(
            self.db.query(
                func.coalesce(func.sum(SaleReturn.total_refunded), 0),
                func.count(SaleReturn.id),
            ).filter(
                SaleReturn.organization_id == self.organization_id,
                SaleReturn.branch_id == self.branch_id,
                (
                    (SaleReturn.cash_session_id == session.id)
                    | (
                        (SaleReturn.cash_session_id.is_(None))
                        & (SaleReturn.created_at >= session.opened_at)
                        & (SaleReturn.created_at <= (session.closed_at or datetime.now(timezone.utc)))
                    )
                ),
            )
        )

        avg_ticket = (sales_total / sales_count) if sales_count else Decimal("0")

        goal_pct = None
        if goal and goal > 0:
            goal_pct = float(round((sales_total / goal) * 100, 1))

        payment_methods = self._payment_methods_session(session_filter)
        top_products = self._top_products_today()

        return DashboardToday(
            sales_total=sales_total,
            sales_count=sales_count,
            avg_ticket=avg_ticket,
            returns_total=returns_total,
            returns_count=returns_count,
            goal=goal,
            goal_progress_pct=goal_pct,
            payment_methods=payment_methods,
            top_products=top_products,
        )

    def _payment_methods_session(self, session_filter) -> Dict[str, Decimal]:
        """Sum of payments grouped by method for the active session's PAID sales.

        `Payment.amount` del efectivo es lo que entregó la clienta: el cambio
        (`SalesDocument.change_given`) se resta de CASH, como en el corte y en
        `metricas_ventas.por_metodo`."""
        filtros = (
            SalesDocument.organization_id == self.organization_id,
            session_filter,
            SalesDocument.status == DocumentStatus.PAID,
            SalesDocument.doc_type == DocumentType.INVOICE,
        )
        rows = (
            self.db.query(Payment.method, func.coalesce(func.sum(Payment.amount), 0))
            .join(SalesDocument, SalesDocument.id == Payment.sales_document_id)
            .filter(*filtros)
            .group_by(Payment.method)
            .all()
        )
        totales = {(method.value if hasattr(method, 'value') else str(method)): Decimal(total or 0) for method, total in rows}
        if "CASH" in totales:
            cambio = self.db.query(func.coalesce(func.sum(SalesDocument.change_given), 0)).filter(*filtros).scalar()
            totales["CASH"] -= Decimal(str(cambio or 0))
        return totales

    def _top_products_session(self, session_filter) -> List[TopProduct]:
        """Top 3 products by units sold during the active session."""
        rows = (
            self.db.query(
                Product.name,
                func.coalesce(func.sum(SalesLineItem.quantity), 0).label("units"),
            )
            .select_from(SalesDocument)
            .join(SalesLineItem, SalesLineItem.document_id == SalesDocument.id)
            .join(ProductVariant, ProductVariant.id == SalesLineItem.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                SalesDocument.organization_id == self.organization_id,
                session_filter,
                SalesDocument.status == DocumentStatus.PAID,
                SalesDocument.doc_type == DocumentType.INVOICE,
            )
            .group_by(Product.id, Product.name)
            .order_by(func.sum(SalesLineItem.quantity).desc())
            .limit(5)
            .all()
        )
        return [TopProduct(name=name, units=Decimal(units or 0)) for name, units in rows]

    def _top_products_today(self) -> List[TopProduct]:
        """Top products by units sold across the entire local day (all shifts)."""
        today_start = _today_start_local()
        rows = (
            self.db.query(
                Product.name,
                func.coalesce(func.sum(SalesLineItem.quantity), 0).label("units"),
            )
            .select_from(SalesDocument)
            .join(SalesLineItem, SalesLineItem.document_id == SalesDocument.id)
            .join(ProductVariant, ProductVariant.id == SalesLineItem.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                SalesDocument.organization_id == self.organization_id,
                SalesDocument.branch_id == self.branch_id,
                SalesDocument.status == DocumentStatus.PAID,
                SalesDocument.doc_type == DocumentType.INVOICE,
                SalesDocument.created_at >= today_start,
            )
            .group_by(Product.id, Product.name)
            .order_by(func.sum(SalesLineItem.quantity).desc())
            .limit(5)
            .all()
        )
        return [TopProduct(name=name, units=Decimal(units or 0)) for name, units in rows]

    @staticmethod
    def _sum_count(query) -> tuple:
        row = query.first()
        if row is None:
            return Decimal("0"), 0
        total, count = row
        return Decimal(total or 0), int(count or 0)

    def _alerts_block(self) -> List[DashboardAlert]:
        out: List[DashboardAlert] = []

        # 1. Low stock — units in this branch where on-hand qty is below the min_stock_alert
        low_stock = (
            self.db.query(func.count(StockOnHand.id))
            .join(ProductBranchStatus,
                  (ProductBranchStatus.variant_id == StockOnHand.variant_id)
                  & (ProductBranchStatus.branch_id == StockOnHand.branch_id))
            .filter(
                StockOnHand.organization_id == self.organization_id,
                StockOnHand.branch_id == self.branch_id,
                StockOnHand.is_active == True,
                ProductBranchStatus.min_stock_alert.isnot(None),
                ProductBranchStatus.min_stock_alert > 0,
                StockOnHand.qty_on_hand < ProductBranchStatus.min_stock_alert,
            )
            .scalar()
            or 0
        )
        if low_stock:
            out.append(DashboardAlert(
                kind="low_stock", count=int(low_stock),
                deeplink="/products?filter=low_stock",
            ))

        # 2. Products active in branch POS but without a branch price override
        no_price = (
            self.db.query(func.count(ProductBranchStatus.id))
            .filter(
                ProductBranchStatus.organization_id == self.organization_id,
                ProductBranchStatus.branch_id == self.branch_id,
                ProductBranchStatus.is_active_pos == True,
                ProductBranchStatus.price_override.is_(None),
            )
            .scalar()
            or 0
        )
        if no_price:
            out.append(DashboardAlert(
                kind="no_branch_price", count=int(no_price),
                deeplink="/products?filter=no_price",
            ))

        # 3. Cash variance from last CLOSED session at this branch (any cashier).
        last_closed = (
            self.db.query(CashSession.id, CashSession.difference)
            .filter(
                CashSession.branch_id == self.branch_id,
                CashSession.closed_at.isnot(None),
            )
            .order_by(CashSession.closed_at.desc())
            .first()
        )
        if last_closed is not None:
            _, diff = last_closed
            if diff is not None and abs(Decimal(diff)) >= Decimal("1"):
                out.append(DashboardAlert(
                    kind="cash_variance",
                    amount=Decimal(diff),
                    deeplink="/cash-history",
                ))

        return out

    def _closing_visible(self) -> bool:
        if not self._shift_block().is_open:
            return False
        branch = self.db.query(Branch).filter(Branch.id == self.branch_id).first()
        if not branch or not branch.closing_time:
            return False
        now = datetime.now(MX_TZ)
        closing_dt = datetime.combine(now.date(), branch.closing_time).replace(tzinfo=MX_TZ)
        delta = closing_dt - now
        return timedelta(minutes=-30) <= delta <= timedelta(hours=1)
