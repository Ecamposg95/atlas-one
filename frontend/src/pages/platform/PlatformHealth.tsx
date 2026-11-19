import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { platformApi, HealthRow } from '../../api/platform'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'

import '../../styles/platform-v2.css'

import { KPICardV2 } from '../../components/platform/v2/KPICardV2'
import { SkeletonState } from '../../components/platform/v2/SkeletonState'
import { StatusBadgeV2 } from '../../components/platform/v2/StatusBadgeV2'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'

type SortKey = 'health' | 'revenue' | 'last_sale' | 'name'

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'health', label: 'Health ↓' },
  { key: 'revenue', label: 'Revenue 30d ↓' },
  { key: 'last_sale', label: 'Última venta ↓' },
  { key: 'name', label: 'Nombre A-Z' },
]

function healthColor(score: number): string {
  if (score >= 70) return 'var(--p-success)'
  if (score >= 40) return 'var(--p-warning)'
  return 'var(--p-danger)'
}

function healthTint(score: number): string {
  if (score >= 70) return 'rgba(34, 197, 94, 0.14)'
  if (score >= 40) return 'rgba(234, 179, 8, 0.14)'
  return 'rgba(239, 68, 68, 0.14)'
}

function formatRelative(iso: string | null, days: number | null): string {
  if (iso == null || days == null) return 'Nunca'
  if (days === 0) return 'Hoy'
  if (days === 1) return 'Ayer'
  if (days < 7) return `Hace ${days} días`
  if (days < 30) return `Hace ${Math.floor(days / 7)} sem`
  if (days < 365) return `Hace ${Math.floor(days / 30)} meses`
  return `Hace ${Math.floor(days / 365)} años`
}

function compareLastSale(a: HealthRow, b: HealthRow): number {
  const ta = a.last_sale_at ? new Date(a.last_sale_at).getTime() : 0
  const tb = b.last_sale_at ? new Date(b.last_sale_at).getTime() : 0
  return tb - ta
}

