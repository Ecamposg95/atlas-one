# Runbook — Cajero Pack Stable (2026-04-30)

> **HISTÓRICO — no ejecutar los rollbacks de este archivo.** Describe el esquema de abril
> de 2026: ramas `release/qa`, `release/beta`, `release/production` con autodeploy de
> Railway. Nada de eso existe ya (comprobado el 2026-11-18: ni esas ramas ni los tags
> `v2026.04.30-cajero-stable` / `milestone-2026.04.30` están en el remoto). Producción es
> `main` → VPS IONOS y el rollback vigente está en [`docs/DEPLOY.md §4`](../../DEPLOY.md).
> El **catálogo de síntomas** (422 en ventas, 409 de caja, 410 de tickets en espera, logo
> del ticket) sigue siendo útil como guía de diagnóstico; las consultas SQL se corren
> contra `atlas_one_prod` en el VPS.

**Tags**:
- `v2026.04.30-cajero-stable` → `a79d9393` (feature anchor)
- `milestone-2026.04.30` → `a79d9393` (multi-branch alignment hito)

**All four branches aligned at `a79d9393`**: `release/qa`, `release/beta`, `release/production`, `main`.

**Pre-deploy tip (rollback target for any branch)**: `fc6df18`

Symptom-driven mitigations for the cajero pack release. Read top to bottom; the first matching symptom wins.

---

## SEV-1 — full rollback (POS unusable, sales failing for everyone)

Roll back the affected environment first (production OR beta), THEN evaluate whether qa needs to follow:

**Production hot-rollback** (real customers down):
```bash
git checkout release/production
git pull --ff-only origin release/production
git reset --hard fc6df18
git push --force-with-lease origin release/production
```

**Beta hot-rollback** (cashier QA unblocked):
```bash
git checkout release/beta
git pull --ff-only origin release/beta
git reset --hard fc6df18
git push --force-with-lease origin release/beta
```

Railway autodeploys the previous code in ~5 min per environment. The new DB columns (`sales_documents.global_discount_pct`, `parked_tickets.status`, `parked_tickets.converted_to_sale_id`) stay; the old code ignores them and the defaults are pre-feature behavior.

After rollback, leave the changes on `release/qa` for diagnosis. Don't delete the tags `v2026.04.30-cajero-stable` and `milestone-2026.04.30` — they're our forensic anchors. `main` can stay at `a79d9393` (no deploy hook).

---

## SEV-2 — partial revert (one feature broken, rest fine)

The release lands as several independent commits. Find the offending commit and revert just that one on a hotfix branch.

```bash
git log --oneline release/beta | head -10
# pick the SHA to revert
git checkout release/beta
git checkout -b hotfix/revert-<SHA-short>
git revert <SHA>
git push -u origin hotfix/revert-<SHA-short>
# … merge to qa, then FF beta
```

Key revertible commits:

| Symptom | Commit | What it carries |
|---|---|---|
| Tickets misformatted on hardware | `817c211` + `ffd1ce1` | OXXO compact + 56-col + manual-center logo |
| POS price popover broken | `aad4dca`, `0354e2b`, `f2bd666` | Popover + readability fixes |
| Sales failing 422 unexpectedly | `c7cd419` (wave 1) | money trust validation |
| Frontend trust / popover scroll | `45d37a1` (wave 2) | global_discount_pct send + popover ancestors + state collapse |
| Branch-isolation issues | `c539ac1` (hotfix) | C-1..C-4 |
| Print agent download broken | `019137d` | print agent restructure |

---

## Symptom catalog

### "Cashier sees 422 on every sale"
**Likely**: H-1 server-side validation rejecting because `sum(payments.amount) < total`.
**Verify**: check API logs for `Pagos insuficientes: recibido X vs total Y`. Difference > $0.01?
**Mitigation**: if the discrepancy is ALL real-life rounding (e.g. cents the cashier entered loosely), bump tolerance in `app/routers/sales.py` (search for `tolerance = Decimal("0.01")`) to `0.05` and redeploy. Don't disable the check.
**Root cause to investigate**: frontend rounding pipeline — likely a Decimal-vs-float coercion when computing `sum(items.subtotal)` client-side.

