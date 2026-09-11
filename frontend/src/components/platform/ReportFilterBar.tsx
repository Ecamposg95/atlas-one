import { useEffect, useState } from 'react'
import { platformApi, PlatformOrg, PlatformBranch } from '../../api/platform'
import type { ReportFilters } from '../../types/reports'
import type { CompareMode } from '../../types/reportsMoney'
import { COMPARE_OPTIONS } from '../../pages/platform/reports/compareFormat'

interface Props {
  filters: ReportFilters
  onFiltersChange: (next: ReportFilters) => void
  compare: CompareMode
  onCompareChange: (m: CompareMode) => void
  onExportCsv: () => void
  isLoading?: boolean
  /** Las cuatro pestañas de dinero no soportan comparación de periodos en el
   * backend (spec 2026-09-09 §5.2) — el selector se oculta ahí en vez de
   * quedarse visible sin hacer nada. */
  showCompare?: boolean
}

const RANGE_PRESETS: { key: NonNullable<ReportFilters['range']>; label: string }[] = [
  { key: '7d', label: '7d' },
  { key: '30d', label: '30d' },
  { key: '90d', label: '90d' },
  { key: '12m', label: '12m' },
  { key: 'custom', label: 'Custom' },
]

const inputStyle: React.CSSProperties = {
  background: 'var(--p-surface-2)',
  border: '1px solid var(--p-border)',
  color: 'var(--p-text)',
  padding: '8px 10px',
  borderRadius: 8,
  fontSize: 13,
  outline: 'none',
  fontFamily: 'var(--font-sans)',
  minWidth: 180,
}

const pillBtn = (active: boolean): React.CSSProperties => ({
  background: active ? 'var(--p-accent)' : 'var(--p-surface-2)',
  color: active ? '#fff' : 'var(--p-text)',
  border: '1px solid ' + (active ? 'var(--p-accent)' : 'var(--p-border)'),
  padding: '6px 12px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'var(--font-sans)',
})

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 10,
  color: 'var(--p-hint)',
  textTransform: 'uppercase',
  letterSpacing: '0.12em',
  fontWeight: 600,
  marginBottom: 6,
}

export function ReportFilterBar({
  filters, onFiltersChange, compare, onCompareChange, onExportCsv, isLoading, showCompare = true,
}: Props) {
  const [orgs, setOrgs] = useState<PlatformOrg[]>([])
  const [branches, setBranches] = useState<PlatformBranch[]>([])
  const [bannerDismissed, setBannerDismissed] = useState(false)

  useEffect(() => {
    let cancel = false
    platformApi.getOrgs().then((rows) => {
      if (cancel) return
      setOrgs(rows)
    }).catch(() => { /* handled by parent */ })
    return () => { cancel = true }
  }, [])

  useEffect(() => {
    if (!filters.org_id) { setBranches([]); return }
    let cancel = false
    platformApi.getBranches(filters.org_id).then((rows) => {
      if (cancel) return
      setBranches(rows)
    }).catch(() => { /* handled by parent */ })
    return () => { cancel = true }
  }, [filters.org_id])

  const setRange = (range: NonNullable<ReportFilters['range']>) => {
    if (range === 'custom') {
      onFiltersChange({ ...filters, range })
    } else {
      onFiltersChange({ ...filters, range, start: undefined, end: undefined })
    }
  }

  const setOrg = (orgId: number | undefined) => {
    onFiltersChange({ ...filters, org_id: orgId, branch_id: undefined })
  }

  const setBranch = (branchId: number | undefined) => {
    onFiltersChange({ ...filters, branch_id: branchId })
  }

  const setStart = (start: string | undefined) => {
    onFiltersChange({ ...filters, range: 'custom', start })
  }

  const setEnd = (end: string | undefined) => {
    onFiltersChange({ ...filters, range: 'custom', end })
  }

  const showWarning = !filters.org_id && !bannerDismissed

  return (
    <div style={{
      background: 'var(--p-surface)',
      border: '1px solid var(--p-border)',
      borderRadius: 14,
      padding: '16px 18px',
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
    }}>
      <div className="pv2-filters">
        {/* ── Range pills + custom dates ────────────────────────────── */}
        <div style={{ minWidth: 240 }}>
          <span style={labelStyle}>Rango</span>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {RANGE_PRESETS.map((r) => (
              <button
                key={r.key}
                type="button"
                onClick={() => setRange(r.key)}
                style={pillBtn(filters.range === r.key)}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {filters.range === 'custom' && (
          <>
            <div>
              <span style={labelStyle}>Inicio</span>
              <input
                type="date"
                style={inputStyle}
                value={filters.start ?? ''}
                onChange={(e) => setStart(e.target.value || undefined)}
              />
            </div>
            <div>
              <span style={labelStyle}>Fin</span>
              <input
                type="date"
                style={inputStyle}
                value={filters.end ?? ''}
                onChange={(e) => setEnd(e.target.value || undefined)}
              />
            </div>
          </>
        )}

        {/* ── Org selector ──────────────────────────────────────────── */}
        <div>
          <span style={labelStyle}>Organización</span>
          <select
            style={inputStyle}
            value={filters.org_id ?? ''}
            onChange={(e) => setOrg(e.target.value ? Number(e.target.value) : undefined)}
          >
            <option value="">Todos los orgs</option>
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </select>
        </div>

        {/* ── Branch selector (disabled when no org) ────────────────── */}
        <div>
          <span style={labelStyle}>Sucursal</span>
          <select
            style={{ ...inputStyle, opacity: filters.org_id ? 1 : 0.55 }}
            value={filters.branch_id ?? ''}
            onChange={(e) => setBranch(e.target.value ? Number(e.target.value) : undefined)}
            disabled={!filters.org_id}
          >
            <option value="">Todas las sucursales</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>

        {/* ── Comparación de periodos ───────────────────────────────── */}
        {showCompare && (
          <div style={{ minWidth: 180 }}>
            <span style={labelStyle}>Comparar</span>
            <select
              style={inputStyle}
              value={compare}
              onChange={(e) => onCompareChange(e.target.value as CompareMode)}
            >
              {COMPARE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </div>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <button
            type="button"
            onClick={onExportCsv}
            disabled={isLoading}
            style={{
              background: 'var(--p-surface-2)',
              border: '1px solid var(--p-border)',
              color: 'var(--p-text)',
              padding: '8px 14px',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 600,
              cursor: isLoading ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-sans)',
              opacity: isLoading ? 0.6 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <i className="fa-solid fa-download" style={{ fontSize: 11 }} />
            Export CSV
          </button>
        </div>
      </div>

      {showWarning && (
        <div
          role="alert"
          style={{
            background: 'rgba(245, 158, 11, 0.08)',
            border: '1px solid rgba(245, 158, 11, 0.35)',
            color: 'var(--p-text)',
            padding: '10px 14px',
            borderRadius: 10,
            fontSize: 12,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span>
            <i className="fa-solid fa-triangle-exclamation" style={{ marginRight: 8, color: 'var(--p-warning)' }} />
            Esta consulta cubre todos los orgs. Puede tomar 10-20 segundos.
          </span>
          <button
            type="button"
            onClick={() => setBannerDismissed(true)}
            aria-label="Cerrar aviso"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--p-muted)',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            <i className="fa-solid fa-xmark" />
          </button>
        </div>
      )}
    </div>
  )
}
