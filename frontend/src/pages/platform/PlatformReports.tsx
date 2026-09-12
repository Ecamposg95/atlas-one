import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import { reportApi } from '../../api/platform'
import { reportsMoneyApi } from '../../api/reportsMoney'
import { toast } from '../../store/toastStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { ReportFilterBar } from '../../components/platform/ReportFilterBar'
import { ReportDrillDownDrawer } from '../../components/platform/ReportDrillDownDrawer'
import { CashCutsTab } from './reports/CashCutsTab'
import { ReturnsTab } from './reports/ReturnsTab'
import { CancellationsTab } from './reports/CancellationsTab'
import { BiweeklyTab } from './reports/BiweeklyTab'
import { MoneyDetailDrawer } from './reports/MoneyDetailDrawer'
import { fmtDeltaCell, deltaTone } from './reports/compareFormat'
import type {
  ReportTab,
  ReportFilters,
  ReportParams,
  PaginatedReport,
  ProductRow,
  BranchRow,
  SellerRow,
  CustomerRow,
} from '../../types/reports'
import type { BiweeklyUnit, CompareMode, MoneyTab } from '../../types/reportsMoney'
import '../../styles/platform-v2.css'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'

// ── Constants ───────────────────────────────────────────────────────────────

const TABS: { key: ReportTab; label: string }[] = [
  { key: 'productos',     label: 'Productos' },
  { key: 'sucursales',    label: 'Sucursales' },
  { key: 'vendedores',    label: 'Vendedores' },
  { key: 'clientes',      label: 'Clientes' },
  { key: 'cortes',        label: 'Cortes' },
  { key: 'devoluciones',  label: 'Devoluciones' },
  { key: 'cancelaciones', label: 'Cancelaciones' },
  { key: 'quincenal',     label: 'Quincenal · método' },
]

const MONEY_TABS: readonly ReportTab[] = ['cortes', 'devoluciones', 'cancelaciones', 'quincenal']

function isMoneyTab(tab: ReportTab): tab is MoneyTab {
  return (MONEY_TABS as readonly string[]).includes(tab)
}

const DEFAULT_SORT: Record<ReportTab, string> = {
  productos:     'revenue:desc',
  sucursales:    'revenue:desc',
  vendedores:    'revenue:desc',
  clientes:      'total_revenue:desc',
  cortes:        '',
  devoluciones:  '',
  cancelaciones: '',
  quincenal:     '',
}

const PAGE_SIZE = 50

// ── Helpers ─────────────────────────────────────────────────────────────────

function readFiltersFromSearch(sp: URLSearchParams): ReportFilters {
  const range = (sp.get('range') ?? '30d') as ReportFilters['range']
  const start = sp.get('start') ?? undefined
  const end = sp.get('end') ?? undefined
  const orgIdRaw = sp.get('org_id')
  const branchIdRaw = sp.get('branch_id')
  return {
    range,
    start,
    end,
    org_id: orgIdRaw ? Number(orgIdRaw) : undefined,
    branch_id: branchIdRaw ? Number(branchIdRaw) : undefined,
  }
}

function fmtMoney(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 })
}

function fmtMoneyDecimal(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 2 })
}

