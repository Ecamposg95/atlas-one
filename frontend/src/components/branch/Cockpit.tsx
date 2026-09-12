import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { BRANCH_COPY } from '../../copy/branchCopy'
import { getBranchDashboard } from '../../api/branchDashboard'
import type { BranchDashboard } from '../../types/branchDashboard'
import { ui } from './branchUI'
import { CockpitGreeting } from './CockpitGreeting'
import { CockpitDayKPIs } from './CockpitDayKPIs'
import { CockpitAlerts } from './CockpitAlerts'
import { CockpitQuickAccess } from './CockpitQuickAccess'

export function Cockpit() {
  const [data, setData] = useState<BranchDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadDashboard = useCallback(async () => {
    try {
      const d = await getBranchDashboard()
      setData(d)
    } catch {
      setError(BRANCH_COPY.cockpit.error)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setError(null)
    getBranchDashboard()
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError(BRANCH_COPY.cockpit.error) })
    return () => { cancelled = true }
  }, [])

  if (error) {
    return (
      <div className={`min-h-screen ${ui.page} flex items-center justify-center`}>
        <p className="p-6 text-rose-600 dark:text-rose-400 text-sm">{error}</p>
      </div>
    )
  }
  if (!data) {
    return (
      <div className={`min-h-screen ${ui.page} flex items-center justify-center`}>
        <p className="p-6 text-slate-400 dark:text-slate-600 text-sm">{BRANCH_COPY.states.loading}</p>
      </div>
    )
  }

  return (
    <div className={`min-h-screen ${ui.page}`}>
      <div className={`${ui.container} py-4 lg:py-5 space-y-4`}>

        {/* Row 1 — Hero full-width: Greeting + CTA */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-12">
            <CockpitGreeting
              user={data.user}
              shift={data.shift}
              onShiftOpened={() => { loadDashboard() }}
            />
          </div>
        </div>

        {/* Row 2 — KPI columns: Hero sales | Secondary KPIs | Top products */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-5 anim-cascade" style={{ '--i': 1 } as CSSProperties}>
            <CockpitDayKPIs.HeroSales today={data.today} />
          </div>
          <div className="lg:col-span-3 anim-cascade" style={{ '--i': 2 } as CSSProperties}>
            <CockpitDayKPIs.SecondaryKPIs today={data.today} />
          </div>
          <div className="lg:col-span-4 anim-cascade" style={{ '--i': 3 } as CSSProperties}>
            <CockpitDayKPIs.TopProducts today={data.today} />
          </div>
        </div>

        {/* Row 3 — Payment methods | Alerts */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-7 anim-cascade" style={{ '--i': 4 } as CSSProperties}>
            <CockpitDayKPIs.PaymentMethods today={data.today} />
          </div>
          <div className="lg:col-span-5 anim-cascade" style={{ '--i': 5 } as CSSProperties}>
            <CockpitAlerts alerts={data.alerts} />
          </div>
        </div>

        {/* Row 4 — Quick access (full width) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-12 anim-cascade" style={{ '--i': 6 } as CSSProperties}>
            <CockpitQuickAccess />
          </div>
        </div>

        {/* Closing wizard removed from cockpit — accessible via POS top header (Cerrar turno) and Mi caja */}

      </div>
    </div>
  )
}
