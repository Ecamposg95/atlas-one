# Runbook — Cash Session Repair

**Use when**: a session has bad data (inflated refund, wrong difference, etc.) and you need to surgically fix it without rebuilding the whole month.

**Prerequisite**: read `cash-discrepancy-debugging.md` first to confirm the diagnosis.

---

## Tools

| Script | Purpose | Side-effects |
|---|---|---|
| `scripts/audit_cash_anomalies.py` | Scan all closed sessions; report which ones tripped F2 warnings | Read-only |
| `scripts/recompute_session_differences.py` | Re-run `compute_expected_cash` on closed sessions; update persisted `difference` | Updates `cash_sessions.difference` (preserves `closing_balance`); appends `[RECALCULADO]` tag to `notes` |
| `scripts/repair_inflated_refund.py` | Reverse a single inflated/duplicated refund (deletes CashMovement OUT, reverts SaleReturn to REJECTED, restores stock + sale.status, leaves audit row) | Mutates: `cash_movements`, `sale_returns`, `sales_documents`, `stock_on_hand`, `inventory_movements`, `cash_audit_log` |

All scripts default to **dry-run**. Pass `--apply` to persist.

**Where to run (production, VPS IONOS since 2026-09-22):** the scripts ship inside the
image, so run them in the app container — the commands below are shown bare for brevity:

```bash
ssh ionos 'docker exec -w /app -e PYTHONPATH=/app atlas-one-prod python scripts/audit_cash_anomalies.py --since 2026-04-01'
```

SQL goes through the shared Postgres container:
`ssh -t ionos 'docker exec -it postgres psql -U postgres atlas_one_prod'`.

---

## Scenarios

### A. "Found a single inflated refund" (e.g. session 65)

Step 1 — confirm in `/platform/cash-audit/{session_id}`. Note the `cash_movements.id` of the offending OUT row.

Step 2 — dry-run:
```bash
python scripts/repair_inflated_refund.py --movement-id 7849
```
Output shows the SaleReturn, sale, items it would touch.

Step 3 — apply:
```bash
python scripts/repair_inflated_refund.py --movement-id 7849 --apply \
  --operator-id 12 --note "kimberly reportó refund duplicado por outage 2026-05-01"
```

Step 4 — refresh the persisted difference:
```bash
python scripts/recompute_session_differences.py --session-id 65 --apply
```

Step 5 — verify in UI: `/platform/cash-audit/65` should now show clean breakdown + a new `REFUND_REJECTED` event in the timeline tagged `[ADMIN-FIX]`.

### B. "Bulk recompute differences after a formula fix"

Whenever `compute_expected_cash` changes (e.g. the 640fbe9 REFUNDED_* fix), persisted `difference` values become stale.

```bash
# Dry-run first — shows what would change
python scripts/recompute_session_differences.py --since 2026-04-01

# Apply
python scripts/recompute_session_differences.py --since 2026-04-01 --apply
```

The script preserves `closing_balance` (what the cashier counted) and only updates `difference`. Original `notes` is appended with `[RECALCULADO YYYY-MM-DD] old_diff=X new_diff=Y`.

### C. "Find all anomalies across the whole month"

```bash
python scripts/audit_cash_anomalies.py --since 2026-04-01 > /tmp/anomalies.md
```

Output is markdown — open in any viewer. Each row is one warning. Group by `code`:
- Many `REFUNDS_EXCEED_TODAY_CASH` → check for cross-day refund pattern (legit) or systemic over-refunds (problem).
- Any `CHANGE_EXCEEDS_GROSS_CASH` → critical, individual investigation per session.
- Many `LARGE_DIFFERENCE_RATIO` → could be cashier discipline issue.

Filter:
```bash
python scripts/audit_cash_anomalies.py --severity critical
python scripts/audit_cash_anomalies.py --org-id 3 --since 2026-04-01
```

### D. "Discovered a session with NULL session_id sales not being counted"

This is normally legitimate (legacy fallback). If it persists for new sales, it's a bug in `create_sale` not setting `cash_session_id`. File a github issue. As a one-off, manually update:
```sql
UPDATE sales_documents
SET cash_session_id = {session_id}
WHERE cash_session_id IS NULL
  AND seller_id = {user_id}
  AND branch_id = {branch_id}
  AND created_at BETWEEN {opened_at} AND {closed_at};
```
Then `recompute_session_differences.py --session-id X --apply`.

---

## Safety checklist before --apply

- [ ] Confirmed the diagnosis in `/platform/cash-audit/{session_id}` first
- [ ] Ran dry-run and the output matches what you expected
- [ ] You have `operator-id` and `note` ready (audit trail)
- [ ] Backup taken before `--apply`: `ssh ionos 'docker exec postgres pg_dump -U postgres atlas_one_prod | gzip > /srv/backups/atlas_one_prod_antes_de_<qué>_<fecha>.sql.gz'` (Railway snapshots no longer apply; the nightly 03:30 dump may be hours old)
- [ ] Notified the cashier/branch manager of what you're about to fix

## Audit trail expectations

After any repair, these rows must exist:

1. `cash_audit_log.event_type = 'REFUND_REJECTED'` with `payload.tag = '[ADMIN-FIX]'`
2. `inventory_movements.reference = 'REPAIR_REFUND:{return_id}'` (if items were inventory_reentry)
3. `cash_sessions.notes` ends with `[RECALCULADO ...]`

If any of those are missing, the fix was incomplete. Investigate before declaring done.

## Related

- Spec: `docs/superpowers/specs/cash-reconciliation-spec.md`
- Debug: `docs/superpowers/runbooks/cash-discrepancy-debugging.md`
- Outage: `docs/superpowers/audits/2026-05-01-cash-mapper-outage-audit.md`