function fmtPct(s: string | null): string {
  if (s === null || s === undefined) return '—'
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return n.toFixed(2) + '%'
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return iso
  return d.toLocaleDateString('es-MX', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

function isoDate(d: Date): string {
  const yy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

function resolveRange(filters: ReportFilters): { start?: string; end?: string } {
  if (filters.range === 'custom') {
    return { start: filters.start, end: filters.end }
  }
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const end = isoDate(today)
  const startDate = new Date(today)
  if (filters.range === '7d')      startDate.setDate(startDate.getDate() - 7)
  else if (filters.range === '90d') startDate.setDate(startDate.getDate() - 90)
  else if (filters.range === '12m') startDate.setFullYear(startDate.getFullYear() - 1)
  else                              startDate.setDate(startDate.getDate() - 30)  // default 30d
  return { start: isoDate(startDate), end }
}

function paramsForRequest(
  filters: ReportFilters,
  sort: string,
  page: number,
  compare: CompareMode = 'none',
): ReportParams {
  const out: ReportParams = {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  }
  // Los endpoints de dinero no ordenan por parámetro: mandarles `sort=''` es
  // ruido en la URL, en el CSV y en la llave del cache.
  if (sort) out.sort = sort
  const { start, end } = resolveRange(filters)
  if (start) out.start = start
  if (end) out.end = end
  if (filters.org_id !== undefined) out.org_id = filters.org_id
  if (filters.branch_id !== undefined) out.branch_id = filters.branch_id
  if (compare !== 'none') out.compare = compare
  return out
}

// ── Page ────────────────────────────────────────────────────────────────────

export function PlatformReports() {
  const [searchParams, setSearchParams] = useSearchParams()

  const tab = (searchParams.get('tab') ?? 'productos') as ReportTab
  const filters = useMemo(() => readFiltersFromSearch(searchParams), [searchParams])
  const sort = searchParams.get('sort') ?? DEFAULT_SORT[tab]
  const compare = (searchParams.get('compare') ?? 'none') as CompareMode
  // La unidad del quincenal vive en la URL para que el CSV salga con la misma
  // agrupación que la tabla en pantalla.
  const biweeklyUnit = (searchParams.get('unit') ?? 'branch') as BiweeklyUnit

  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<{ id: string | number; label: string } | null>(null)

  const setTab = (next: ReportTab) => {
    const sp = new URLSearchParams(searchParams)
    sp.set('tab', next)
    sp.delete('sort')
    setSearchParams(sp, { replace: true })
    setPage(0)
    setSelected(null)
  }

  const setFilters = useCallback((next: ReportFilters) => {
    const sp = new URLSearchParams(searchParams)
    if (next.range) sp.set('range', next.range); else sp.delete('range')
    if (next.start) sp.set('start', next.start); else sp.delete('start')
    if (next.end) sp.set('end', next.end); else sp.delete('end')
    if (next.org_id !== undefined) sp.set('org_id', String(next.org_id)); else sp.delete('org_id')
    if (next.branch_id !== undefined) sp.set('branch_id', String(next.branch_id)); else sp.delete('branch_id')
    setSearchParams(sp, { replace: true })
    setPage(0)
  }, [searchParams, setSearchParams])

  const setSort = (next: string) => {
    const sp = new URLSearchParams(searchParams)
    sp.set('sort', next)
    setSearchParams(sp, { replace: true })
    setPage(0)
  }

  const setCompare = (next: CompareMode) => {
    const sp = new URLSearchParams(searchParams)
    if (next === 'none') sp.delete('compare'); else sp.set('compare', next)
    setSearchParams(sp, { replace: true })
    setPage(0)
  }

  const setBiweeklyUnit = (next: BiweeklyUnit) => {
    const sp = new URLSearchParams(searchParams)
    if (next === 'branch') sp.delete('unit'); else sp.set('unit', next)
    setSearchParams(sp, { replace: true })
    setPage(0)
  }

  return (
    <PlatformPageShell
      breadcrumb="Platform / Reportes"
      title="Reportes"
      actions={<span style={{ fontSize: 12, color: 'var(--p-muted)' }}>Análisis cross-tenant</span>}
    >
      <TabBar tab={tab} onChange={setTab} />

      <ReportFilterBar
        filters={filters}
        onFiltersChange={setFilters}
        compare={compare}
        onCompareChange={setCompare}
        showCompare={!isMoneyTab(tab)}
        onExportCsv={async () => {
          try {
            // Las pestañas de dinero no soportan compare: un `compare`
            // heredado de otra pestaña no se manda en su CSV.
            const esDinero = isMoneyTab(tab)
            const params: ReportParams = paramsForRequest(
              filters, esDinero ? '' : sort, 0, esDinero ? undefined : compare,
            )
            delete params.limit
            delete params.offset
            if (tab === 'productos') await reportApi.exportProductsCsv(params)
            else if (tab === 'sucursales') await reportApi.exportBranchesCsv(params)
            else if (tab === 'vendedores') await reportApi.exportSellersCsv(params)
            else if (tab === 'clientes') await reportApi.exportCustomersCsv(params)
            else if (tab === 'cortes') await reportsMoneyApi.exportCashCutsCsv(params)
            else if (tab === 'devoluciones') await reportsMoneyApi.exportReturnsCsv(params)
            else if (tab === 'cancelaciones') await reportsMoneyApi.exportCancellationsCsv(params)
            else await reportsMoneyApi.exportBiweeklyCsv({ ...params, unit: biweeklyUnit })
          } catch (e: any) {
            toast.error(e?.response?.data?.detail ?? e?.message ?? 'No se pudo exportar')
          }
        }}
      />

      <ReportTabContent
        tab={tab}
        filters={filters}
        sort={sort}
        page={page}
        compare={compare}
        biweeklyUnit={biweeklyUnit}
        onBiweeklyUnitChange={setBiweeklyUnit}
        onPageChange={setPage}
        onSortChange={setSort}
        onRowClick={(id, label) => setSelected({ id, label })}
      />

      {isMoneyTab(tab) ? (
        <MoneyDetailDrawer
          tab={tab}
          branchId={typeof selected?.id === 'number' ? selected.id : null}
          branchLabel={selected?.label ?? ''}
          params={paramsForRequest(filters, '', 0)}
          onClose={() => setSelected(null)}
        />
      ) : (
        <ReportDrillDownDrawer
          tab={tab}
          entityId={selected?.id ?? null}
          entityLabel={selected?.label ?? ''}
          filters={filters}
          onClose={() => setSelected(null)}
        />
      )}
    </PlatformPageShell>
  )
}

// ── TabBar ──────────────────────────────────────────────────────────────────

function TabBar({ tab, onChange }: { tab: ReportTab; onChange: (t: ReportTab) => void }) {
  return (
    <div style={{
      display: 'flex',
      gap: 4,
      borderBottom: '1px solid var(--p-border)',
      marginBottom: 0,
      overflowX: 'auto',
    }}>
      {TABS.map((t) => {
        const active = t.key === tab
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: '2px solid ' + (active ? 'var(--p-accent)' : 'transparent'),
              color: active ? 'var(--p-text)' : 'var(--p-muted)',
              padding: '10px 16px',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
              marginBottom: -1,
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

// ── Tab content router ──────────────────────────────────────────────────────

interface TabContentProps {
  tab: ReportTab
  filters: ReportFilters
  sort: string
  page: number
  compare: CompareMode
  biweeklyUnit: BiweeklyUnit
  onBiweeklyUnitChange: (u: BiweeklyUnit) => void
  onPageChange: (p: number) => void
  onSortChange: (s: string) => void
  onRowClick: (id: string | number, label: string) => void
}

function ReportTabContent(props: TabContentProps) {
  if (props.tab === 'productos') return <ProductsReport {...props} />
  if (props.tab === 'sucursales') return <BranchesReport {...props} />
  if (props.tab === 'vendedores') return <SellersReport {...props} />
  if (props.tab === 'clientes') return <CustomersReport {...props} />

  // Las pestañas de dinero no soportan `compare` en el backend: nunca se
  // manda, aunque el usuario lo haya elegido antes en otra pestaña.
  const moneyParams = paramsForRequest(props.filters, '', props.page)
  if (props.tab === 'cortes') {
    return (
      <CashCutsTab
        params={moneyParams} filters={props.filters}
        page={props.page} onPageChange={props.onPageChange}
        onRowClick={props.onRowClick}
      />
    )
  }
  if (props.tab === 'devoluciones') {
    return (
      <ReturnsTab
        params={moneyParams} filters={props.filters}
        page={props.page} onPageChange={props.onPageChange}
        onRowClick={props.onRowClick}
      />
    )
  }
  if (props.tab === 'cancelaciones') {
    return (
      <CancellationsTab
        params={moneyParams} filters={props.filters}
        page={props.page} onPageChange={props.onPageChange}
        onRowClick={props.onRowClick}
      />
    )
  }
  return (
    <BiweeklyTab
      params={moneyParams}
      filters={props.filters}
      unit={props.biweeklyUnit}
      onUnitChange={props.onBiweeklyUnitChange}
      page={props.page}
      onPageChange={props.onPageChange}
    />
  )
}

// ── Reusable table primitives ───────────────────────────────────────────────

const cellStyle: React.CSSProperties = {
  padding: '12px 14px',
  borderBottom: '1px solid var(--p-border-2)',
  fontSize: 13,
  color: 'var(--p-text)',
}

const rightCell: React.CSSProperties = {
  ...cellStyle,
  textAlign: 'right',
  fontFamily: 'var(--font-mono)',
  fontVariantNumeric: 'tabular-nums',
}

function HeaderCell({
  label, sortKey, sort, onSortChange, align = 'left',
}: {
  label: string
  sortKey?: string
  sort: string
  onSortChange: (s: string) => void
  align?: 'left' | 'right'
}) {
  const [activeKey, activeDir] = sort.split(':') as [string, 'asc' | 'desc']
  const isActive = sortKey && sortKey === activeKey
  const handleClick = () => {
    if (!sortKey) return
    const nextDir = isActive && activeDir === 'desc' ? 'asc' : 'desc'
    onSortChange(`${sortKey}:${nextDir}`)
  }
  return (
    <th
      onClick={handleClick}
      style={{
        padding: '10px 14px',
        textAlign: align,
        color: 'var(--p-hint)',
        fontSize: 10,
        textTransform: 'uppercase',
        letterSpacing: '0.12em',
        fontWeight: 500,
        cursor: sortKey ? 'pointer' : 'default',
        userSelect: 'none',
        borderBottom: '1px solid var(--p-border)',
        background: 'transparent',
      }}
    >
      {label}
      {isActive && (
        <span style={{ marginLeft: 6, color: 'var(--p-accent)' }}>
          {activeDir === 'asc' ? '↑' : '↓'}
        </span>
      )}
    </th>
  )
}

// ── Columna Δ (compare !== 'none') para los cuatro pivotes clásicos ────────

function DeltaHeaderCell({ label }: { label: string }) {
  return (
    <th
      className="pv2-delta-col"
      style={{
        padding: '10px 14px', textAlign: 'right', color: 'var(--p-hint)', fontSize: 10,
        textTransform: 'uppercase', letterSpacing: '0.12em', fontWeight: 500,
        borderBottom: '1px solid var(--p-border)', background: 'transparent',
      }}
    >
      Δ {label}
    </th>
  )
}

// Los cuatro pivotes clásicos solo comparan Revenue, donde crecer es bueno:
// por eso `deltaTone` va sin `lowerIsBetter`. Si alguna vez se compara una
// cifra donde crecer es malo (faltantes), se le pasa aquí.
function DeltaCell({ pct }: { pct: number | null | undefined }) {
  return (
    <td className={`pv2-delta-col pv2-tone-${deltaTone(pct)}`} style={{ ...rightCell }}>
      {fmtDeltaCell(pct)}
    </td>
  )
}

function Pagination({
  page, total, onPageChange,
}: {
  page: number
  total: number
  onPageChange: (p: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  if (total <= PAGE_SIZE) return null
  return (
    <div style={{
      padding: '12px 18px',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      borderTop: '1px solid var(--p-border)',
    }}>
      <button
        onClick={() => onPageChange(Math.max(0, page - 1))}
        disabled={page === 0}
        style={{
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          color: 'var(--p-text)',
          padding: '6px 12px',
          borderRadius: 8,
          fontSize: 12,
          cursor: page === 0 ? 'not-allowed' : 'pointer',
          opacity: page === 0 ? 0.5 : 1,
        }}
      >
        <i className="fa-solid fa-chevron-left" style={{ fontSize: 10 }} /> Anterior
      </button>
      <span style={{
        color: 'var(--p-muted)',
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
      }}>
        Pág. {page + 1} / {pages} · {total} registros
      </span>
      <button
        onClick={() => onPageChange(Math.min(pages - 1, page + 1))}
        disabled={page >= pages - 1}
        style={{
          background: 'var(--p-surface)',
          border: '1px solid var(--p-border)',
          color: 'var(--p-text)',
          padding: '6px 12px',
          borderRadius: 8,
          fontSize: 12,
          cursor: page >= pages - 1 ? 'not-allowed' : 'pointer',
          opacity: page >= pages - 1 ? 0.5 : 1,
        }}
      >
        Siguiente <i className="fa-solid fa-chevron-right" style={{ fontSize: 10 }} />
      </button>
    </div>
  )
}

function TopChart({
  title,
  data,
  dataKey,
  labelFormatter,
}: {
  title: string
  data: { label: string; value: number }[]
  dataKey: string
  labelFormatter?: (v: number) => string
}) {
  const fmt = labelFormatter ?? ((v) => v.toLocaleString('es-MX'))
  return (
    <div style={{
      background: 'var(--p-surface)',
      border: '1px solid var(--p-border)',
      borderRadius: 14,
      padding: '16px 18px',
    }}>
      <h3 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 14,
        fontWeight: 600,
        margin: '0 0 12px',
        color: 'var(--p-text)',
        letterSpacing: '-0.01em',
      }}>
        {title}
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--p-border)" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--p-hint)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval={0}
            angle={-25}
            textAnchor="end"
            height={70}
          />
          <YAxis
            tick={{ fill: 'var(--p-hint)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={64}
            tickFormatter={fmt}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--p-sidebar)',
              border: '1px solid var(--p-border)',
              borderRadius: 8,
              color: 'var(--p-text)',
              fontSize: 12,
            }}
            formatter={(v: any) => fmt(typeof v === 'number' ? v : Number(v) || 0)}
          />
          <Bar dataKey={dataKey} fill="var(--p-accent)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Loading / error helpers ─────────────────────────────────────────────────

function useReportFetch<T>(
  fetcher: () => Promise<PaginatedReport<T>>,
  deps: unknown[],
): { data: PaginatedReport<T> | null; loading: boolean; error: string | null; reload: () => void } {
  const [data, setData] = useState<PaginatedReport<T> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    setError(null)
    let timeoutId: ReturnType<typeof setTimeout> | null = null
    const timeoutPromise = new Promise<never>((_, reject) => {
      timeoutId = setTimeout(() => reject(new Error('Tiempo de espera agotado (15s)')), 15_000)
    })
    Promise.race([fetcher(), timeoutPromise])
      .then((res) => { if (!cancel) setData(res as PaginatedReport<T>) })
      .catch((e) => {
        if (cancel) return
        const msg = e?.response?.data?.detail ?? e?.message ?? 'Error cargando reporte'
        setError(typeof msg === 'string' ? msg : 'Error cargando reporte')
      })
      .finally(() => {
        if (timeoutId) clearTimeout(timeoutId)
        if (!cancel) setLoading(false)
      })
    return () => { cancel = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, loading, error, reload: () => setTick((t) => t + 1) }
}

function ReportShell({
  loading, error, onReload, children,
}: {
  loading: boolean
  error: string | null
  onReload: () => void
  children: React.ReactNode
}) {
  if (error) {
    return (
      <div style={{
        padding: 18,
        border: '1px solid var(--p-border)',
        borderRadius: 12,
        background: 'rgba(239, 68, 68, 0.08)',
        color: 'var(--p-text)',
        fontSize: 13,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}>
        <span>{error}</span>
        <button
          type="button"
          onClick={onReload}
          style={{
            alignSelf: 'flex-start',
            background: 'var(--p-surface-2)',
            border: '1px solid var(--p-border)',
            color: 'var(--p-text)',
            padding: '6px 12px',
            borderRadius: 8,
            fontSize: 12,
            cursor: 'pointer',
          }}
        >
          Reintentar
        </button>
      </div>
    )
  }
  return (
    <div style={{ opacity: loading ? 0.55 : 1, transition: 'opacity 0.15s ease' }}>
      {children}
    </div>
  )
}

// ── Productos ───────────────────────────────────────────────────────────────

function ProductsReport({ filters, sort, page, compare, onPageChange, onSortChange, onRowClick }: TabContentProps) {
  const params = useMemo(() => paramsForRequest(filters, sort, page, compare), [filters, sort, page, compare])
  const { data, loading, error, reload } = useReportFetch<ProductRow>(
    () => reportApi.getProducts(params),
    [JSON.stringify(params)],
  )
  const withDelta = compare !== 'none'

  const chartData = useMemo(() => {
    if (!data) return []
    return data.items.slice(0, 10).map((r) => ({
      label: r.name.length > 18 ? r.name.slice(0, 16) + '…' : r.name,
      value: Number(r.revenue),
    }))
  }, [data])

  return (
    <ReportShell loading={loading} error={error} onReload={reload}>
      <TopChart title="Top 10 productos por revenue" data={chartData} dataKey="value" labelFormatter={(v) => fmtMoney(String(v))} />
      <div style={{ height: 16 }} />
      <div style={{ background: 'var(--p-surface)', border: '1px solid var(--p-border)', borderRadius: 14, overflow: 'hidden' }}>
        <TablaDesplazable>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, fontSize: 13 }}>
            <thead>
              <tr>
                <HeaderCell label="SKU" sortKey="sku" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Nombre" sortKey="name" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Marca" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Depto" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Unidades" sortKey="units_sold" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Revenue" sortKey="revenue" sort={sort} onSortChange={onSortChange} align="right" />
                {withDelta && <DeltaHeaderCell label="Revenue" />}
                <HeaderCell label="AOV" sortKey="aov" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="% Dev" sortKey="return_rate_pct" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Margen est." sortKey="estimated_margin_pct" sort={sort} onSortChange={onSortChange} align="right" />
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((r) => (
                <tr
                  key={r.product_id}
                  onClick={() => onRowClick(r.product_id, r.name)}
                  style={{ cursor: 'pointer', transition: 'background 0.12s ease' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--p-surface-2)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <td style={{ ...cellStyle, fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.sku}</td>
                  <td style={cellStyle}>{r.name}</td>
                  <td style={cellStyle}>{r.brand ?? '—'}</td>
                  <td style={cellStyle}>{r.department ?? '—'}</td>
                  <td style={rightCell}>{r.units_sold.toLocaleString('es-MX')}</td>
                  <td style={rightCell}>{fmtMoney(r.revenue)}</td>
                  {withDelta && <DeltaCell pct={r.delta_revenue_pct} />}
                  <td style={rightCell}>{fmtMoneyDecimal(r.aov)}</td>
                  <td style={rightCell}>{fmtPct(r.return_rate_pct)}</td>
                  <td style={rightCell}>{fmtPct(r.estimated_margin_pct)}</td>
                </tr>
              ))}
              {(!data || data.items.length === 0) && !loading && (
                <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={withDelta ? 10 : 9}>Sin productos.</td></tr>
              )}
            </tbody>
          </table>
        </TablaDesplazable>
        <Pagination page={page} total={data?.total ?? 0} onPageChange={onPageChange} />
      </div>
    </ReportShell>
  )
}

// ── Sucursales ──────────────────────────────────────────────────────────────

function BranchesReport({ filters, sort, page, compare, onPageChange, onSortChange, onRowClick }: TabContentProps) {
  const params = useMemo(() => paramsForRequest(filters, sort, page, compare), [filters, sort, page, compare])
  const { data, loading, error, reload } = useReportFetch<BranchRow>(
    () => reportApi.getBranches(params),
    [JSON.stringify(params)],
  )
  const withDelta = compare !== 'none'

  const chartData = useMemo(() => {
    if (!data) return []
    return data.items.slice(0, 10).map((r) => ({
      label: r.name.length > 18 ? r.name.slice(0, 16) + '…' : r.name,
      value: Number(r.revenue),
    }))
  }, [data])

  return (
    <ReportShell loading={loading} error={error} onReload={reload}>
      <TopChart title="Top 10 sucursales por revenue" data={chartData} dataKey="value" labelFormatter={(v) => fmtMoney(String(v))} />
      <div style={{ height: 16 }} />
      <div style={{ background: 'var(--p-surface)', border: '1px solid var(--p-border)', borderRadius: 14, overflow: 'hidden' }}>
        <TablaDesplazable>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, fontSize: 13 }}>
            <thead>
              <tr>
                <HeaderCell label="Sucursal" sortKey="name" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Org" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Ciudad" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Trans." sortKey="transactions" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Revenue" sortKey="revenue" sort={sort} onSortChange={onSortChange} align="right" />
                {withDelta && <DeltaHeaderCell label="Revenue" />}
                <HeaderCell label="Tkt prom." sortKey="avg_ticket" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Cajeros" sortKey="active_cashiers" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="% Dev" sortKey="return_rate_pct" sort={sort} onSortChange={onSortChange} align="right" />
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((r) => (
                <tr
                  key={r.branch_id}
                  onClick={() => onRowClick(r.branch_id, r.name)}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--p-surface-2)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <td style={cellStyle}>{r.name}</td>
                  <td style={cellStyle}>{r.org_name}</td>
                  <td style={cellStyle}>{r.city ?? '—'}</td>
                  <td style={rightCell}>{r.transactions.toLocaleString('es-MX')}</td>
                  <td style={rightCell}>{fmtMoney(r.revenue)}</td>
                  {withDelta && <DeltaCell pct={r.delta_revenue_pct} />}
                  <td style={rightCell}>{fmtMoneyDecimal(r.avg_ticket)}</td>
                  <td style={rightCell}>{r.active_cashiers}</td>
                  <td style={rightCell}>{fmtPct(r.return_rate_pct)}</td>
                </tr>
              ))}
              {(!data || data.items.length === 0) && !loading && (
                <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={withDelta ? 9 : 8}>Sin sucursales.</td></tr>
              )}
            </tbody>
          </table>
        </TablaDesplazable>
        <Pagination page={page} total={data?.total ?? 0} onPageChange={onPageChange} />
      </div>
    </ReportShell>
  )
}

// ── Vendedores ──────────────────────────────────────────────────────────────

function SellersReport({ filters, sort, page, compare, onPageChange, onSortChange, onRowClick }: TabContentProps) {
  const params = useMemo(() => paramsForRequest(filters, sort, page, compare), [filters, sort, page, compare])
  const { data, loading, error, reload } = useReportFetch<SellerRow>(
    () => reportApi.getSellers(params),
    [JSON.stringify(params)],
  )
  const withDelta = compare !== 'none'

  const chartData = useMemo(() => {
    if (!data) return []
    return data.items.slice(0, 10).map((r) => ({
      label: r.full_name.length > 18 ? r.full_name.slice(0, 16) + '…' : r.full_name,
      value: Number(r.revenue),
    }))
  }, [data])

  return (
    <ReportShell loading={loading} error={error} onReload={reload}>
      <TopChart title="Top 10 vendedores por revenue" data={chartData} dataKey="value" labelFormatter={(v) => fmtMoney(String(v))} />
      <div style={{ height: 16 }} />
      <div style={{ background: 'var(--p-surface)', border: '1px solid var(--p-border)', borderRadius: 14, overflow: 'hidden' }}>
        <TablaDesplazable>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, fontSize: 13 }}>
            <thead>
              <tr>
                <HeaderCell label="Nombre" sortKey="full_name" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Rol" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Sucursal" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Org" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Trans." sortKey="transactions" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Revenue" sortKey="revenue" sort={sort} onSortChange={onSortChange} align="right" />
                {withDelta && <DeltaHeaderCell label="Revenue" />}
                <HeaderCell label="Tkt prom." sortKey="avg_ticket" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Días act." sortKey="active_days" sort={sort} onSortChange={onSortChange} align="right" />
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((r) => (
                <tr
                  key={r.user_id}
                  onClick={() => onRowClick(r.user_id, r.full_name)}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--p-surface-2)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <td style={cellStyle}>{r.full_name}</td>
                  <td style={cellStyle}>{r.role}</td>
                  <td style={cellStyle}>{r.branch_name}</td>
                  <td style={cellStyle}>{r.org_name}</td>
                  <td style={rightCell}>{r.transactions.toLocaleString('es-MX')}</td>
                  <td style={rightCell}>{fmtMoney(r.revenue)}</td>
                  {withDelta && <DeltaCell pct={r.delta_revenue_pct} />}
                  <td style={rightCell}>{fmtMoneyDecimal(r.avg_ticket)}</td>
                  <td style={rightCell}>{r.active_days}</td>
                </tr>
              ))}
              {(!data || data.items.length === 0) && !loading && (
                <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={withDelta ? 9 : 8}>Sin vendedores.</td></tr>
              )}
            </tbody>
          </table>
        </TablaDesplazable>
        <Pagination page={page} total={data?.total ?? 0} onPageChange={onPageChange} />
      </div>
    </ReportShell>
  )
}