### "Cashier sees 409 'Debes abrir caja' but they have a session open"
**Likely**: H-5 enforcement is correct; their session is in a different branch or they're querying the wrong `branch_id`.
**Verify**:
```sql
SELECT id, branch_id, user_id, status, opened_at
FROM cash_sessions
WHERE user_id = <user_id> AND status = 'OPEN';
```
If the session's `branch_id` doesn't match `users.branch_id`, that's pre-existing data drift.
**Mitigation**: as superadmin, force-close the misaligned session, have the cashier re-open at their actual branch.

### "Cashier sees 410 Gone when reanudar a ticket"
**Likely**: M-3 — the parked ticket is `CONVERTED` (already used to make a sale).
**Verify**:
```sql
SELECT id, status, converted_to_sale_id FROM parked_tickets WHERE id = '<id>';
```
**Mitigation**: if the conversion was an accident (cashier double-clicked Cobrar), find the resulting sale and either `DELETE` it (cash session reconciliation will recover) or refund. Then `UPDATE parked_tickets SET status='ACTIVE', converted_to_sale_id=NULL WHERE id='<id>'` to allow re-resume. Document why in #ops Slack.

### "Cashier can't close session — 409 with N parked tickets"
**Likely**: H-7 — they have un-converted parked tickets pending.
**Verify** in API response or:
```sql
SELECT id, expires_at FROM parked_tickets
WHERE user_id = <user_id> AND deleted_at IS NULL
  AND status = 'ACTIVE'
  AND created_at >= '<session.opened_at>'::timestamp;
```
**Mitigation**: cashier resumes/sells/discards each parked ticket, then closes. If the cashier can't (left, sick, etc.) a GERENTE can soft-delete: `UPDATE parked_tickets SET deleted_at = now(), status='ARCHIVED' WHERE id IN (...)` then close.

### "Returns approval double-credits inventory or cash"
**Likely**: H-4 race never triggered because of the `SELECT FOR UPDATE` lock. If you DO see this, something serialized incorrectly.
**Verify**: check if the duplicate inventory movement has the same `return_id` referenced.
**Mitigation**: manually reverse the duplicate `InventoryMovement` and `CashMovement` rows. Investigate why the lock didn't hold (possible Postgres replica lag if reads went to a replica).

### "Tax/finance reports show inflated tax for sales that had returns"
**Likely**: M-2 fix didn't fire. Most reports query `SUM(sales_documents.tax_amount)`.
**Verify**: pick a sale with a known return, query `SELECT subtotal, tax_amount, total_amount FROM sales_documents WHERE id = '<id>'`. Compare against printed ticket — if the printed values are the net but the DB still shows pre-return, the DB recompute didn't run.
**Mitigation**: re-run the recompute manually for affected period:
```sql
-- Find sales with approved returns since 2026-04-30
WITH r AS (
  SELECT sale_id, SUM(refund_amount) AS total_refund
  FROM sale_return_items sri
  JOIN sale_returns sr ON sr.id = sri.sale_return_id
  WHERE sr.status = 'APPROVED' AND sr.approved_at >= '2026-04-30'
  GROUP BY sale_id
)
SELECT sd.id, sd.subtotal, sd.tax_amount, r.total_refund
FROM sales_documents sd JOIN r ON r.sale_id = sd.id;
```
If recompute didn't apply, run it manually per row or open a fix ticket.

