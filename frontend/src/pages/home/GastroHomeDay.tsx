import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { reportsApi, DashboardData } from '../../api/reports'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { BarChart, Sparkline } from '../../components/atlas-one'

/**
 * Home del día — presets gastro (Restaurant / Café / Bar). Cablea datos reales
 * de reportsApi.dashboard del día y los muestra con el idioma OSCURO del app
 * (dax-card + slate/white) para ser coherente con el shell. Los accesos rápidos
 * siguen visibles aunque el reporte falle.
 */

export interface QuickAction {
  icon: string
  label: string
  to: string
  beta?: boolean
}

export interface GastroHomeConfig {
  greeting: string
  orgName: string
  title: string
  subtitle: string
  accent: string
  topLabel: string          // "Platillos top" / "Bebidas top" / "Productos top"
  actions: QuickAction[]
}

const money = (n: number) =>
  new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(n || 0)

function todayISO(): string {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

function growthDelta(curr: number, prev?: number): string | undefined {
  if (prev == null || prev === 0) return undefined
  const pct = ((curr - prev) / prev) * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}%`
}

function Delta({ v }: { v?: string }) {
  if (!v) return null
  const up = v.startsWith('+')
  return (
    <span className={`text-xs font-bold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
      <i className={`fa-solid ${up ? 'fa-arrow-trend-up' : 'fa-arrow-trend-down'} mr-1`} />{v}
    </span>
  )
}

export function GastroHomeDay({ greeting, orgName, title, subtitle, accent, topLabel, actions }: GastroHomeConfig) {
  const { branch } = useAuthStore()
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    const day = todayISO()
    setLoading(true)
    setFailed(false)
    reportsApi
      .dashboard({ start_date: day, end_date: day, branch_id: branch?.id })
      .then((d) => { if (alive) setData(d) })
      .catch(() => { if (alive) setFailed(true) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [branch?.id])

  const k = data?.kpis
  const hourly = data?.charts?.hourly?.data ?? []
  const topProducts = (data?.top_products ?? []).slice(0, 5)
  const peakHour = (() => {
    const h = data?.charts?.hourly
    if (!h?.data?.length) return null
    let bestI = 0
    h.data.forEach((v, i) => { if (v > h.data[bestI]) bestI = i })
    return h.labels?.[bestI] ?? null
  })()

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500 font-semibold">
            {orgName} · {title}
          </p>
          <h1 className="text-2xl font-black text-white mt-1">
            {greeting ? `Hola, ${greeting}` : 'Bienvenido'}
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>
        </div>
        <span
          className="text-[11px] font-bold uppercase tracking-wide px-3 py-1.5 rounded-full whitespace-nowrap"
          style={{ background: `${accent}22`, color: accent }}
        >
          Hoy · {todayISO()}
        </span>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {loading ? (
          [0, 1, 2, 3].map((i) => (
            <DaxCard key={i}><div className="h-16 animate-pulse opacity-40 text-xs text-slate-500">Cargando…</div></DaxCard>
          ))
        ) : (
          <>
            <DaxCard>
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Ventas del día</p>
              <div className="flex items-end justify-between gap-2 mt-1">
                <p className="text-2xl font-black text-white tabular-nums">{money(k?.sales ?? 0)}</p>
                {hourly.length > 1 && <Sparkline values={hourly} color={accent} width={62} height={26} fill />}
              </div>
              <div className="mt-1"><Delta v={growthDelta(k?.sales ?? 0, k?.prev_sales)} /></div>
            </DaxCard>
            <DaxCard>
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Órdenes</p>
              <p className="text-2xl font-black text-white tabular-nums mt-1">{k?.orders ?? 0}</p>
              <div className="mt-1"><Delta v={growthDelta(k?.orders ?? 0, k?.prev_orders)} /></div>
            </DaxCard>
            <DaxCard>
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Ticket promedio</p>
              <p className="text-2xl font-black text-white tabular-nums mt-1">{money(k?.avg_ticket ?? 0)}</p>
              <div className="mt-1"><Delta v={growthDelta(k?.avg_ticket ?? 0, k?.prev_avg_ticket)} /></div>
            </DaxCard>
            <DaxCard>
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Cuentas abiertas</p>
              <p className="text-2xl font-black text-white tabular-nums mt-1">{k?.pending ?? 0}</p>
              {peakHour != null && <p className="text-[11px] text-slate-500 mt-1">Hora pico {peakHour}</p>}
            </DaxCard>
          </>
        )}
      </div>

      {failed && (
        <DaxCard>
          <p className="text-sm text-slate-300">
            No pudimos cargar los datos del día. Los accesos rápidos siguen disponibles abajo.
          </p>
        </DaxCard>
      )}

      {/* Charts */}
      {!failed && (
        <div className="grid gap-3 lg:grid-cols-3">
          <DaxCard className="lg:col-span-2">
            <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-3">{topLabel} de hoy</p>
            {topProducts.length ? (
              <div className="overflow-x-auto">
                <BarChart
                  width={620} height={200} color={accent} soft="rgba(148,163,184,0.22)"
                  data={topProducts.map((p, i) => ({
                    label: p.name.length > 10 ? p.name.slice(0, 9) + '…' : p.name,
                    value: p.qty,
                    highlight: i === 0,
                  }))}
                />
              </div>
            ) : (
              <p className="text-sm text-slate-500 py-8">Aún sin ventas hoy 🍽️</p>
            )}
          </DaxCard>

          <DaxCard className="flex flex-col">
            <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-3">Ritmo del día</p>
            {hourly.some((v) => v > 0) ? (
              <>
                <Sparkline values={hourly} color={accent} width={280} height={100} fill />
                <p className="mt-auto pt-3 text-xs text-slate-400">
                  {peakHour != null ? <>Hora pico: <strong className="text-white">{peakHour}</strong></> : 'Sin actividad'}
                </p>
              </>
            ) : (
              <p className="text-sm text-slate-500 py-8">Sin actividad todavía</p>
            )}
          </DaxCard>
        </div>
      )}

      {/* Quick actions */}
      <div>
        <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-3">Accesos rápidos</p>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {actions.map((a) => (
            <Link key={a.to} to={a.to} className="block">
              <DaxCard className="cursor-pointer h-full">
                <div className="flex flex-col items-center text-center gap-2">
                  <span
                    className="w-11 h-11 rounded-xl inline-flex items-center justify-center text-lg"
                    style={{ background: `${accent}22`, color: accent }}
                  >
                    <i className={`fa-solid ${a.icon}`} />
                  </span>
                  <span className="text-xs font-bold text-white leading-tight">{a.label}</span>
                  {a.beta && <span className="text-[8px] font-black uppercase tracking-wide text-amber-300">Beta</span>}
                </div>
              </DaxCard>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
