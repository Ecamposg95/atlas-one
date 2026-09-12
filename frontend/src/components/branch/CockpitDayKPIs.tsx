import { BRANCH_COPY, PAY_METHOD_LABELS } from '../../copy/branchCopy'
import { ui, brand, fmtMoney } from './branchUI'
import { useCountUp } from '../../hooks/useCountUp'
import type { DashboardToday } from '../../types/branchDashboard'

interface TodayProps { today: DashboardToday }

/** Col-span-5: large sales total + ticket count + inline goal bar */
function HeroSales({ today }: TodayProps) {
  const salesTotal = useCountUp(Number(today.sales_total ?? 0))
  const goalPct = today.goal_progress_pct ?? null
  // Goal bar: purple fill (brand) for ≥80%, amber for mid, rose for low
  const barColor =
    goalPct == null ? 'bg-slate-300 dark:bg-slate-600' :
    goalPct < 50    ? 'bg-rose-500'    :
    goalPct < 80    ? 'bg-amber-500'   : 'bg-purple-500'

  return (
    <div className={`${ui.card} p-6 h-full flex flex-col justify-between`}>
      <div>
        <p className={`${ui.kpiLabel} mb-1`}>{BRANCH_COPY.cockpit.salesToday}</p>
        <p className={`${ui.kpiHero} text-emerald-500 dark:text-emerald-400`}>
          {fmtMoney(salesTotal)}
        </p>
        <p className={`mt-2 text-sm ${ui.muted}`}>
          {BRANCH_COPY.cockpit.salesTickets(today.sales_count)}
        </p>
      </div>

      {today.goal != null && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-1.5">
            <p className={ui.kpiLabel}>{BRANCH_COPY.cockpit.goalLabel}</p>
            <span className="text-sm font-bold tabular-nums text-slate-700 dark:text-slate-200">
              {goalPct ?? 0}%
            </span>
          </div>
          <div className="h-2 bg-stone-100 dark:bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${barColor}`}
              style={{ width: `${Math.min(100, goalPct ?? 0)}%` }}
            />
          </div>
          <p className={`mt-1 text-xs ${ui.muted}`}>
            {BRANCH_COPY.cockpit.goalOf(fmtMoney(today.goal))}
          </p>
        </div>
      )}
    </div>
  )
}

/** Col-span-3: ticket promedio */
function SecondaryKPIs({ today }: TodayProps) {
  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Ticket promedio */}
      <div className={`${ui.card} p-5 flex-1 flex flex-col justify-center`}>
        <div className="flex items-center gap-1.5 mb-1">
          <i className="fa-solid fa-receipt text-purple-400 dark:text-purple-500 text-[10px]" aria-hidden="true" />
          <p className={ui.kpiLabel}>{BRANCH_COPY.cockpit.avgTicket}</p>
        </div>
        <p className="text-2xl font-extrabold tabular-nums tracking-tight text-slate-900 dark:text-slate-100 mt-0.5">
          {fmtMoney(today.avg_ticket)}
        </p>
      </div>
    </div>
  )
}

/** Col-span-4: top products list (max 5 rows) */
function TopProducts({ today }: TodayProps) {
  const topProds = (today.top_products ?? []).slice(0, 5)

  return (
    <div className={`${ui.card} p-5 h-full flex flex-col`}>
      <div className="flex items-center gap-1.5 mb-3">
        <i className="fa-solid fa-trophy text-amber-400 text-[10px]" aria-hidden="true" />
        <p className={ui.kpiLabel}>{BRANCH_COPY.cockpit.topProducts}</p>
      </div>

      {topProds.length === 0 ? (
        <p className={`text-sm italic ${ui.muted}`}>{BRANCH_COPY.states.empty}</p>
      ) : (
        <ol className={`${ui.divider} flex-1`}>
          {topProds.map((p, i) => (
            <li key={i} className="flex items-center justify-between gap-2 py-2.5">
              <span className="text-sm text-slate-600 dark:text-slate-400 truncate flex-1">
                {p.name}
              </span>
              <span className={`text-sm font-bold tabular-nums ${brand.purpleText} flex-shrink-0`}>
                {Number(p.units).toFixed(0)} u
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

const FIXED_METHODS = [
  { key: 'CASH',     icon: 'fa-money-bill-wave',  iconBg: 'rgba(16,185,129,0.1)',  iconColor: '#10b981' },
  { key: 'CARD',     icon: 'fa-credit-card',      iconBg: 'rgba(139,92,246,0.1)', iconColor: '#a78bfa' },
  { key: 'TRANSFER', icon: 'fa-building-columns', iconBg: 'rgba(59,130,246,0.1)', iconColor: '#60a5fa' },
] as const

function PaymentMethods({ today }: TodayProps) {
  const payMethods = today.payment_methods ?? {}

  return (
    <div className={`${ui.card} p-5`}>
      <p className={`${ui.kpiLabel} mb-4`}>{BRANCH_COPY.cockpit.paymentMethods}</p>
      <div className="grid grid-cols-3 gap-3">
        {FIXED_METHODS.map(({ key, icon, iconBg, iconColor }) => {
          const amount = Number(payMethods[key] ?? 0)
          return (
            <div
              key={key}
              className="flex items-center gap-3 rounded-xl px-4 py-3"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
            >
              <div
                className="flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0"
                style={{ background: iconBg }}
              >
                <i className={`fa-solid ${icon} text-sm`} style={{ color: iconColor }} />
              </div>
              <div className="min-w-0">
                <p className={`text-[10px] font-semibold uppercase tracking-wider ${ui.muted}`}>
                  {PAY_METHOD_LABELS[key] ?? key}
                </p>
                <p className="text-sm font-bold tabular-nums text-slate-800 dark:text-slate-100 mt-0.5">
                  {fmtMoney(amount)}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Barrel — Cockpit.tsx imports CockpitDayKPIs.HeroSales etc. */
export const CockpitDayKPIs = {
  HeroSales,
  SecondaryKPIs,
  TopProducts,
  PaymentMethods,
}
