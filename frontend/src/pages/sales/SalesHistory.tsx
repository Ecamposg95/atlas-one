// frontend/src/pages/sales/SalesHistory.tsx
import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { salesApi, type SalesStats } from '../../api/sales'
import { printerApi } from '../../api/printer'
import { usePOSStore } from '../../store/posStore'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { KpiCard } from '../../components/ui/KpiCard'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useSucursalesVendibles } from '../../hooks/useSucursalesVendibles'
import { esRolHq } from '../../utils/rolesHq'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { ReturnModal } from '../../components/pos/modals/ReturnModal'
import { ReprintPinModal } from '../../components/pos/modals/ReprintPinModal'
import { formatCurrency } from '../../utils/currency'
import { toast } from '../../store/toastStore'
import { errorDetailText } from '../../utils/errorDetail'
import { mensajeReimpresion, pinBloqueado, pinIncorrecto, requierePin } from '../../utils/reimpresion'
import { formatPct } from '../pos/cardSurcharge'
import { PRESETS, presetActivo, rangoPreset, type ClavePreset, type Rango } from '../reports/presetsReportes'

/**
 * Ventas (`/sales`). Una sola pantalla para todos los roles (Fase 3 del admin,
 * spec 2026-10-23 §4.1): cajera y gerente ven su sucursal (el backend la
 * impone); administrador y dueño ven toda la organización y, con más de una
 * sucursal que vende, un selector. Sustituye a `pages/hq/HQSalesLog.tsx`.
 * Solo tokens `dax-*` (coloresPorTokens.test.ts, LIMPIOS).
 */

const STATUS_LABELS: Record<string, string> = {
  PAID:             'Pagado',
  CANCELLED:        'Cancelado',
  REFUNDED_PARTIAL: 'Dev. parcial',
  REFUNDED_TOTAL:   'Dev. total',
  PENDING:          'Pendiente',
  DRAFT:            'Borrador',
}

const METHOD_LABELS: Record<string, string> = {
  CASH:         'Efectivo',
  CARD:         'Tarjeta',
  TRANSFER:     'Transferencia',
  STORE_CREDIT: 'Crédito tienda',
  CHECK:        'Cheque',
  OTHER:        'Otro',
  MIXED:        'Mixto',
}

// Por defecto solo ventas realizadas (PAID, REFUNDED_*) y CANCELLED: PENDING y
// DRAFT son créditos abiertos / borradores que confunden a la cajera ("¿vendí o no?").
const ESTADOS_CERRADOS = 'PAID,REFUNDED_PARTIAL,REFUNDED_TOTAL,CANCELLED'
const LIMIT = 100

// Formatos de la fila: los comparten la tabla (escritorio) y la tarjeta (teléfono).
const fechaVenta = (s: SalesDocument) =>
  new Date(s.created_at).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
const clienteVenta = (s: SalesDocument) =>
  s.customer_name ?? <span className="text-dax-faint italic">Público general</span>
const pagosVenta = (s: SalesDocument) =>
  s.payments?.map((p, i) => (
    <span key={i} className="dax-badge dax-badge-blue mr-1">{METHOD_LABELS[p.method] ?? p.method}</span>
  ))
const sePuedeDevolver = (s: SalesDocument) => s.status === 'PAID' || s.status === 'REFUNDED_PARTIAL'
// Estados reales del backend: PAID / CANCELLED / REFUNDED_* / PENDING / DRAFT
const statusVariant = (s: string): 'green' | 'red' | 'blue' | 'yellow' =>
  s === 'PAID' ? 'green' : s === 'CANCELLED' ? 'red' : s.startsWith('REFUNDED') ? 'blue' : 'yellow'
const badgeEstado = (s: SalesDocument) => <Badge variant={statusVariant(s.status)}>{STATUS_LABELS[s.status] ?? s.status}</Badge>