### "Tickets imprimen sin logo de pronto" (post-hotfix `adc9e002`)
**Likely**: the new size+ctype cap on `_generate_image_bytes` is rejecting the configured logo URL — too large (>5 MB), wrong Content-Type, or 5s timeout.
**Verify**: tail backend logs for `logo rejected:` or `logo fetch/open failed`. The reject-reason is logged with the URL.
**Mitigation**: if the URL is legitimately large (e.g. 8 MP master file), have the admin replace it with a CDN-resized version (Cloudinary `c_limit,w_500` transformation, ~50 KB). If the timeout is the issue, raise `_LOGO_FETCH_TIMEOUT` from 5 s to 8 s in `app/pos_printer.py` — but consider that as a step backwards (slow tickets).

### "Logo prints flush-left instead of centered"
**Likely**: the printer-side bitmap padding isn't honored by this particular hardware. Most cheap thermals respect `GS v 0` after `ESC a 1`, but a few generic clones treat raster as left-aligned regardless.
**Verify**: print on a different thermal; if both fail, it's a code bug; if one works, hardware quirk.
**Mitigation**: as a hardware workaround, the bitmap is already left-padded to fill the full paper width with empty pixels — this should work even on raster-ignorers. If it doesn't, investigate `_generate_image_bytes` paper_dots calculation; verify `PAPER_DOTS_80MM = 576` matches the actual printer's printable width (some 80mm units have 512 instead).

### "Frontend shows 'Ticket guardado pero no se pudo imprimir'"
**Likely**: print agent offline on the cashier's PC. This is a new toast (L-3) that surfaces a previously-silent error.
**Mitigation**: cashier opens the agent (`impresora_win.bat` / `impresora_linux.sh`), then clicks "Reimprimir" on the sale. Sale itself is safe and persisted.

### "Popover shows but text leaks through"
**Likely**: dark mode token regression — `--dax-card-solid` not loaded yet or overridden.
**Verify**: inspect computed style on `.PricePickerPopover` — `background` should resolve to a fully opaque value.
**Mitigation**: hard-code background in the inline `style` of the popover root (just in case the variable isn't available globally).

### "Build canceled / context canceled on Railway"
**Cause**: not the code — Railway side. Builder timeout, queue saturation, or a parallel deploy preempted the build.
**Mitigation**: Redeploy from Railway dashboard. If consistently failing, the repo has 76 MB less binary content as of `184f48b`, so each clone is faster. If still failing → check Railway plan limits.

---

## Quick-glance state of the deployed code

```
release/qa          adc9e002   (cajero stable + image-url Day-1 hotfix)
release/beta        adc9e002
release/production  adc9e002
main                adc9e002

tag: v2026.04.30-cajero-stable  → a79d9393  (feature anchor — pre-hotfix)
tag: milestone-2026.04.30       → a79d9393  (multi-branch alignment hito)
prior stable tag:                 v2026.04.29-cashier-pack → e55921c
pre-promotion tip:                fc6df18  (2026-04-29 — pre-cashier-pack push)

Hotfix on top of the milestone tag:
  adc9e002  fix(printer): hotfix operational — Pillow bomb cap + size cap + ctype
            (closes audit findings H-2 / H-3 / M-1 / L-2 in
             docs/superpowers/audits/2026-04-30-image-url-audit.md)
```

If you need to know what shipped between `fc6df18` and `45d37a12`:

```bash
git log --oneline fc6df18..45d37a12
```

---

## Health probes worth wiring (future work)

These would catch the issues this release introduces before a customer notices:

1. **Sales 422 rate** — alert if `> 1 % of POST /api/sales return 422`. Today's release adds new 422 paths.
2. **`/api/health` ticks** — already exists; ensure it responds < 200 ms after deploy.
3. **`payments` orphan count** — was cleaned up by the cashier pack migrator. A regression would re-introduce orphans; alert if `SELECT count(*) FROM payments WHERE sales_document_id IS NULL > 0`.
4. **Stale parked tickets** — count `WHERE status='ACTIVE' AND created_at < now() - interval '24 hours'`. If it grows, cashiers are forgetting to close.

Wire these through Grafana / whatever observability stack beta uses.
