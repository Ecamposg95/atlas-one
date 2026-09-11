"""
Tests: Cash register reconciliation matrix (F1 of cash hardening plan).

20+ cases covering all combinations of payment methods, change, manual
movements, and refunds (same-day / cross-session / mixed). The single source
of truth is `compute_expected_cash` in app/services/cash_reconciliation.py.

Each test follows: setup state → invoke compute_expected_cash → assert
exact Decimal value. Tests target the function directly to avoid coupling
to the surrounding HTTP layer.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from app.models.cash import CashSession, CashSessionStatus, CashMovement
from app.models.sales import SalesDocument, DocumentStatus, Payment, PaymentMethod
from app.services.cash_reconciliation import compute_expected_cash


# ── Helpers ──────────────────────────────────────────────────────────────────


def _open_session(db, user, branch, opening=Decimal("0"), opened_at=None):
    s = CashSession(
        branch_id=branch.id,
        user_id=user.id,
        status=CashSessionStatus.OPEN,
        opening_balance=Decimal(str(opening)),
        opened_at=opened_at or datetime.now(timezone.utc),
        organization_id=branch.organization_id,
    )
    db.add(s)
    db.flush()
    return s


def _create_sale(
    db, user, branch, total, payments, *,
    session=None, change_given=None, status=DocumentStatus.PAID,
    created_at=None,
):
    """payments: list of (PaymentMethod, amount)."""
    sale = SalesDocument(
        seller_id=user.id,
        branch_id=branch.id,
        organization_id=branch.organization_id,
        total_amount=Decimal(str(total)),
        subtotal=Decimal(str(total)),
        tax_amount=Decimal("0"),
        status=status,
        cash_session_id=session.id if session else None,
        change_given=Decimal(str(change_given)) if change_given is not None else None,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(sale)
    db.flush()
    for method, amount in payments:
        db.add(Payment(
            sales_document_id=sale.id,
            method=method,
            amount=Decimal(str(amount)),
            organization_id=branch.organization_id,
            created_at=created_at or datetime.now(timezone.utc),
        ))
    db.flush()
    return sale


def _approve_refund(db, sale, refund_amount, session, *, status_after=None):
    """Simulate approve_return side-effects:
       - update sale.status to REFUNDED_PARTIAL/TOTAL
       - update sale.total_amount to net
       - create CashMovement OUT with 'Devolución #' prefix
    """
    refund_amount = Decimal(str(refund_amount))
    new_total = Decimal(str(sale.total_amount)) - refund_amount
    if status_after is None:
        status_after = (
            DocumentStatus.REFUNDED_TOTAL if new_total <= 0
            else DocumentStatus.REFUNDED_PARTIAL
        )
    sale.status = status_after
    sale.total_amount = max(new_total, Decimal("0"))
    short_id = uuid.uuid4().hex[:8].upper()
    cm = CashMovement(
        session_id=session.id,
        type="OUT",
        amount=refund_amount,
        reason=f"Devolución #{short_id} - Test",
    )
    db.add(cm)
    db.flush()
    return cm


def _add_movement(db, session, mtype, amount, reason="manual"):
    cm = CashMovement(
        session_id=session.id,
        type=mtype,
        amount=Decimal(str(amount)),
        reason=reason,
    )
    db.add(cm)
    db.flush()
    return cm


# ── Class: existing tests preserved ──────────────────────────────────────────


class TestCashCalculations:
    """Original 3 baseline tests — preserved as-is for back-compat."""

    def _create_cash_session(self, db, user, branch, opening=Decimal("500")):
        return _open_session(db, user, branch, opening)

    def _create_sale(self, db, user, branch, total, payments_list, session_opened_at):
        return _create_sale(db, user, branch, total, payments_list)

    def test_expected_balance_simple_cash_sale(self, db, cajero_a, branch_a):
        from app.routers.cash import get_session_audit_data
        session = self._create_cash_session(db, cajero_a, branch_a, Decimal("500"))
        self._create_sale(db, cajero_a, branch_a, total=100,
                          payments_list=[(PaymentMethod.CASH, 100)],
                          session_opened_at=session.opened_at)
        audit = get_session_audit_data(db, session.id)
        assert float(audit["expected"]["cash_physical"]) == 600.0

    def test_change_subtracted_from_net_cash(self, db, cajero_a, branch_a):
        from app.routers.cash import get_session_audit_data
        session = self._create_cash_session(db, cajero_a, branch_a, Decimal("500"))
        self._create_sale(db, cajero_a, branch_a, total=90,
                          payments_list=[(PaymentMethod.CASH, 100)],
                          session_opened_at=session.opened_at)
        audit = get_session_audit_data(db, session.id)
        assert float(audit["expected"]["cash_physical"]) == 590.0

    def test_closing_balance_rejects_negative(self, client, auth_cajero_a, db, cajero_a, branch_a):
        self._create_cash_session(db, cajero_a, branch_a)
        resp = client.post("/api/cash/close",
                           json={"closing_balance": -100, "notes": "test"},
                           headers=auth_cajero_a)
        assert resp.status_code == 400


# ── Section A: Payment-method matrix (cases 1-7) ─────────────────────────────


class TestPaymentMethodMatrix:
    """Cases 1-7: cash/card/transfer/mixed combinations."""

    # Case 1: Cash exact, no change
    def test_cash_exact_no_change(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=100)
        _create_sale(db, cajero_a, branch_a, total=50,
                     payments=[(PaymentMethod.CASH, 50)],
                     session=s, change_given=0)
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("150")  # 100 + 50

    # Case 2: Cash with change
    def test_cash_with_change(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=100)
        _create_sale(db, cajero_a, branch_a, total=50,
                     payments=[(PaymentMethod.CASH, 100)],
                     session=s, change_given=50)
        result = compute_expected_cash(db, s)
        # gross_cash 100 - change 50 = net 50; expected 100 + 50 = 150
        assert result.expected == Decimal("150")

    # Case 3: Card exclusive
    def test_card_only_no_cash_impact(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=200)
        _create_sale(db, cajero_a, branch_a, total=300,
                     payments=[(PaymentMethod.CARD, 300)],
                     session=s)
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("200")  # opening only, no cash flow
        assert result.gross_cash == Decimal("0")

    # Case 4: Transfer exclusive
    def test_transfer_only_no_cash_impact(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=200)
        _create_sale(db, cajero_a, branch_a, total=500,
                     payments=[(PaymentMethod.TRANSFER, 500)],
                     session=s)
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("200")
        assert result.gross_cash == Decimal("0")

    # Case 5: Mixed cash + card
    def test_mixed_cash_card(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=100)
        _create_sale(db, cajero_a, branch_a, total=500,
                     payments=[(PaymentMethod.CASH, 200),
                               (PaymentMethod.CARD, 300)],
                     session=s, change_given=0)
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("300")  # 100 + 200 cash net
        assert result.gross_cash == Decimal("200")

    # Case 6: Mixed cash + card + transfer
    def test_mixed_cash_card_transfer(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=50)
        _create_sale(db, cajero_a, branch_a, total=1000,
                     payments=[(PaymentMethod.CASH, 100),
                               (PaymentMethod.CARD, 400),
                               (PaymentMethod.TRANSFER, 500)],
                     session=s, change_given=0)
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("150")  # 50 + 100 cash

    # Case 7: Mixed with cash overpayment producing change
    def test_mixed_cash_overpayment_with_change(self, db, cajero_a, branch_a):
        # Sale 500: paid 400 card + 200 cash → 100 change
        s = _open_session(db, cajero_a, branch_a, opening=0)
        _create_sale(db, cajero_a, branch_a, total=500,
                     payments=[(PaymentMethod.CARD, 400),
                               (PaymentMethod.CASH, 200)],
                     session=s, change_given=100)
        result = compute_expected_cash(db, s)
        # gross_cash 200 - change 100 = net 100
        assert result.expected == Decimal("100")


# ── Section B: Refunds (cases 8-12, 15) ──────────────────────────────────────


class TestRefundReconciliation:
    """Cases 8-12, 15: refund flows."""

    # Case 8: Refund total same-day cash
    def test_refund_total_same_day_cash(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=0)
        sale = _create_sale(db, cajero_a, branch_a, total=100,
                            payments=[(PaymentMethod.CASH, 100)],
                            session=s, change_given=0)
        _approve_refund(db, sale, refund_amount=100, session=s)
        result = compute_expected_cash(db, s)
        # Money in (100) and out (100) → net zero
        assert result.expected == Decimal("0")
        assert result.gross_cash == Decimal("100")  # original payment counted
        assert result.refund_cash_outflows == Decimal("100")

    # Case 9: Refund partial same-day cash
    def test_refund_partial_same_day_cash(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=50)
        sale = _create_sale(db, cajero_a, branch_a, total=200,
                            payments=[(PaymentMethod.CASH, 200)],
                            session=s, change_given=0)
        _approve_refund(db, sale, refund_amount=50, session=s)
        result = compute_expected_cash(db, s)
        # opening 50 + cash 200 - refund 50 = 200
        assert result.expected == Decimal("200")

    # Case 10: Refund total cross-session (sale en otra sesión, refund en esta)
    def test_refund_cross_session_cash(self, db, cajero_a, branch_a):
        old_session = _open_session(
            db, cajero_a, branch_a, opening=0,
            opened_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        sale = _create_sale(db, cajero_a, branch_a, total=80,
                            payments=[(PaymentMethod.CASH, 80)],
                            session=old_session, change_given=0,
                            created_at=old_session.opened_at)
        # La sesión vieja se cierra antes de abrir la de hoy: un cajero no
        # puede tener dos sesiones abiertas a la vez en la misma sucursal
        # (índice uq_cash_sessions_open_user_branch).
        old_session.status = CashSessionStatus.CLOSED
        old_session.closed_at = old_session.opened_at + timedelta(hours=8)
        db.flush()
        # Refund hoy en NUEVA sesión
        new_session = _open_session(db, cajero_a, branch_a, opening=200)
        _approve_refund(db, sale, refund_amount=80, session=new_session)
        result = compute_expected_cash(db, new_session)
        # New session: opening 200, sin ventas hoy, refund OUT 80 → 120
        # Cash original (80) entró en old_session, NO debe contar aquí
        assert result.expected == Decimal("120")
        assert result.gross_cash == Decimal("0")
        assert result.refund_cash_outflows == Decimal("80")

    # Case 11: Refund of MIXED sale — cash refund only partial of total
    def test_refund_of_mixed_sale_cash_portion(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=0)
        sale = _create_sale(db, cajero_a, branch_a, total=300,
                            payments=[(PaymentMethod.CASH, 100),
                                      (PaymentMethod.CARD, 200)],
                            session=s, change_given=0)
        # Refund partial $50 — affects cash
        _approve_refund(db, sale, refund_amount=50, session=s)
        result = compute_expected_cash(db, s)
        # gross_cash 100 - refund 50 = 50 net
        assert result.expected == Decimal("50")

    # Case 12: Multiple partial refunds on the same sale
    def test_multiple_partial_refunds_same_sale(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=100)
        sale = _create_sale(db, cajero_a, branch_a, total=500,
                            payments=[(PaymentMethod.CASH, 500)],
                            session=s, change_given=0)
        _approve_refund(db, sale, refund_amount=100, session=s,
                        status_after=DocumentStatus.REFUNDED_PARTIAL)
        _approve_refund(db, sale, refund_amount=150, session=s,
                        status_after=DocumentStatus.REFUNDED_PARTIAL)
        result = compute_expected_cash(db, s)
        # opening 100 + 500 - 100 - 150 = 350
        assert result.expected == Decimal("350")

    # Case 15: Refund of NON-cash method (card refund) — does NOT affect cash
    def test_refund_non_cash_method_no_cash_impact(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=200)
        sale = _create_sale(db, cajero_a, branch_a, total=300,
                            payments=[(PaymentMethod.CARD, 300)],
                            session=s)
        # Mark sale as refunded but DON'T create CashMovement OUT
        # (because refund went back to card, not cash from drawer)
        sale.status = DocumentStatus.REFUNDED_TOTAL
        sale.total_amount = Decimal("0")
        db.flush()
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("200")  # opening only, no cash impact
        assert result.refund_cash_outflows == Decimal("0")


# ── Section C: Manual movements (cases 13-14) ────────────────────────────────


class TestManualMovements:
    """Cases 13-14: manual cash inflows/outflows."""

    # Case 13: Manual inflow (cashier adds money to drawer)
    def test_manual_inflow_added_to_expected(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=100)
        _add_movement(db, s, "IN", 50, reason="Reposición de fondo")
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("150")
        assert result.manual_inflows == Decimal("50")

    # Case 14: Manual outflow (gasto, retiro, etc.) — NOT a refund
    def test_manual_outflow_subtracted(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=500)
        _add_movement(db, s, "OUT", 80, reason="Pago de gasolina")
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("420")
        assert result.manual_outflows == Decimal("80")
        assert result.refund_cash_outflows == Decimal("0")

    # Case 14b: OUT con prefix Devolución cuenta como refund, no manual
    def test_outflow_with_devolucion_prefix_classified_as_refund(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=500)
        _add_movement(db, s, "OUT", 80, reason="Devolución #ABC123 - test")
        result = compute_expected_cash(db, s)
        assert result.refund_cash_outflows == Decimal("80")
        assert result.manual_outflows == Decimal("0")
        assert result.expected == Decimal("420")  # mismo resultado, distinto bucket


# ── Section D: Edge cases (cases 16, 19, 20) ─────────────────────────────────


class TestEdgeCases:
    """Cases 16, 19, 20: legacy/edge."""

    # Case 16: Sale with cash_session_id NULL — legacy fallback via seller+branch+time
    def test_legacy_sale_null_session_id(self, db, cajero_a, branch_a):
        # Open session in the past so the sale "now" is inside the window.
        s = _open_session(db, cajero_a, branch_a, opening=100,
                          opened_at=datetime.now(timezone.utc) - timedelta(minutes=10))
        _create_sale(db, cajero_a, branch_a, total=200,
                     payments=[(PaymentMethod.CASH, 200)],
                     session=None,  # ← legacy NULL
                     change_given=0)
        result = compute_expected_cash(db, s)
        # Fallback picks it up: same seller, same branch, created_at in [opened, now)
        assert result.expected == Decimal("300")
        assert result.gross_cash == Decimal("200")

    # Case 19: Empty session (no activity at all)
    def test_empty_session_returns_opening(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=300)
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("300")
        assert result.gross_cash == Decimal("0")
        assert result.change_given == Decimal("0")

    # Case 20: Multiple PCs same cajero — all sales count once
    def test_multi_pc_same_cashier_sums_all_sales(self, db, cajero_a, branch_a):
        # Past-anchored opened_at so all sales fall in [opened, now()].
        s = _open_session(db, cajero_a, branch_a, opening=0,
                          opened_at=datetime.now(timezone.utc) - timedelta(hours=1))
        # 3 sales from "different PCs" — same session
        for _ in range(3):
            _create_sale(db, cajero_a, branch_a, total=100,
                         payments=[(PaymentMethod.CASH, 100)],
                         session=s, change_given=0)
        result = compute_expected_cash(db, s)
        assert result.expected == Decimal("300")


# ── Section E: Closing balance & difference (cases 17-18) ────────────────────


class TestClosingBalanceDifference:
    """Cases 17-18: surplus vs shortage."""

    def _close_and_get_diff(self, db, session, closing):
        """Mimic _apply_close_to_session math without the HTTP layer."""
        breakdown = compute_expected_cash(db, session)
        return Decimal(str(closing)) - breakdown.expected

    # Case 17: closing > expected → positive difference (sobrante)
    def test_closing_above_expected_is_surplus(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=100)
        _create_sale(db, cajero_a, branch_a, total=50,
                     payments=[(PaymentMethod.CASH, 50)],
                     session=s, change_given=0)
        diff = self._close_and_get_diff(db, s, Decimal("160"))  # expected 150
        assert diff == Decimal("10")

    # Case 18: closing < expected → negative difference (faltante)
    def test_closing_below_expected_is_shortage(self, db, cajero_a, branch_a):
        s = _open_session(db, cajero_a, branch_a, opening=100)
        _create_sale(db, cajero_a, branch_a, total=50,
                     payments=[(PaymentMethod.CASH, 50)],
                     session=s, change_given=0)
        diff = self._close_and_get_diff(db, s, Decimal("140"))  # expected 150
        assert diff == Decimal("-10")
