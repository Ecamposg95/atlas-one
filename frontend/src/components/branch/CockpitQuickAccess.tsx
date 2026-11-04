import { Link } from 'react-router-dom'
import { BRANCH_COPY } from '../../copy/branchCopy'
import { ui, brand } from './branchUI'
import { useAuthStore } from '../../store/authStore'
import { rolesConAcceso } from '../layout/navConfig'
import type { Role } from '../../types/auth'

const TILES = [
  { to: '/sales',            label: BRANCH_COPY.pages.sales,    icon: 'fa-solid fa-receipt' },
  { to: '/cash-history',     label: BRANCH_COPY.pages.cash,     icon: 'fa-solid fa-vault' },
  { to: '/returns',          label: BRANCH_COPY.pages.returns,  icon: 'fa-solid fa-rotate-left' },
  { to: '/products',         label: BRANCH_COPY.pages.products, icon: 'fa-solid fa-magnifying-glass' },
  { to: '/reports',          label: BRANCH_COPY.pages.reports,  icon: 'fa-solid fa-chart-bar' },
] as const

export function CockpitQuickAccess() {
  // Solo los accesos que el rol puede abrir: a la cajera "Reportes" la
  // regresaba a Mi día sin decir nada.
  const role = useAuthStore((s) => s.user?.role) as Role | undefined
  const tiles = TILES.filter((t) => !role || rolesConAcceso(t.to).includes(role))
  return (
    <div className={`${ui.card} p-6`}>
      <p className={`${ui.kpiLabel} mb-4`}>{BRANCH_COPY.cockpit.quickAccess}</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {tiles.map((t) => (
          <Link
            key={t.to}
            to={t.to}
            className={`
              ${ui.card}
              ring-1 ring-transparent hover:ring-purple-400 dark:hover:ring-purple-500
              flex flex-col items-center justify-center gap-2
              py-5 px-3
              text-center
              group
              transition-all duration-150
            `}
          >
            <i
              className={`${t.icon} text-xl ${brand.purpleText} group-hover:scale-110 transition-transform duration-150`}
              aria-hidden="true"
            />
            <span className="text-xs font-medium text-slate-600 dark:text-slate-400 group-hover:text-slate-900 dark:group-hover:text-slate-100 transition-colors leading-tight">
              {t.label}
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
