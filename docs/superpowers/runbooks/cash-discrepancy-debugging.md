# Runbook — Cash Discrepancy Debugging

**Use when**: a cashier/admin reports "el corte no cuadra" or "el ESPERADO sale negativo".

**Time budget**: 5-10 minutes from open to root cause.

---

## Step 1 — Open the Cash Audit UI

Navigate to `/platform/cash-audit/{session_id}`. Login as ADMINISTRADOR / DUEÑO / GERENTE.

If you don't have the session_id, ask the cashier or query:
```sql
SELECT cs.id, cs.opening_balance, cs.closing_balance, cs.difference, u.username, b.name
FROM cash_sessions cs JOIN users u ON u.id=cs.user_id JOIN branches b ON b.id=cs.branch_id
WHERE u.username = 'kimberly' AND cs.opened_at::date = '2026-05-01'
ORDER BY cs.opened_at DESC;
```

## Step 2 — Read the BREAKDOWN MATEMÁTICO card

The card shows the full formula line by line. **Find the line that doesn't match physical reality**:

| Symptom | Likely cause | Drill-down |
|---|---|---|
| `Reembolsos efectivo` is huge (>50% of cash) | Inflated refund OR cross-day refunds OR duplicate refund movement | Step 3a |
| `Ventas efectivo` is much lower than expected | Many sales with `cash_session_id` mis-assigned, or status filter issue | Step 3b |
| `Fondo inicial` is $0 but cashier had a starting fund | Session was opened without registering opening_balance | Step 3c |
| `DIFERENCIA` huge but breakdown all looks OK | Cashier counted wrong, or cash physically missing | Recount |
| `ESPERADO` is negative | refunds_out > opening + cash_in (legitimate cross-day OR a single inflated refund) | Step 3a |

## Step 3a — Inflated refund investigation

In the Cash Audit UI, scroll the TIMELINE looking for `REFUND_APPROVED` events. Sort by amount mentally:

- **One big refund stands out**: click it. Payload shows `sale_id`, `refund_method`, `force_used`, `supervisor_id`. If `force_used=true`, the supervisor explicitly overrode the fat-finger guard — confirm with them.
- **Multiple refunds same minute/amount**: possible duplicate from the cajero retrying after a 500. Cross-check with `payment-methods` outage logs.
- **Refunds for sales NOT in this session's timeline**: cross-day refund. Legitimate, but explains the negative `ESPERADO`. Recommend reposición.

**To get the SaleReturn details**:
```sql
SELECT sr.id, sr.sale_id, sr.total_refunded, sr.refund_method, sr.status,
       sr.created_at, sd.series||'-'||sd.folio AS folio,
       sd.total_amount AS sale_total_now, sd.created_at AS sale_at
FROM sale_returns sr
JOIN sales_documents sd ON sd.id = sr.sale_id
WHERE sr.id = '...uuid del REFUND_APPROVED.related_id...';
```

## Step 3b — Sales mis-assigned

Verify the sales attached to this session:
```sql
SELECT id, series||'-'||folio AS folio, status, total_amount, change_given,
       cash_session_id, created_at
FROM sales_documents
WHERE cash_session_id = {session_id}
   OR (cash_session_id IS NULL AND seller_id = {user_id}
       AND branch_id = {branch_id}
       AND created_at BETWEEN {opened_at} AND {closed_at})
ORDER BY created_at;
```

If you see status REFUNDED_* sales with `change_given` populated weirdly (>total_amount) → corrupted change_given (W2 warning). Open the sale's payments to verify.

## Step 3c — Opening balance issue

```sql
SELECT id, opening_balance, opened_at, status
FROM cash_sessions WHERE id = {session_id};
```

If `opening_balance = 0` but the cashier reports having a starting fund: either the cashier opened the session wrong (UI bug or misclick), or this is a legitimate $0 start. No fix from backend; document for cashier training.

## Step 4 — Decide action

| Finding | Action |
|---|---|
| Legitimate cross-day refund | Document in audit notes. Recommend org policy: refunds cross-day require manager pre-approval. |
| Inflated refund (fat-finger) | Use `scripts/repair_inflated_refund.py` (see `cash-session-repair.md`, scenario A). Manual fallback: reject SaleReturn, delete CashMovement OUT, recompute difference. |
| Duplicate refund movement | Delete the duplicate `cash_movements` row, recompute. |
| Cashier counted wrong | No code change. Rerun `scripts/recompute_session_differences.py --session-id X --apply` after manual recount + closing_balance update. |
| Pre-fix sessions (before commit `640fbe9`) | Bulk run `scripts/recompute_session_differences.py --since 2026-04-01 --apply` to recompute all `difference` values with current formula. |

## Step 5 — Close the loop

- If you fixed data: insert a manual `cash_audit_log` row noting what you changed (event_type=`MANUAL_INFLOW` with reason `"[ADMIN-FIX] Reconciliación manual: ..."`).
- If you found a code bug: open a github issue + add a regression test in `tests/test_cash_*.py`.
- If you found a process gap (e.g. cashier opened session wrong): flag for the operations team.

## Common rationalizations to AVOID

| Excuse | Reality |
|---|---|
| "Lo cierro con $0 y ya" | Borra evidencia. Investigar primero, ajustar después con audit trail. |
| "El sistema está mal, contó mi cajón bien" | El sistema lee Payment + CashMovement rows. Si dicen X, esa es la realidad de software. La discrepancia es real — encuentra dónde. |
| "Es solo $50, dejémoslo así" | $50 hoy, $500 mañana, nadie sabe el patrón. Cada diff != 0 audita. |

## Related docs

- Spec: `docs/superpowers/specs/cash-reconciliation-spec.md`
- Outage report: `docs/superpowers/audits/2026-05-01-cash-mapper-outage-audit.md`
- Audit script: `scripts/audit_outage_2026_05_01.sql`