// ── Clientes ────────────────────────────────────────────────────────────────

function CustomersReport({ filters, sort, page, compare, onPageChange, onSortChange, onRowClick }: TabContentProps) {
  const params = useMemo(() => paramsForRequest(filters, sort, page, compare), [filters, sort, page, compare])
  const { data, loading, error, reload } = useReportFetch<CustomerRow>(
    () => reportApi.getCustomers(params),
    [JSON.stringify(params)],
  )
  const withDelta = compare !== 'none'

  const chartData = useMemo(() => {
    if (!data) return []
    return data.items.slice(0, 10).map((r) => ({
      label: r.customer_name.length > 18 ? r.customer_name.slice(0, 16) + '…' : r.customer_name,
      value: Number(r.total_revenue),
    }))
  }, [data])

  return (
    <ReportShell loading={loading} error={error} onReload={reload}>
      <TopChart title="Top 10 clientes por revenue" data={chartData} dataKey="value" labelFormatter={(v) => fmtMoney(String(v))} />
      <div style={{ height: 16 }} />
      <div style={{ background: 'var(--p-surface)', border: '1px solid var(--p-border)', borderRadius: 14, overflow: 'hidden' }}>
        <TablaDesplazable>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, fontSize: 13 }}>
            <thead>
              <tr>
                <HeaderCell label="Cliente" sortKey="customer_name" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Tickets" sortKey="ticket_count" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Revenue" sortKey="total_revenue" sort={sort} onSortChange={onSortChange} align="right" />
                {withDelta && <DeltaHeaderCell label="Revenue" />}
                <HeaderCell label="Tkt prom." sortKey="avg_ticket" sort={sort} onSortChange={onSortChange} align="right" />
                <HeaderCell label="Último" sortKey="last_purchase" sort={sort} onSortChange={onSortChange} />
                <HeaderCell label="Recur. (días)" sortKey="avg_days_between_purchases" sort={sort} onSortChange={onSortChange} align="right" />
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((r) => (
                <tr
                  key={r.customer_id}
                  onClick={() => onRowClick(r.customer_id, r.customer_name)}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--p-surface-2)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <td style={cellStyle}>{r.customer_name}</td>
                  <td style={rightCell}>{r.ticket_count}</td>
                  <td style={rightCell}>{fmtMoney(r.total_revenue)}</td>
                  {withDelta && <DeltaCell pct={r.delta_total_revenue_pct} />}
                  <td style={rightCell}>{fmtMoneyDecimal(r.avg_ticket)}</td>
                  <td style={cellStyle}>{fmtDate(r.last_purchase)}</td>
                  <td style={rightCell}>
                    {r.avg_days_between_purchases !== null
                      ? r.avg_days_between_purchases.toFixed(1)
                      : '—'}
                  </td>
                </tr>
              ))}
              {(!data || data.items.length === 0) && !loading && (
                <tr><td style={{ ...cellStyle, textAlign: 'center', color: 'var(--p-muted)' }} colSpan={withDelta ? 7 : 6}>Sin clientes.</td></tr>
              )}
            </tbody>
          </table>
        </TablaDesplazable>
        <Pagination page={page} total={data?.total ?? 0} onPageChange={onPageChange} />
      </div>
    </ReportShell>
  )
}
