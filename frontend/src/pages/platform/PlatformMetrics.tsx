import { useCallback, useEffect, useMemo, useState, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip,
} from 'recharts'
import {
  platformApi,
  TopTenant,
  KpisExtendedResponse,
  TrendsMultiResponse,
  TopBranchRow,
  TopProductRow,
  CohortRow,
  HeatmapResponse,
  StatsRange,
  PaymentMethodsResponse,
  BranchComparisonResponse,
  PlatformOrg,
} from '../../api/platform'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'

import '../../styles/platform-v2.css'

import { KPICardV2 } from '../../components/platform/v2/KPICardV2'
import { Card } from '../../components/platform/v2/Card'
import { TrendChart, TrendPoint } from '../../components/platform/v2/TrendChart'
import { SkeletonState } from '../../components/platform/v2/SkeletonState'
import { Leaderboard } from '../../components/platform/v2/Leaderboard'

import { ActivityHeatmap } from '../../components/platform/v2/ActivityHeatmap'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'

import { OrgBoard } from './org/OrgBoard'
import { AttentionPanel } from './org/AttentionPanel'
import { useAttentionToday } from './org/useOrgOverview'
import { readMode, readOrgId, writeMode, writeOrgId } from './org/orgPrefs'
import type { PlatformMode } from '../../types/platformOverview'

// Lazy: cohort retention is the only chart left in "Análisis avanzado".
const CohortTable = lazy(() =>
  import('../../components/platform/v2/CohortTable').then(m => ({ default: m.CohortTable })),
)

// ── helpers ──────────────────────────────────────────────────────────────────

const RANGES: StatsRange[] = ['7d', '30d', '90d', 'ytd']