export function PlatformHealth() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<HealthRow[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('health')

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const data = await platformApi.healthMatrix()
      setRows(Array.isArray(data) ? data : [])
      if (silent) toast.success('Health matrix actualizado')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'No se pudo cargar el health matrix')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const sorted = useMemo(() => {
    const copy = [...rows]
    switch (sortKey) {
      case 'health':
        copy.sort((a, b) => b.health_score - a.health_score)
        break
      case 'revenue':
        copy.sort((a, b) => b.revenue_30d - a.revenue_30d)
        break
      case 'last_sale':
        copy.sort(compareLastSale)
        break
      case 'name':
        copy.sort((a, b) => a.name.localeCompare(b.name))
        break
    }
    return copy
  }, [rows, sortKey])

  const kpis = useMemo(() => {
    const total = rows.length
    const low = rows.filter(r => r.health_score < 50).length
    const stale = rows.filter(r => r.days_since_last_sale == null || r.days_since_last_sale >= 2).length
    const avg = total > 0
      ? Math.round(rows.reduce((s, r) => s + r.health_score, 0) / total)
      : 0
    const modulesFilled = rows.filter(r => r.modules_total > 0 && (r.modules_enabled / r.modules_total) >= 0.5).length
    return { total, low, stale, avg, modulesFilled }
  }, [rows])

  const columns: DataTableColumn<HealthRow>[] = [
    {
      key: 'name',
      label: 'Organization',
      sortable: true,
      sortValue: r => r.name,
      accessor: r => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
              color: 'var(--p-text)',
              fontSize: 13,
              letterSpacing: '-0.01em',
            }}
          >
            {r.name}
          </span>
          <span
            style={{
              fontSize: 11,
              color: 'var(--p-muted)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            #{r.organization_id}
          </span>
        </div>
      ),
    },
    {
      key: 'industry',
      label: 'Industry',
      sortable: true,
      sortValue: r => r.industry_type || '',
      accessor: r => (
        <span
          style={{
            background: 'rgba(246, 121, 59, 0.12)',
            color: 'var(--p-accent)',
            padding: '2px 8px',
            borderRadius: 4,
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
          }}
        >
          {r.industry_type || '—'}
        </span>
      ),
    },
    {
      key: 'health',
      label: 'Health',
      sortable: true,
      sortValue: r => r.health_score,
      accessor: r => (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: 42,
            padding: '3px 10px',
            borderRadius: 6,
            background: healthTint(r.health_score),
            color: healthColor(r.health_score),
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
          }}
          title={`Score ${r.health_score}/100`}
        >
          {r.health_score}
        </span>
      ),
    },
    {
      key: 'last_sale',
      label: 'Última venta',
      sortable: true,
      sortValue: r => (r.last_sale_at ? new Date(r.last_sale_at).getTime() : 0),
      accessor: r => (
        <span
          style={{
            color: r.days_since_last_sale == null || r.days_since_last_sale >= 2 ? 'var(--p-warning)' : 'var(--p-muted)',
            fontSize: 12,
          }}
        >
          {formatRelative(r.last_sale_at, r.days_since_last_sale)}
        </span>
      ),
    },
    {
      key: 'sales_7d',
      label: 'Ventas 7d',
      sortable: true,
      sortValue: r => r.sales_count_7d,
      accessor: r => (
        <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          {r.sales_count_7d.toLocaleString()}
        </span>
      ),
    },
    {
      key: 'revenue_30d',
      label: 'Revenue 30d',
      sortable: true,
      sortValue: r => r.revenue_30d,
      accessor: r => (
        <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          {formatCurrency(r.revenue_30d)}
        </span>
      ),
    },
    {
      key: 'users',
      label: 'Users 7d/total',
      sortable: true,
      sortValue: r => r.active_users_7d,
      accessor: r => (
        <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          <span style={{ color: 'var(--p-text)' }}>{r.active_users_7d}</span>
          <span style={{ color: 'var(--p-muted)' }}> / {r.total_users}</span>
        </span>
      ),
    },
    {
      key: 'modules',
      label: 'Módulos',
      sortable: true,
      sortValue: r => r.modules_total > 0 ? r.modules_enabled / r.modules_total : 0,
      accessor: r => (
        <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          <span style={{ color: 'var(--p-text)' }}>{r.modules_enabled}</span>
          <span style={{ color: 'var(--p-muted)' }}> / {r.modules_total}</span>
        </span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      sortValue: r => (r.is_active ? 1 : 0),
      accessor: r => <StatusBadgeV2 status={r.is_active ? 'active' : 'inactive'} />,
    },
  ]

  if (loading) return <SkeletonState />

  return (
    <main className="pv2-main">
      {/* ── Breadcrumb ───────────────────────────────────────────────── */}
      <div className="crumb">
        <span>Platform</span>
        <span className="sep">/</span>
        <span className="now">Health</span>
      </div>

      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="page-head">
        <div>
          <h1>Health matrix</h1>
          <div className="sub">Estado por tenant · datos últimas 24h</div>
        </div>
        <div className="right">
          <div className="pill-group" role="tablist" aria-label="Orden">
            {SORT_OPTIONS.map(opt => (
              <button
                key={opt.key}
                type="button"
                role="tab"
                aria-pressed={opt.key === sortKey}
                className={'pill ' + (opt.key === sortKey ? 'active' : '')}
                onClick={() => setSortKey(opt.key)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            className="btn ghost"
            type="button"
            onClick={() => load({ silent: true })}
            disabled={refreshing}
            aria-label="Refrescar health matrix"
          >
            <i
              className={'fa-solid fa-arrow-rotate-right'}
              style={refreshing ? { animation: 'pv2-spin 0.9s linear infinite' } : undefined}
            />
            {refreshing ? 'Refrescando…' : 'Refrescar'}
          </button>
        </div>
      </div>

      {/* ── KPIs ─────────────────────────────────────────────────────── */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 14,
          marginBottom: 20,
        }}
      >
        <KPICardV2
          label="Health bajo (<50)"
          value={kpis.low}
          icon="fa-triangle-exclamation"
        />
        <KPICardV2
          label="Sin venta 48h+"
          value={kpis.stale}
          icon="fa-bed"
        />
        <KPICardV2
          label="Health score promedio"
          value={kpis.avg}
          unit="/100"
          icon="fa-heart-pulse"
        />
        <KPICardV2
          label="Orgs con ≥50% módulos"
          value={kpis.modulesFilled}
          icon="fa-puzzle-piece"
        />
      </section>

      {/* ── Matrix table ────────────────────────────────────────────── */}
      <DataTable<HealthRow>
        data={sorted}
        columns={columns}
        rowKey={r => r.organization_id}
        searchKeys={r => `${r.name} ${r.industry_type ?? ''}`}
        pageSize={25}
        csvFilename="health-matrix.csv"
        csvRow={r => ({
          id: r.organization_id,
          name: r.name,
          industry: r.industry_type || '',
          health_score: r.health_score,
          last_sale_at: r.last_sale_at || '',
          days_since_last_sale: r.days_since_last_sale ?? '',
          sales_count_7d: r.sales_count_7d,
          sales_count_30d: r.sales_count_30d,
          revenue_7d: r.revenue_7d,
          revenue_30d: r.revenue_30d,
          active_users_7d: r.active_users_7d,
          total_users: r.total_users,
          total_branches: r.total_branches,
          modules_enabled: r.modules_enabled,
          modules_total: r.modules_total,
          is_active: r.is_active ? '1' : '0',
        })}
        onRowClick={r => navigate(`/platform/organizations/${r.organization_id}`)}
        emptyMessage="No hay orgs activas"
      />
    </main>
  )
}
