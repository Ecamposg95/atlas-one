import { useEffect, useState } from 'react'
import { SkeletonState } from '../../../components/platform/v2/SkeletonState'
import type { AttentionLists, BranchOverviewRow } from '../../../types/platformOverview'
import { AttentionPanel } from './AttentionPanel'
import { OrgKpis } from './OrgKpis'
import { OrgTable } from './OrgTable'
import { UnitDrawer } from './UnitDrawer'
import { staleLabel } from './orgFormat'
import { useOrgOverview } from './useOrgOverview'

interface Props {
  /** La organización que se está mirando; `null` mientras no hay ninguna elegida. */
  orgId: number | null
  /** Los pendientes de TODAS las organizaciones (los carga la página). */
  attention: AttentionLists | null
  /** Saltar a otra organización desde un pendiente de la tira. */
  onPickOrg: (orgId: number) => void
}

/** El día de UNA organización: sus totales, sus sucursales y, al lado, los
 *  pendientes de todas (lo único que cruza clientes). */
export function OrgBoard({ orgId, attention, onPickOrg }: Props) {
  const [selected, setSelected] = useState<BranchOverviewRow | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const { data, loading, error, lastUpdatedAt, refresh } = useOrgOverview(orgId)

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  useEffect(() => { setSelected(null) }, [orgId])

  const stale = staleLabel(lastUpdatedAt, now)

  if (orgId === null) {
    return <div className="card"><div className="body">Elige una organización para ver su día.</div></div>
  }
  if (!data) {
    if (!loading && error) {
      return (
        <div className="card">
          <div className="body">
            No se pudo cargar el tablero: {error}.{' '}
            <button type="button" className="btn ghost" onClick={() => refresh()}>Reintentar</button>
          </div>
        </div>
      )
    }
    return <SkeletonState />
  }
  // `data` puede quedarse un instante con la organización anterior mientras la
  // nueva petición vuela (ver useOrgOverview) — sin este guard se ven las
  // sucursales de un cliente bajo el nombre de otro.
  const matches = data.organization_id === orgId

  return (
    <>
      <div className="pv2-org-toolbar">
        <span className="hint">
          {data.organization_name} · {data.date} · {data.rows.length} sucursales
        </span>
        <span>
          {error && stale && (
            <span className="pv2-stale">
              <i className="fa-solid fa-triangle-exclamation" /> {stale}
            </span>
          )}
          <button type="button" className="btn ghost" onClick={() => refresh()} aria-label="Refrescar tablero">
            <i className="fa-solid fa-arrow-rotate-right" /> Refrescar
          </button>
        </span>
      </div>
      {matches ? <OrgKpis totals={data.totals} /> : <SkeletonState />}
      <div className="pv2-org-layout">
        {matches
          ? <OrgTable rows={data.rows} onRowClick={setSelected} />
          : <SkeletonState />}
        {attention && <AttentionPanel attention={attention} variant="panel" onPickOrg={onPickOrg} />}
      </div>
      <UnitDrawer row={selected} onClose={() => setSelected(null)} />
    </>
  )
}