function fmtPct(v: number | null | undefined, decimals = 1): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(decimals)}%`
}

function deltaFraction(delta_pct: number | null): number | null {
  // Backend returns a percent already (e.g. 12.5 for +12.5%). KPICardV2 expects
  // a fraction (0.125). Convert.
  if (delta_pct == null) return null
  return delta_pct / 100
}

function asSpark(arr: number[] | undefined): { v: number }[] {
  if (!arr || arr.length === 0) return []
  return arr.map(v => ({ v }))
}

// Build TrendPoint[] usable by the existing TrendChart from multi-series points.
function multiToRevenueSeries(points: TrendsMultiResponse['points']): TrendPoint[] {
  if (!points || points.length === 0) return []
  // 7-day MA of revenue
  return points.map((p, idx) => {
    let ma: number | null = null
    if (idx >= 6) {
      const slice = points.slice(idx - 6, idx + 1)
      ma = slice.reduce((s, x) => s + x.revenue, 0) / 7
    }
    return {
      date: p.date,
      label: p.label,
      revenue: p.revenue,
      ma7: ma,
      sales: p.sales,
      signups: p.signups,
    }
  })
}

// ── BranchComparisonTable ────────────────────────────────────────────────────

interface BranchComparisonRowLike {
  branch_id: number
  branch_name: string
  org_id: number
  org_name: string
  revenue: number
  sales_count: number
  aov: number
  peak_hour: number | null
}

function BranchComparisonTable({
  rows,
  onRowClick,
}: {
  rows: BranchComparisonRowLike[]
  onRowClick?: (r: BranchComparisonRowLike) => void
}) {
  const maxRev = Math.max(...rows.map(r => r.revenue), 1)
  return (
    <TablaDesplazable>
      <table className="lb-table" style={{ tableLayout: 'fixed' }}>
        <thead>
          <tr>
            <th style={{ width: 28, textAlign: 'right' }}>#</th>
            <th style={{ textAlign: 'left' }}>Sucursal</th>
            <th style={{ textAlign: 'right' }}>Revenue</th>
            <th style={{ textAlign: 'right' }}>Tickets</th>
            <th style={{ textAlign: 'right' }}>AOV</th>
            <th style={{ textAlign: 'right' }}>Hora pico</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr
              key={r.branch_id}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              style={onRowClick ? { cursor: 'pointer' } : undefined}
              className={onRowClick ? 'lb-row-clickable' : undefined}
            >
              <td className="rank mono">{idx + 1}</td>
              <td className="first">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span>{r.branch_name}</span>
                  <span style={{ fontSize: 10, color: 'var(--p-muted)' }}>{r.org_name}</span>
                  <div
                    style={{
                      marginTop: 4,
                      height: 4,
                      background: 'var(--p-surface-2)',
                      borderRadius: 2,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        width: `${(r.revenue / maxRev) * 100}%`,
                        background: 'var(--p-accent)',
                      }}
                    />
                  </div>
                </div>
              </td>
              <td className="mono" style={{ textAlign: 'right' }}>{formatCurrency(r.revenue)}</td>
              <td className="mono" style={{ textAlign: 'right' }}>{r.sales_count}</td>
              <td className="mono" style={{ textAlign: 'right' }}>{formatCurrency(r.aov)}</td>
              <td className="mono" style={{ textAlign: 'right' }}>
                {r.peak_hour != null ? `${String(r.peak_hour).padStart(2, '0')}:00` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TablaDesplazable>
  )
}

// Pie palette for payment methods — matches the Editorial v2 token set.
const METHOD_COLORS = [
  'var(--p-accent)',
  '#4ade80',
  '#fbbf24',
  '#60a5fa',
  '#c084fc',
  '#f87171',
]

// ── component ────────────────────────────────────────────────────────────────

export function PlatformMetrics() {
  const navigate = useNavigate()
  const [range, setRange] = useState<StatsRange>('30d')

  // Global = la plataforma entera; Organización = un cliente a la vez. Ningún
  // KPI del modo Organización mezcla el dinero de dos clientes; lo único que
  // cruza a todos es la tira "Atención hoy".
  const [mode, setMode] = useState<PlatformMode>(() => readMode())
  const [orgId, setOrgId] = useState<number | null>(() => readOrgId())
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const { data: attention } = useAttentionToday()

  useEffect(() => {
    platformApi.getOrgs()
      .then((list) => setOrgs([...list].sort((a, b) => a.name.localeCompare(b.name, 'es'))))
      .catch(() => toast.error('No se pudo cargar la lista de organizaciones'))
  }, [])

  // Si lo recordado ya no existe (organización borrada, sesión nueva), cae a la primera.
  useEffect(() => {
    if (orgs.length === 0) return
    if (orgId !== null && orgs.some((o) => o.id === orgId)) return
    writeOrgId(orgs[0].id)
    setOrgId(orgs[0].id)
  }, [orgs, orgId])

  const changeMode = (m: PlatformMode) => { writeMode(m); setMode(m) }
  const changeOrg = (id: number) => { writeOrgId(id); setOrgId(id) }
  /** Desde un pendiente de la tira: abrir esa organización. */
  const pickOrg = (id: number) => { changeOrg(id); changeMode('organizacion') }

  // Phase 1 state
  const [kpis, setKpis] = useState<KpisExtendedResponse | null>(null)
  const [trendsMulti, setTrendsMulti] = useState<TrendsMultiResponse | null>(null)
  const [topTenants, setTopTenants] = useState<TopTenant[]>([])
  const [topBranches, setTopBranches] = useState<TopBranchRow[]>([])
  const [topProducts, setTopProducts] = useState<TopProductRow[]>([])
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethodsResponse | null>(null)
  const [branchComparison, setBranchComparison] = useState<BranchComparisonResponse | null>(null)
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null)

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  // Phase 2 (advanced — lazy): cohort retention only.
  const [cohort, setCohort] = useState<CohortRow[] | null>(null)
  const [advLoading, setAdvLoading] = useState(false)
  const [advFetched, setAdvFetched] = useState(false)

  const loadPhase1 = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      // allSettled: un endpoint colgado/lento NO bloquea el resto de la página.
      const results = await Promise.allSettled([
        platformApi.kpisExtended(range),
        platformApi.trendsMulti(range),
        platformApi.topTenants(10),
        platformApi.topBranches(10),
        platformApi.topProducts(10, range),
        platformApi.paymentMethods(range),
        platformApi.branchComparison(5, range),
        platformApi.activityHeatmap(range),
      ])
      const pick = <T,>(idx: number, fallback: T): T => {
        const r = results[idx]
        return r.status === 'fulfilled' ? (r.value as T) : fallback
      }
      setKpis(pick<KpisExtendedResponse | null>(0, null))
      setTrendsMulti(pick<TrendsMultiResponse | null>(1, null))
      const tt = pick<unknown>(2, [])
      const tb = pick<unknown>(3, [])
      const tp = pick<unknown>(4, [])
      setTopTenants(Array.isArray(tt) ? tt as TopTenant[] : [])
      setTopBranches(Array.isArray(tb) ? tb as TopBranchRow[] : [])
      setTopProducts(Array.isArray(tp) ? tp as TopProductRow[] : [])
      setPaymentMethods(pick<PaymentMethodsResponse | null>(5, null))
      setBranchComparison(pick<BranchComparisonResponse | null>(6, null))
      setHeatmap(pick<HeatmapResponse | null>(7, null))
      const failed = results.filter(r => r.status === 'rejected').length
      if (failed > 0) {
        toast.error(`${failed} de ${results.length} métricas no cargaron`)
      } else if (silent) {
        toast.success('Métricas actualizadas')
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [range])

  useEffect(() => { if (mode === 'global') loadPhase1() }, [loadPhase1, mode])

  const loadPhase2 = useCallback(async () => {
    if (advFetched || advLoading) return
    setAdvLoading(true)
    try {
      const c = await platformApi.cohortRetention()
      setCohort(Array.isArray(c) ? c : [])
      setAdvFetched(true)
    } catch {
      toast.error('Cohort retention no cargó')
    } finally {
      setAdvLoading(false)
    }
  }, [advFetched, advLoading])

  // Derived series
  const revenueSeries = useMemo<TrendPoint[]>(
    () => trendsMulti ? multiToRevenueSeries(trendsMulti.points) : [],
    [trendsMulti],
  )

  return (
    <main className="pv2-main">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="crumb">
        <span>Platform</span>
        <span className="sep">/</span>
        <span className="now">Métricas globales</span>
      </div>
      <div className="page-head">
        <div>
          <h1>{mode === 'global' ? 'Métricas globales' : 'El día de la organización'}</h1>
          <div className="sub">
            {mode === 'global'
              ? 'Panorama cross-tenant de la plataforma Atlas · SUPERADMIN'
              : 'Una organización a la vez · ningún total mezcla dinero de dos clientes'}
          </div>
        </div>
        <div className="right">
          <div className="pv2-segmented" role="tablist" aria-label="Vista de la plataforma">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'global'}
              className={mode === 'global' ? 'active' : ''}
              onClick={() => changeMode('global')}
            >
              Global
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'organizacion'}
              className={mode === 'organizacion' ? 'active' : ''}
              onClick={() => changeMode('organizacion')}
            >
              Organización
            </button>
          </div>

          {mode === 'organizacion' ? (
            <label className="pv2-attention-selector">
              <span className="hint">Organización</span>
              <select
                className="pv2-org-select"
                aria-label="Organización"
                value={orgId ?? ''}
                onChange={(e) => changeOrg(Number(e.target.value))}
              >
                {orgs.length === 0 && <option value="">Cargando…</option>}
                {orgs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </label>
          ) : (
            <>
              <div className="pill-group" role="tablist" aria-label="Rango temporal">
                {RANGES.map(r => (
                  <button
                    key={r}
                    type="button"
                    role="tab"
                    aria-pressed={r === range}
                    className={'pill ' + (r === range ? 'active' : '')}
                    onClick={() => setRange(r)}
                  >
                    {r === 'ytd' ? 'YTD' : r}
                  </button>
                ))}
              </div>
              <button
                className="btn ghost"
                type="button"
                onClick={() => loadPhase1({ silent: true })}
                disabled={refreshing}
                aria-label="Refrescar métricas"
              >
                <i
                  className={'fa-solid fa-arrow-rotate-right'}
                  style={refreshing ? { animation: 'pv2-spin 0.9s linear infinite' } : undefined}
                />
                {refreshing ? 'Refrescando…' : 'Refrescar'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Atención hoy: cruza TODAS las organizaciones (en el modo Organización
          va como panel al lado de la tabla, dentro de OrgBoard). */}
      {mode === 'global' && attention && (
        <AttentionPanel attention={attention} variant="strip" onPickOrg={pickOrg} />
      )}

      {mode === 'organizacion' ? (
        <OrgBoard orgId={orgId} attention={attention} onPickOrg={pickOrg} />
      ) : loading ? (
        <SkeletonState />
      ) : (
        <>

      {/* ── Section A · KPIs principales ───────────────────────────── */}
      <section className="grid-kpis-8">
        <KPICardV2
          label="Revenue"
          value={formatCurrency(kpis?.revenue?.total ?? 0)}
          icon="fa-dollar-sign"
          delta={deltaFraction(kpis?.revenue?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.revenue?.spark)}
        />
        <KPICardV2
          label="Tickets"
          value={kpis?.sales_count?.total ?? 0}
          icon="fa-receipt"
          delta={deltaFraction(kpis?.sales_count?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.sales_count?.spark)}
        />
        <KPICardV2
          label="AOV"
          value={formatCurrency(kpis?.aov?.value ?? 0)}
          icon="fa-coins"
          delta={deltaFraction(kpis?.aov?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.aov?.spark)}
        />
        <KPICardV2
          label="Tenants activos"
          value={kpis?.active_tenants?.value ?? 0}
          icon="fa-building"
          delta={deltaFraction(kpis?.active_tenants?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.active_tenants?.spark)}
        />
        <KPICardV2
          label="Sucursales activas"
          value={kpis?.active_branches?.value ?? 0}
          icon="fa-store"
          delta={deltaFraction(kpis?.active_branches?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.active_branches?.spark)}
        />
        <KPICardV2
          label="MRR proxy"
          value={formatCurrency(kpis?.mrr_proxy?.value ?? 0)}
          icon="fa-chart-line"
          delta={deltaFraction(kpis?.mrr_proxy?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.mrr_proxy?.spark)}
        />
        <KPICardV2
          label="Tasa activación"
          value={fmtPct(kpis?.activation_rate?.value ?? null, 1)}
          icon="fa-bolt"
          delta={deltaFraction(kpis?.activation_rate?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.activation_rate?.spark)}
        />
        <KPICardV2
          label="Tasa suspensión"
          value={fmtPct(kpis?.suspension_rate?.value ?? null, 1)}
          icon="fa-pause"
          delta={deltaFraction(kpis?.suspension_rate?.delta_pct ?? null)}
          deltaLabel={`vs. ${range}`}
          spark={asSpark(kpis?.suspension_rate?.spark)}
        />
      </section>

      {/* ── Section B · Tendencia ────────────────────────────────────── */}
      <section>
        <Card title="TENDENCIA" subtitle="Multi-serie · revenue / tickets / signups">
          <TrendChart
            data={revenueSeries}
            salesSeries={revenueSeries}
            signupsSeries={revenueSeries}
            showSeriesToggles
            showLegend={false}
            showGrid
            height={300}
          />
        </Card>
      </section>

      {/* ── Section B' · Métodos de pago ─────────────────────────────── */}
      <section>
        <Card title="MÉTODOS DE PAGO" subtitle={`Mix cross-tenant · ${range}`}>
          {paymentMethods && paymentMethods.items.length > 0 ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(260px, 320px) 1fr',
                gap: 32,
                alignItems: 'center',
              }}
            >
              <div style={{ width: '100%', height: 280 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={paymentMethods.items}
                      dataKey="revenue"
                      nameKey="label"
                      innerRadius={70}
                      outerRadius={120}
                      paddingAngle={2}
                      stroke="var(--p-bg)"
                    >
                      {paymentMethods.items.map((_, i) => (
                        <Cell key={i} fill={METHOD_COLORS[i % METHOD_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: 'var(--p-sidebar)',
                        border: '1px solid var(--p-border)',
                        borderRadius: 8,
                        color: 'var(--p-text)',
                        fontSize: 12,
                      }}
                      formatter={(v: any) => formatCurrency(typeof v === 'number' ? v : 0)}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
                {paymentMethods.items.map((m, i) => (
                  <div key={m.method} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span
                      style={{
                        width: 12, height: 12, borderRadius: 3,
                        background: METHOD_COLORS[i % METHOD_COLORS.length],
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ flex: 1, color: 'var(--p-text)', fontWeight: 500 }}>{m.label}</span>
                    <span style={{ color: 'var(--p-muted)', fontFamily: 'var(--font-mono)', minWidth: 60, textAlign: 'right' }}>
                      {m.count} ops
                    </span>
                    <span style={{ color: 'var(--p-muted)', fontFamily: 'var(--font-mono)', minWidth: 60, textAlign: 'right' }}>
                      {m.pct.toFixed(1)}%
                    </span>
                    <span style={{ color: 'var(--p-text)', fontFamily: 'var(--font-mono)', minWidth: 120, textAlign: 'right', fontWeight: 600 }}>
                      {formatCurrency(m.revenue)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ padding: 24, color: 'var(--p-muted)', fontSize: 13 }}>
              Sin pagos en el rango.
            </div>
          )}
        </Card>
      </section>

      {/* ── Section C · Comparativa sucursales ───────────────────────── */}
      <section>
        <Card title="COMPARATIVA SUCURSALES" subtitle={`Top 5 por revenue · ${range}`}>
          {branchComparison && branchComparison.items.length > 0 ? (
            <BranchComparisonTable
              rows={branchComparison.items}
              onRowClick={(r) => navigate(`/platform/organizations/${r.org_id}`)}
            />
          ) : (
            <div style={{ padding: 24, color: 'var(--p-muted)', fontSize: 13 }}>
              Sin sucursales con ventas en el rango.
            </div>
          )}
        </Card>
      </section>

      {/* ── Section C' · Activity heatmap ─────────────────────────────── */}
      <section>
        <Card title="ACTIVITY HEATMAP" subtitle={`Día × hora · ${range}`}>
          {heatmap ? (
            <ActivityHeatmap cells={heatmap.cells} maxCount={heatmap.max_count} />
          ) : (
            <div style={{ padding: 24, color: 'var(--p-muted)', fontSize: 13 }}>
              Sin datos.
            </div>
          )}
        </Card>
      </section>

      {/* ── Section D · Leaderboards ───────────────────────────────── */}
      <section className="row-thirds">
        <Leaderboard
          title="TOP TENANTS"
          rows={topTenants as unknown as Record<string, any>[]}
          columns={[
            { key: 'name', label: 'Tenant', align: 'left' },
            { key: 'revenue', label: 'Revenue', align: 'right', format: (v) => formatCurrency(v ?? 0) },
            { key: 'transactions', label: 'Tickets', align: 'right', format: (v) => String(v ?? 0) },
          ]}
          onRowClick={(r) => {
            if (r.id != null) navigate(`/platform/organizations/${r.id}`)
          }}
        />
        <Leaderboard
          title="TOP SUCURSALES"
          rows={topBranches as unknown as Record<string, any>[]}
          columns={[
            { key: 'branch_name', label: 'Sucursal', align: 'left' },
            { key: 'org_name', label: 'Org', align: 'left' },
            { key: 'revenue_30d', label: 'Rev. 30d', align: 'right', format: (v) => formatCurrency(v ?? 0) },
          ]}
          onRowClick={(r) => {
            if (r.org_id != null) navigate(`/platform/organizations/${r.org_id}`)
          }}
        />
        <Leaderboard
          title="TOP PRODUCTOS"
          rows={topProducts as unknown as Record<string, any>[]}
          columns={[
            { key: 'product_name', label: 'Producto', align: 'left' },
            { key: 'quantity_sold', label: 'Qty', align: 'right', format: (v) => String(v ?? 0) },
            { key: 'revenue', label: 'Revenue', align: 'right', format: (v) => formatCurrency(v ?? 0) },
          ]}
        />
      </section>

      {/* ── Section E · Avanzado (lazy) ────────────────────────────── */}
      <section>
        <details
          onToggle={(e) => {
            if ((e.currentTarget as HTMLDetailsElement).open) {
              loadPhase2()
            }
          }}
        >
          <summary
            style={{
              cursor: 'pointer',
              padding: '12px 16px',
              borderRadius: 8,
              border: '1px solid var(--p-border)',
              background: 'var(--p-surface)',
              color: 'var(--p-text)',
              fontSize: 13,
              userSelect: 'none',
            }}
          >
            Expandir análisis avanzado · Cohort retention
          </summary>
          <div style={{ marginTop: 16, display: 'grid', gap: 16 }}>
            {advLoading && !advFetched ? (
              <div style={{ padding: 24, color: 'var(--p-muted)', fontSize: 13 }}>
                Cargando análisis avanzado…
              </div>
            ) : (
              <Suspense fallback={
                <div style={{ padding: 24, color: 'var(--p-muted)', fontSize: 13 }}>
                  Cargando componentes…
                </div>
              }>
                <Card title="COHORT RETENTION" subtitle="Retención por cohorte mensual">
                  {cohort ? <CohortTable rows={cohort} /> : null}
                </Card>
              </Suspense>
            )}
          </div>
        </details>
      </section>
        </>
      )}
    </main>
  )
}
