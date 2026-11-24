import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  suscripcionesApi, ESTADOS, ETIQUETA_ESTADO, fechaCorta, num,
  type EstadoSuscripcion, type FilaSuscripcion, type ListaSuscripciones,
} from '../../api/suscripciones'
import { formatCurrency } from '../../utils/currency'
import { toast } from '../../store/toastStore'
import { PlatformPageShell } from '../../components/platform/PlatformPageShell'
import { KPICard } from '../../components/platform/KPICard'
import { DataTable, DataTableColumn } from '../../components/platform/DataTable'
import { PildoraEstado } from './org/SeccionSuscripcion'

/**
 * `/platform/suscripciones` — cartera de lo que Atlas le cobra a cada tienda
 * (megaplan F3). Los totales son de toda la cartera; el filtro solo recorta
 * la lista. El detalle, los cargos y el registro de pagos viven en la ficha
 * de cada organización.
 */
const chip = (activo: boolean): React.CSSProperties => ({
  display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 12px', borderRadius: 999,
  background: activo ? 'var(--p-accent-soft)' : 'var(--p-surface)',
  border: `1px solid ${activo ? 'var(--p-accent)' : 'var(--p-border)'}`,
  color: activo ? 'var(--p-accent)' : 'var(--p-text)',
  fontSize: 12, fontWeight: 600, cursor: 'pointer',
})

export function PlatformSuscripciones() {
  const navigate = useNavigate()
  const [estado, setEstado] = useState<EstadoSuscripcion | null>(null)
  const [datos, setDatos] = useState<ListaSuscripciones | null>(null)
  const [cargando, setCargando] = useState(true)

  useEffect(() => {
    let vivo = true
    setCargando(true)
    suscripcionesApi.listar(estado ? { estado } : undefined)
      .then((d) => { if (vivo) setDatos(d) })
      .catch((e) => toast.error(e?.response?.data?.detail || 'No se pudieron cargar las suscripciones'))
      .finally(() => { if (vivo) setCargando(false) })
    return () => { vivo = false }
  }, [estado])

  const t = datos?.totales
  const columnas: DataTableColumn<FilaSuscripcion>[] = [
    { key: 'org', label: 'Organización', accessor: (f) => f.organizacion, sortValue: (f) => f.organizacion.toLowerCase(), sortable: true },
    { key: 'plan', label: 'Plan', accessor: (f) => f.plan_nombre, sortValue: (f) => f.plan_nombre, sortable: true },
    {
      key: 'precio', label: 'Precio pactado', sortable: true, sortValue: (f) => num(f.precio_mxn),
      accessor: (f) => `${formatCurrency(num(f.precio_mxn))} ${f.periodicidad === 'anual' ? '/año' : '/mes'}`,
    },
    { key: 'renovacion', label: 'Próxima renovación', accessor: (f) => fechaCorta(f.proxima_renovacion), sortValue: (f) => f.proxima_renovacion, sortable: true },
    { key: 'estado', label: 'Estado', accessor: (f) => <PildoraEstado estado={f.estado} />, sortValue: (f) => f.estado, sortable: true },
    {
      key: 'vencido', label: 'Saldo vencido', sortable: true, sortValue: (f) => num(f.saldo_vencido),
      accessor: (f) => (
        <span style={{ color: num(f.saldo_vencido) > 0 ? 'var(--p-danger)' : 'var(--p-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {formatCurrency(num(f.saldo_vencido))}
        </span>
      ),
    },
    {
      key: 'por_vencer', label: 'Por vencer', sortable: true, sortValue: (f) => num(f.saldo_por_vencer),
      accessor: (f) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(num(f.saldo_por_vencer))}</span>,
    },
  ]

  return (
    <PlatformPageShell
      breadcrumb="Platform / Suscripciones"
      title="Suscripciones"
      kpis={t && (
        <>
          <KPICard label="Ingreso mensual recurrente" value={formatCurrency(num(t.ingreso_mensual_recurrente))} icon="fa-arrows-rotate" />
          <KPICard label="Cartera vencida" value={formatCurrency(num(t.cartera_vencida))} icon="fa-triangle-exclamation"
                   accent={num(t.cartera_vencida) > 0 ? 'danger' : undefined} />
          <KPICard label="Por vencer" value={formatCurrency(num(t.por_vencer))} icon="fa-hourglass-half"
                   accent={num(t.por_vencer) > 0 ? 'warning' : undefined} />
          <KPICard label="Sin suscripción" value={t.sin_suscripcion} icon="fa-building" />
        </>
      )}
    >
      <div role="group" aria-label="Filtrar por estado" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" style={chip(estado === null)} aria-pressed={estado === null} onClick={() => setEstado(null)}>
          Todas
        </button>
        {ESTADOS.map((e) => (
          <button key={e} type="button" style={chip(estado === e)} aria-pressed={estado === e} onClick={() => setEstado(e)}>
            {ETIQUETA_ESTADO[e]}{t ? ` · ${t.por_estado[e] ?? 0}` : ''}
          </button>
        ))}
      </div>

      {cargando && !datos ? (
        <div style={{ background: 'var(--p-surface)', border: '1px solid var(--p-border)', borderRadius: 6, padding: '3rem', textAlign: 'center', color: 'var(--p-muted)' }}>
          Cargando suscripciones…
        </div>
      ) : (
        <DataTable
          data={datos?.items ?? []}
          columns={columnas}
          rowKey={(f) => f.organization_id}
          searchable
          searchKeys={(f) => `${f.organizacion} ${f.plan_nombre} ${f.plan}`}
          onRowClick={(f) => navigate(`/platform/organizations/${f.organization_id}`)}
          emptyMessage={estado ? `Ninguna suscripción ${ETIQUETA_ESTADO[estado].toLowerCase()}.` : 'Aún no hay suscripciones. Dalas de alta desde la ficha de cada organización.'}
          csvFilename="suscripciones"
          csvRow={(f) => ({
            organizacion: f.organizacion, plan: f.plan, precio_mxn: f.precio_mxn, periodicidad: f.periodicidad,
            proxima_renovacion: f.proxima_renovacion, estado: f.estado,
            saldo_vencido: f.saldo_vencido, saldo_por_vencer: f.saldo_por_vencer,
          })}
        />
      )}
    </PlatformPageShell>
  )
}
