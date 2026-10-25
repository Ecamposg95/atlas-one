// frontend/src/pages/sales/Returns.tsx
import { useEffect, useState, useCallback, useRef } from 'react'
import { ReturnsBranchView } from '../../components/branch/ReturnsBranchView'
import {
  returnsApi, type ReturnDocument, type ReturnStatus,
  returnLabel, returnRequestedBy, returnApprovedBy, returnBranchName,
} from '../../api/returns'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { confirm } from '../../components/ui/ConfirmDialog'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { Badge } from '../../components/ui/Badge'
import { Spinner } from '../../components/ui/Spinner'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useSucursalesVendibles } from '../../hooks/useSucursalesVendibles'
import { esRolHq } from '../../utils/rolesHq'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { estadoDevolucion } from '../../utils/enumsEspanol'
import { PRESETS, presetActivo, rangoPreset, type ClavePreset, type Rango } from '../reports/presetsReportes'

/**
 * Devoluciones (`/returns`). Una sola pantalla (Fase 3 del admin, spec
 * 2026-10-23 §4.1): la cajera usa el asistente de sucursal; gerente,
 * administrador y dueño ven la bandeja (pendientes e historial). Los roles de
 * oficina eligen sucursal cuando hay más de una que vende. Sustituye a
 * `pages/hq/HQReturns.tsx`. Solo tokens `dax-*` (coloresPorTokens, LIMPIOS).
 */

// Tope del backend (`le=200`); el default de 50 recortaría pendientes viejos.
const TOPE = 200
const CAN_APPROVE = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE']
type Pestana = 'pending' | 'history'

const fechaCorta = (iso: string) => new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })
const statusVariant = (s: ReturnStatus): 'green' | 'red' | 'yellow' =>
  (s === 'APPROVED' ? 'green' : s === 'REJECTED' ? 'red' : 'yellow')