export function SalesHistory() {
  const printerName = usePOSStore((s) => s.printerName)
  const esHq = esRolHq(useAuthStore((s) => s.user?.role))
  const esTelefono = useEsTelefono()
  // Solo los roles de oficina piden la lista; el selector sale con más de una sucursal que vende.
  const sucursales = useSucursalesVendibles(esHq)
  const conSucursales = esHq && sucursales.length > 1
  const [sucursal, setSucursal] = useState<number | ''>('')

  const [sales, setSales] = useState<SalesDocument[]>([])
  const [stats, setStats] = useState<SalesStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Contador de peticiones: una respuesta vieja (otro periodo o sucursal) no pisa a la nueva.
  const reqId = useRef(0)
  // Arranca en Hoy, como la pantalla HQ que sustituye.
  const [rango, setRango] = useState<Rango>(() => rangoPreset('hoy'))
  const [desde, setDesde] = useState(rango.inicio)
  const [hasta, setHasta] = useState(rango.fin)
  // En el día 1 del mes «Este mes» y «Hoy» son el mismo rango: se recuerda cuál se pulsó.
  const [presetElegido, setPresetElegido] = useState<ClavePreset | null>('hoy')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [busqueda, setBusqueda] = useState('')
  // HQ veía PENDING/DRAFT por defecto (HQSalesLog); la cajera no (SalesHistory). Cada rol conserva su costumbre.
  const [includeOpenStates, setIncludeOpenStates] = useState(esHq)
  const [selected, setSel] = useState<SalesDocument | null>(null)
  const [returnSale, setReturnSale] = useState<SalesDocument | null>(null)
  const [reprinting, setReprinting] = useState(false)
  // Venta cuya reimpresión espera el PIN de un supervisor (428 del backend).
  const [ventaPorAutorizar, setVentaPorAutorizar] = useState<SalesDocument | null>(null)

  /**
   * Reimprime un ticket. El backend exige rol gerencial o el PIN de un
   * supervisor (428) salvo que sea una venta propia recién cobrada, así que el
   * primer intento va sin PIN y solo se pide cuando hace falta.
   *
   * Devuelve el mensaje de error si el PIN no sirvió —el modal lo muestra y
   * deja reintentar— o null cuando ya no hay nada pendiente.
   */
  const reprintTicket = async (sale: SalesDocument, pin?: string): Promise<string | null> => {
    if (!printerName) {
      toast.error('Configura una impresora en /printer-settings primero')
      return null
    }
    setReprinting(true)
    try {
      const b64 = await printerApi.getTicketBase64(sale.id, pin)
      if (b64) await printerApi.printViaAgent(printerName, b64)
      toast.success('Ticket enviado a la impresora')
      setVentaPorAutorizar(null)
      return null
    } catch (e: unknown) {
      if (requierePin(e)) {
        setVentaPorAutorizar(sale)
        return null
      }
      // Un PIN equivocado deja el modal abierto para reintentar. El bloqueo por
      // intentos lo cierra: hay que esperar, insistir no sirve. Y cualquier otro
      // conflicto (venta cancelada, sin acceso) también lo cierra con aviso.
      if (pin && pinIncorrecto(e) && !pinBloqueado(e)) return mensajeReimpresion(e)
      toast.error(mensajeReimpresion(e))
      setVentaPorAutorizar(null)
      return null
    } finally {
      setReprinting(false)
    }
  }

  const load = useCallback(async (r: Rango, pg: number, bid: number | '') => {
    const mio = ++reqId.current
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = { start_date: r.inicio, end_date: r.fin, limit: LIMIT, skip: pg * LIMIT }
      // Se manda por si el backend lo respeta; el filtro de abajo (en cliente) siempre aplica.
      if (!includeOpenStates) params.statuses = ESTADOS_CERRADOS
      // `branch_id` solo cuando un rol de oficina eligió sucursal. Sin él, el backend
      // da toda la organización a HQ y su sucursal a cajera y gerente (regla de la Fase 1).
      if (bid !== '') params.branch_id = bid
      const [listRes, statsRes] = await Promise.allSettled([
        salesApi.list(params),
        salesApi.getStats({ start_date: r.inicio, end_date: r.fin, ...(bid !== '' ? { branch_id: bid } : {}) }),
      ])
      if (mio !== reqId.current) return
      if (listRes.status === 'fulfilled') {
        let items = listRes.value?.items ?? []
        // El backend no filtra por `statuses`: aquí se quitan abiertas y borradores.
        if (!includeOpenStates) items = items.filter((s) => !['PENDING', 'DRAFT'].includes(String(s.status)))
        setSales(items)
        setTotal(listRes.value?.total ?? items.length)
      } else {
        // Un fallo no se disfraza de "sin ventas".
        setSales([])
        setTotal(0)
        const e = listRes.reason as { response?: { data?: { detail?: unknown } } } | undefined
        setError(errorDetailText(e?.response?.data?.detail, 'No se pudieron cargar las ventas. Vuelve a intentar en unos segundos.'))
      }
      setStats(statsRes.status === 'fulfilled' ? statsRes.value : null)
    } finally {
      if (mio === reqId.current) setLoading(false)
    }
  }, [includeOpenStates])

  useEffect(() => { load(rango, page, sucursal) }, [load, rango, page, sucursal])

  const aplicar = (r: Rango, clave: ClavePreset | null) => {
    setRango(r); setDesde(r.inicio); setHasta(r.fin); setPresetElegido(clave); setPage(0)
  }
  const aplicarFechas = () => {
    if (desde > hasta) { toast.error('La fecha inicial no puede ser mayor que la final.'); return }
    aplicar({ inicio: desde, fin: hasta }, null)
  }
  const activo: ClavePreset | null = presetActivo(rango) && presetElegido ? presetElegido : presetActivo(rango)

  // Buscador de folio/cliente sobre la página cargada (venía de la pantalla HQ; sirve a todos).
  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    if (!q) return sales
    return sales.filter((s) => saleLabel(s).toLowerCase().includes(q) || (s.customer_name ?? '').toLowerCase().includes(q))
  }, [sales, busqueda])
  const pages = Math.ceil(total / LIMIT)
  const metodoTop = useMemo(
    () => Object.entries(stats?.payment_methods ?? {}).sort((a, b) => b[1] - a[1])[0]?.[0],
    [stats],
  )

  // Ver / Reimprimir / Devolver: los mismos botones en la fila y en la tarjeta.
  // `stopPropagation` evita que el toque abra además el detalle de la fila.
  const accionesVenta = (s: SalesDocument) => (
    <>
      <button type="button" onClick={(e) => { e.stopPropagation(); setSel(s) }} className="dax-btn-secondary text-xs" title="Ver detalle">
        <i className="fa-solid fa-eye" aria-hidden="true" /> Ver
      </button>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); reprintTicket(s) }}
        disabled={reprinting || !printerName}
        className="dax-btn-secondary text-xs disabled:opacity-40 disabled:cursor-not-allowed"
        title={printerName ? 'Reimprimir ticket' : 'Configura una impresora'}
      >
        <i className="fa-solid fa-print" aria-hidden="true" /> Reimprimir
      </button>
      {sePuedeDevolver(s) && (
        <button type="button" onClick={(e) => { e.stopPropagation(); setReturnSale(s) }} className="dax-btn-danger text-xs" title="Iniciar devolución">
          <i className="fa-solid fa-undo" aria-hidden="true" /> Devolver
        </button>
      )}
    </>
  )

  // Paginación: una sola, debajo de la tabla (escritorio) o de las tarjetas (teléfono).
  const paginacion = pages > 1 && (
    <div className={`flex items-center justify-between px-4 py-3 ${esTelefono ? '' : 'border-t border-dax-border-dim'}`}>
      <button type="button" onClick={() => setPage(page - 1)} disabled={page === 0} className="dax-btn-secondary text-xs disabled:opacity-40 max-md:min-h-[44px]">← Anterior</button>
      <span className="text-dax-muted text-xs">Pág. {page + 1} / {pages} · {total} registros</span>
      <button type="button" onClick={() => setPage(page + 1)} disabled={page >= pages - 1} className="dax-btn-secondary text-xs disabled:opacity-40 max-md:min-h-[44px]">Siguiente →</button>
    </div>
  )

  // Mensaje de error con reintento (en lugar de la lista vacía).
  const mensajeError = error && (
    <div role="alert" className="p-8 text-center space-y-3">
      <p className="text-sm text-dax-danger">{error}</p>
      <button type="button" onClick={() => load(rango, page, sucursal)} className="dax-btn-secondary text-xs">
        <i className="fa-solid fa-rotate-right" aria-hidden="true" /> Reintentar
      </button>
    </div>
  )

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-receipt text-dax-accent-text text-xl" aria-hidden="true" />
            <h1 className="text-2xl font-black text-dax-text">Ventas</h1>
          </div>
        }
      />

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <KpiCard etiqueta="Total" valor={formatCurrency(stats.total_sales)} tono="success" data-testid="kpi-total" />
          <KpiCard etiqueta="Transacciones" valor={String(stats.total_transactions)} />
          <KpiCard etiqueta="Ticket promedio" valor={formatCurrency(stats.average_ticket)} />
          <KpiCard etiqueta="Método top" valor={metodoTop ? (METHOD_LABELS[metodoTop] ?? metodoTop) : '—'} />
          <KpiCard etiqueta="Devoluciones" valor={`${stats.refund_count ?? 0} · ${formatCurrency(stats.refund_total ?? 0)}`} tono="danger" />
          <KpiCard etiqueta="Hora pico" valor={stats.peak_hour ?? '—'} />
        </div>
      )}

      {/* `!items-center` conserva la alineación de hoy (BarraFiltros trae items-end). */}
      <BarraFiltros
        className="!items-center"
        accion={
          <button type="button" onClick={aplicarFechas} className="dax-btn-primary text-xs">
            <i className="fa-solid fa-search" aria-hidden="true" /> Filtrar
          </button>
        }
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
        {conSucursales && (
          <select
            aria-label="Sucursal"
            value={sucursal}
            onChange={(e) => { setSucursal(e.target.value ? Number(e.target.value) : ''); setPage(0) }}
            className="dax-input text-xs max-w-[180px]"
          >
            <option value="">Todas las sucursales</option>
            {sucursales.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
        <input
          type="search"
          aria-label="Buscar folio o cliente"
          placeholder="Buscar folio o cliente..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="dax-input text-xs w-44"
        />
        <label className="flex items-center gap-1.5 text-[10px] text-dax-muted cursor-pointer max-md:min-h-[44px]">
          <input type="checkbox" checked={includeOpenStates} onChange={(e) => { setIncludeOpenStates(e.target.checked); setPage(0) }} className="rounded" />
          Incluir abiertas/borradores
        </label>
      </BarraFiltros>

      {/* Teléfono: tarjetas; escritorio: la tabla de siempre (nunca ambos) */}
      {esTelefono ? (
        <>
          {error && !loading ? <DaxCard padding={false}>{mensajeError}</DaxCard> : (
          <ListaTarjetas cargando={loading} vacio={visibles.length === 0} textoVacio="Sin ventas en este periodo">
            {visibles.map((s) => (
              <TarjetaFila
                key={s.id}
                titulo={<span className="font-mono text-dax-accent-text">{saleLabel(s)}</span>}
                subtitulo={[fechaVenta(s), conSucursales ? s.branch_name : null].filter(Boolean).join(' · ')}
                importe={<span className="text-dax-success">{formatCurrency(s.total_amount)}</span>}
                estado={badgeEstado(s)}
                datos={[
                  { etiqueta: 'Cliente', valor: clienteVenta(s) },
                  { etiqueta: 'Pago', valor: s.payments?.length ? pagosVenta(s) : '—' },
                ]}
                acciones={accionesVenta(s)}
                onClick={() => setSel(s)}
              />
            ))}
          </ListaTarjetas>
          )}
          {paginacion && <DaxCard padding={false}>{paginacion}</DaxCard>}
        </>
      ) : (
        <DaxCard padding={false}>
          {loading ? <Spinner text="Cargando ventas..." /> : error ? mensajeError : visibles.length === 0 ? (
            <div className="p-12 text-center text-dax-faint">Sin ventas en este periodo</div>
          ) : (
            <TablaDesplazable sangrado={false}>
              <table className="dax-table w-full">
                <thead>
                  <tr>
                    <th>Folio</th>
                    {conSucursales && <th>Sucursal</th>}
                    <th>Fecha</th>
                    <th>Cliente</th>
                    <th className="text-right">Total</th>
                    <th>Pago</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((s) => (
                    <tr key={s.id} onClick={() => setSel(s)} className="cursor-pointer">
                      <td className="font-mono text-dax-accent-text text-xs">{saleLabel(s)}</td>
                      {conSucursales && <td className="text-xs text-dax-muted">{s.branch_name ?? '—'}</td>}
                      <td className="text-xs text-dax-muted">{fechaVenta(s)}</td>
                      <td className="text-sm">{clienteVenta(s)}</td>
                      <td className="text-right font-semibold text-dax-success">{formatCurrency(s.total_amount)}</td>
                      <td>{pagosVenta(s)}</td>
                      <td>{badgeEstado(s)}</td>
                      <td className="text-right">
                        <div className="flex items-center justify-end gap-2">{accionesVenta(s)}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TablaDesplazable>
          )}
          {paginacion}
        </DaxCard>
      )}

      {/* Detalle de la venta: Modal del kit (Escape, foco, hoja inferior en teléfono). */}
      {selected && (
        <Modal
          open
          onClose={() => setSel(null)}
          size="lg"
          title={
            <span>
              <span className="block text-[10px] text-dax-muted uppercase tracking-widest">Folio</span>
              <span className="text-xl font-black text-dax-accent-text font-mono">{saleLabel(selected)}</span>
            </span>
          }
          footer={
            <>
              <button
                type="button"
                disabled={reprinting || !printerName}
                onClick={() => reprintTicket(selected)}
                className="dax-btn-secondary flex-1 justify-center disabled:opacity-40"
                title={printerName ? 'Reimprimir vía agente local' : 'Configura una impresora en /printer-settings primero'}
              >
                {reprinting
                  ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" />
                  : <><i className="fa-solid fa-print" aria-hidden="true" /> {printerName ? 'Reimprimir ticket' : 'Sin impresora configurada'}</>}
              </button>
              {sePuedeDevolver(selected) && (
                <button type="button" onClick={() => { setSel(null); setReturnSale(selected) }} className="dax-btn-danger flex-1 justify-center">
                  <i className="fa-solid fa-undo" aria-hidden="true" /> Registrar devolución
                </button>
              )}
            </>
          }
        >
          <div className="space-y-3 text-sm">
            {conSucursales && <div className="flex justify-between"><span className="text-dax-muted">Sucursal</span><span>{selected.branch_name ?? '—'}</span></div>}
            <div className="flex justify-between"><span className="text-dax-muted">Cliente</span><span>{selected.customer_name ?? 'Público general'}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Fecha</span><span>{new Date(selected.created_at).toLocaleString('es-MX')}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Estado</span>{badgeEstado(selected)}</div>
          </div>

          <div className="mt-4 border-t border-dax-border-dim pt-4">
            <p className="text-[10px] font-bold text-dax-muted uppercase tracking-widest mb-2">Artículos</p>
            {/* Sin envoltorio, la tabla arrastraba de lado todo el modal. */}
            <TablaDesplazable sangrado={false}>
              <table className="dax-table w-full text-xs">
                <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Precio</th><th className="text-right">Total</th></tr></thead>
                <tbody>
                  {selected.lines?.map((line, i) => (
                    <tr key={i}>
                      <td>{line.description ?? line.sku ?? '—'}</td>
                      <td className="text-right">{line.quantity}</td>
                      <td className="text-right">{formatCurrency(Number(line.unit_price))}</td>
                      <td className="text-right font-semibold">{formatCurrency(Number(line.total_line))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TablaDesplazable>
          </div>

          <div className="mt-4 border-t border-dax-border-dim pt-4 space-y-1 text-sm">
            <div className="flex justify-between text-dax-muted"><span>Subtotal</span><span>{formatCurrency(Number(selected.subtotal))}</span></div>
            {Number(selected.tax_amount) > 0 && <div className="flex justify-between text-dax-muted"><span>IVA</span><span>{formatCurrency(Number(selected.tax_amount))}</span></div>}
            <div className="flex justify-between font-black text-dax-text text-base pt-1"><span>Total</span><span>{formatCurrency(selected.total_amount)}</span></div>
            {Number(selected.card_surcharge_amount ?? 0) > 0 && (
              <>
                <div className="flex justify-between text-dax-muted">
                  <span>Comisión tarjeta {formatPct(selected.card_surcharge_pct)}%</span>
                  <span>{formatCurrency(Number(selected.card_surcharge_amount))}</span>
                </div>
                <div className="flex justify-between font-black text-dax-success text-base">
                  <span>Total cobrado</span>
                  <span>{formatCurrency(Number(selected.total_amount) + Number(selected.card_surcharge_amount))}</span>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}
      {returnSale && (
        <ReturnModal
          initialSale={returnSale}
          onClose={() => setReturnSale(null)}
          onSuccess={() => { setReturnSale(null); load(rango, page, sucursal) }}
        />
      )}
      {ventaPorAutorizar && (
        <ReprintPinModal
          etiqueta={saleLabel(ventaPorAutorizar)}
          onCancel={() => setVentaPorAutorizar(null)}
          onSubmit={(pin) => reprintTicket(ventaPorAutorizar, pin)}
        />
      )}
    </div>
  )
}