const badgeEstado = (s: ReturnStatus) => <Badge variant={statusVariant(s)}>{estadoDevolucion(s)}</Badge>
// Saca el `detail` de FastAPI (409/422 traen mensajes accionables) o cae al respaldo.
const detalle = (err: unknown, respaldo: string) =>
  errorDetailText((err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail, respaldo)

export function Returns() {
  const role = useAuthStore((s) => s.user?.role)
  if (role === 'CAJERO') return <ReturnsBranchView />
  return <ReturnsAdminView />
}

// Separado para no romper Rules of Hooks: el return condicional de arriba
// no puede convivir con hooks en el mismo componente.
function ReturnsAdminView() {
  const role = useAuthStore((s) => s.user?.role)
  const canApprove = CAN_APPROVE.includes(role ?? '')
  const esHq = esRolHq(role)
  const esTelefono = useEsTelefono()
  const sucursales = useSucursalesVendibles(esHq)
  const conSucursales = esHq && sucursales.length > 1
  // El gerente no elige sucursal, pero `/returns/` le devuelve toda la organización:
  // la columna "Sucursal" le dice de dónde viene cada fila.
  const muestraSucursal = conSucursales || role === 'GERENTE'
  const [sucursal, setSucursal] = useState<number | ''>('')

  const [tab, setTab] = useState<Pestana>('pending')
  // El periodo acota el historial; los pendientes se piden siempre completos: una
  // devolución de hace dos meses sigue por aprobar aunque el rango no la cubra.
  const [rango, setRango] = useState<Rango>(() => rangoPreset('30d'))
  const [desde, setDesde] = useState(rango.inicio)
  const [hasta, setHasta] = useState(rango.fin)
  const [presetElegido, setPresetElegido] = useState<ClavePreset | null>('30d')
  const [pending, setPending] = useState<ReturnDocument[]>([])
  const [history, setHistory] = useState<ReturnDocument[]>([])
  // Pendientes e Historial se piden por separado: si una falla, la otra bandeja sigue a la vista.
  const [loadingPend, setLoadingPend] = useState(true)
  const [loadingHist, setLoadingHist] = useState(true)
  const [errorPend, setErrorPend] = useState<string | null>(null)
  const [errorHist, setErrorHist] = useState<string | null>(null)
  // Un contador por bandeja: una respuesta vieja (otra sucursal o periodo) no pisa a la nueva.
  const reqPend = useRef(0)
  const reqHist = useRef(0)
  const [selected, setSelected] = useState<ReturnDocument | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  // `branch_id` solo cuando un rol de oficina eligió sucursal. Sin él, `/returns/`
  // (`resolver_ambito`; HQ_ROLES incluye GERENTE) da toda la organización a admin,
  // dueño y gerente —como hoy— y a la cajera la suya.
  const loadPendientes = useCallback(async (bid: number | '') => {
    const mio = ++reqPend.current
    setLoadingPend(true)
    setErrorPend(null)
    try {
      const data = await returnsApi.list({ ...(bid !== '' ? { branch_id: bid } : {}), status: 'PENDING', limit: TOPE })
      if (mio !== reqPend.current) return
      setPending(data)
    } catch (err) {
      if (mio !== reqPend.current) return
      // Un fallo no se disfraza de "sin devoluciones".
      setPending([])
      setErrorPend(detalle(err, 'No se pudieron cargar las devoluciones. Vuelve a intentar en unos segundos.'))
    } finally {
      if (mio === reqPend.current) setLoadingPend(false)
    }
  }, [])

  const loadHistorial = useCallback(async (bid: number | '', r: Rango) => {
    const mio = ++reqHist.current
    setLoadingHist(true)
    setErrorHist(null)
    try {
      const data = await returnsApi.list({ ...(bid !== '' ? { branch_id: bid } : {}), start_date: r.inicio, end_date: r.fin, limit: TOPE })
      if (mio !== reqHist.current) return
      setHistory(data)
    } catch (err) {
      if (mio !== reqHist.current) return
      setHistory([])
      setErrorHist(detalle(err, 'No se pudo cargar el historial de devoluciones. Vuelve a intentar en unos segundos.'))
    } finally {
      if (mio === reqHist.current) setLoadingHist(false)
    }
  }, [])

  // Pendientes: solo cambia con la sucursal. Historial: con la sucursal y el periodo
  // (cambiar el preset ya no vuelve a pedir los pendientes).
  useEffect(() => { loadPendientes(sucursal) }, [loadPendientes, sucursal])
  useEffect(() => { loadHistorial(sucursal, rango) }, [loadHistorial, sucursal, rango])
  const recargar = () => Promise.all([loadPendientes(sucursal), loadHistorial(sucursal, rango)])

  const aplicar = (r: Rango, clave: ClavePreset | null) => {
    setRango(r); setDesde(r.inicio); setHasta(r.fin); setPresetElegido(clave)
  }
  const aplicarFechas = () => {
    if (!desde || !hasta) { toast.error('Elige la fecha inicial y la final.'); return }
    if (desde > hasta) { toast.error('La fecha inicial no puede ser mayor que la final.'); return }
    aplicar({ inicio: desde, fin: hasta }, null)
  }
  // En el día 1 «Este mes» y «Hoy» coinciden: manda el que se pulsó.
  const activo: ClavePreset | null = presetActivo(rango) && presetElegido ? presetElegido : presetActivo(rango)

  const handleApprove = async (id: string, force = false) => {
    setActionLoading(true)
    try {
      await returnsApi.approve(id, force)
      await recargar()
      setSelected(null)
      toast.success('Devolución aprobada')
    } catch (err) {
      const texto = detalle(err, 'Error al aprobar la devolución')
      // R-3: el backend rechaza efectivo > $10,000 sin force=true. Se confirma con el
      // diálogo de la app (Esc cancela, el foco arranca en Cancelar), no con el del navegador.
      if (!force && /EFECTIVO de monto alto|force=True/i.test(texto)) {
        const ok = await confirm({
          title: 'Confirmar reembolso en efectivo',
          message: texto,
          confirmText: 'Sí, reembolsar en efectivo',
          cancelText: 'Cancelar',
          variant: 'danger',
        })
        if (ok) {
          setActionLoading(false)
          return await handleApprove(id, true)
        }
      } else {
        toast.error(texto)
      }
    } finally { setActionLoading(false) }
  }

  const handleReject = async (id: string, reason?: string) => {
    setActionLoading(true)
    try {
      await returnsApi.reject(id, reason)
      await recargar()
      setSelected(null)
      setRejectingId(null)
      setRejectReason('')
      toast.success('Devolución rechazada')
    } catch (err) {
      toast.error(detalle(err, 'Error al rechazar la devolución'))
    } finally { setActionLoading(false) }
  }

  const items = tab === 'pending' ? pending : history
  const loading = tab === 'pending' ? loadingPend : loadingHist
  const error = tab === 'pending' ? errorPend : errorHist
  const textoVacio = tab === 'pending' ? 'No hay devoluciones pendientes' : 'Sin devoluciones en este periodo'

  // Mensaje de error con reintento (en lugar de la lista vacía).
  const mensajeError = error && (
    <div role="alert" className="p-8 text-center space-y-3">
      <p className="text-sm text-dax-danger">{error}</p>
      <button type="button" onClick={() => { recargar() }} className="dax-btn-secondary text-xs">
        <i className="fa-solid fa-rotate-right" aria-hidden="true" /> Reintentar
      </button>
    </div>
  )

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-undo text-dax-accent-text text-xl" aria-hidden="true" />
            <h1 className="text-2xl font-black text-dax-text">Devoluciones</h1>
          </div>
        }
        acciones={
          <>
            {conSucursales && (
              <select
                aria-label="Sucursal"
                value={sucursal}
                onChange={(e) => setSucursal(e.target.value ? Number(e.target.value) : '')}
                className="dax-input text-xs max-w-[180px]"
              >
                <option value="">Todas las sucursales</option>
                {sucursales.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            )}
            <button type="button" onClick={() => { recargar() }} className="dax-btn-secondary text-xs">
              <i className="fa-solid fa-rotate-right" aria-hidden="true" /> Actualizar
            </button>
          </>
        }
      />

      {/* Pestañas */}
      <div className="flex gap-1 w-fit" role="group" aria-label="Bandeja">
        {(['pending', 'history'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            aria-pressed={tab === t}
            className={`${tab === t ? 'dax-btn-primary' : 'dax-btn-secondary'} text-sm max-md:min-h-[44px]`}
          >
            {t === 'pending' ? 'Pendientes' : 'Historial'}
            {t === 'pending' && pending.length > 0 && (
              <span role="img" aria-label={`${pending.length} por aprobar`} className="ml-1.5 rounded-full bg-dax-danger text-dax-on-accent text-[10px] font-black px-1.5 py-0.5">{pending.length}</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'history' && (
        <BarraFiltros
          className="!items-center"
          accion={<button type="button" onClick={aplicarFechas} className="dax-btn-primary text-xs">Aplicar</button>}
        >
          <div className="flex flex-wrap gap-1" role="group" aria-label="Periodo">
            {PRESETS.map((p) => (
              <button
                key={p.clave}
                type="button"
                onClick={() => aplicar(rangoPreset(p.clave), p.clave)}
                aria-pressed={activo === p.clave}
                className={`${activo === p.clave ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}
              >
                {p.etiqueta}
              </button>
            ))}
          </div>
          <ParFechas>
            <input type="date" aria-label="Desde" value={desde} onChange={(e) => setDesde(e.target.value)} className="dax-input w-36 text-xs" />
            <input type="date" aria-label="Hasta" value={hasta} onChange={(e) => setHasta(e.target.value)} className="dax-input w-36 text-xs" />
          </ParFechas>
        </BarraFiltros>
      )}

      {esTelefono ? (
        error && !loading ? <DaxCard padding={false}>{mensajeError}</DaxCard> : (
        <ListaTarjetas cargando={loading} vacio={items.length === 0} textoVacio={textoVacio}>
          {items.map((r) => (
            <TarjetaFila
              key={r.id}
              titulo={returnLabel(r)}
              subtitulo={[fechaCorta(r.created_at), muestraSucursal ? (returnBranchName(r) ?? '—') : null, returnRequestedBy(r)].filter(Boolean).join(' · ')}
              importe={<span className="text-dax-danger">{formatCurrency(r.total_refunded)}</span>}
              estado={badgeEstado(r.status)}
              datos={[{ etiqueta: 'Motivo', valor: r.reason }]}
              onClick={() => setSelected(r)}
              acciones={
                <button type="button" onClick={() => setSelected(r)} className="dax-btn-secondary text-xs">
                  <i className="fa-solid fa-eye" aria-hidden="true" /> Ver detalle
                </button>
              }
            />
          ))}
        </ListaTarjetas>
        )
      ) : (
        <DaxCard padding={false}>
          {loading ? <Spinner text="Cargando..." /> : error ? mensajeError : items.length === 0 ? (
            <div className="p-12 text-center text-dax-faint">{textoVacio}</div>
          ) : (
            <TablaDesplazable sangrado={false}>
              <table className="dax-table w-full">
                <thead>
                  <tr>
                    <th>Ticket</th>
                    {muestraSucursal && <th>Sucursal</th>}
                    <th>Solicitó</th>
                    <th>Fecha</th>
                    <th>Motivo</th>
                    <th className="text-right">Total</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r) => (
                    <tr key={r.id}>
                      <td className="font-mono text-dax-accent-text text-xs">{returnLabel(r)}</td>
                      {muestraSucursal && <td className="text-xs text-dax-muted">{returnBranchName(r) ?? '—'}</td>}
                      <td className="text-sm">{returnRequestedBy(r)}</td>
                      <td className="text-xs text-dax-muted">{fechaCorta(r.created_at)}</td>
                      <td className="text-xs max-w-[160px] truncate">{r.reason}</td>
                      <td className="text-right font-semibold text-dax-danger">{formatCurrency(r.total_refunded)}</td>
                      <td>{badgeEstado(r.status)}</td>
                      <td>
                        <button
                          type="button"
                          onClick={() => setSelected(r)}
                          className="dax-btn-icon text-dax-muted hover:text-dax-text text-xs"
                          aria-label={`Ver detalle de ${returnLabel(r)}`}
                        >
                          <i className="fa-solid fa-eye" aria-hidden="true" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TablaDesplazable>
          )}
        </DaxCard>
      )}

      {/* Detalle: Modal del kit con Aprobar/Rechazar en el pie. */}
      {selected && (
        <Modal
          open
          onClose={() => setSelected(null)}
          size="lg"
          title="Detalle de devolución"
          footer={canApprove && selected.status === 'PENDING' ? (
            <>
              <button type="button" onClick={() => handleApprove(selected.id)} disabled={actionLoading} className="dax-btn-primary flex-1 justify-center">
                {actionLoading ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : <><i className="fa-solid fa-check" aria-hidden="true" /> Aprobar</>}
              </button>
              <button type="button" onClick={() => { setRejectingId(selected.id); setRejectReason('') }} disabled={actionLoading} className="dax-btn-danger flex-1 justify-center">
                <i className="fa-solid fa-xmark" aria-hidden="true" /> Rechazar
              </button>
            </>
          ) : undefined}
        >
          <div className="space-y-2 text-sm mb-4">
            <div className="flex justify-between"><span className="text-dax-muted">Ticket</span><span className="font-mono text-dax-accent-text">{returnLabel(selected)}</span></div>
            {muestraSucursal && <div className="flex justify-between"><span className="text-dax-muted">Sucursal</span><span>{returnBranchName(selected) ?? '—'}</span></div>}
            <div className="flex justify-between"><span className="text-dax-muted">Solicitó</span><span>{returnRequestedBy(selected)}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Motivo</span><span className="text-right max-w-[60%]">{selected.reason}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Estado</span>{badgeEstado(selected.status)}</div>
            {selected.supervisor && <div className="flex justify-between"><span className="text-dax-muted">Aprobó</span><span>{returnApprovedBy(selected)}</span></div>}
          </div>

          {selected.items?.length > 0 && (
            <div className="border-t border-dax-border-dim pt-4 mb-4">
              <p className="text-[10px] font-bold text-dax-muted uppercase tracking-widest mb-2">Artículos</p>
              {/* Sin envoltorio, la tabla arrastraba de lado todo el modal. */}
              <TablaDesplazable sangrado={false}>
                <table className="dax-table w-full text-xs">
                  <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Reembolso</th><th>Stock</th></tr></thead>
                  <tbody>
                    {selected.items.map((item, i) => (
                      <tr key={i}>
                        <td>{item.variant?.product_name ?? item.variant?.sku ?? '—'}</td>
                        <td className="text-right">{item.quantity}</td>
                        <td className="text-right text-dax-danger">{formatCurrency(Number(item.refund_amount))}</td>
                        <td><Badge variant={item.is_inventory_reentry ? 'green' : 'red'}>{item.is_inventory_reentry ? 'Regresa' : 'Merma'}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TablaDesplazable>
            </div>
          )}

          <div className="flex justify-between font-black text-dax-text border-t border-dax-border-dim pt-3">
            <span>Total reembolso</span><span className="text-dax-danger">{formatCurrency(selected.total_refunded)}</span>
          </div>
        </Modal>
      )}

      {/* Rechazo con motivo. */}
      {rejectingId && (
        <Modal
          open
          onClose={() => setRejectingId(null)}
          size="sm"
          title={<span><i className="fa-solid fa-circle-exclamation mr-2 text-dax-danger" aria-hidden="true" />Rechazar devolución</span>}
          footer={
            <>
              <button type="button" onClick={() => setRejectingId(null)} className="dax-btn-secondary flex-1" disabled={actionLoading}>
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => handleReject(rejectingId, rejectReason.trim() || undefined)}
                className="dax-btn-danger flex-1 justify-center"
                disabled={actionLoading}
              >
                {actionLoading ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : <><i className="fa-solid fa-xmark" aria-hidden="true" /> Confirmar rechazo</>}
              </button>
            </>
          }
        >
          <label htmlFor="motivo-rechazo" className="text-[10px] font-bold uppercase tracking-wider block mb-1 text-dax-muted">
            Motivo (opcional)
          </label>
          <textarea
            id="motivo-rechazo"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            className="dax-input w-full"
            rows={3}
            placeholder="Ej: Producto fuera de plazo de devolución, ticket duplicado..."
            autoFocus
          />
        </Modal>
      )}
    </div>
  )
}
