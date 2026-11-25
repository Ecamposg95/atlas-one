import { useCallback, useEffect, useState } from 'react'
import { salesApi } from '../../api/sales'
import { returnsApi, returnLabel } from '../../api/returns'
import type { ReturnDocument } from '../../api/returns'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { BRANCH_COPY } from '../../copy/branchCopy'
import { esRolCaja } from '../../utils/rolesCaja'
import { useAuthStore } from '../../store/authStore'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { ReturnModal } from '../pos/modals/ReturnModal'
import { ui } from './branchUI'

/** Un folio tecleado o escaneado: "540", "a-540", "A-0540". Lo demás es texto libre. */
const ES_FOLIO = /^[a-z]*-?\d+$/i
const DEVOLVIBLE = (s: SalesDocument) => s.status === 'PAID' || s.status === 'REFUNDED_PARTIAL'

/**
 * Devoluciones del mostrador. La cajera busca el ticket (escaneando el folio
 * impreso, o por cliente o producto dentro del plazo de la tienda) y la
 * devolución en sí —piezas que quedan, motivo, reembolso, PIN del gerente y
 * comprobante— la lleva `ReturnModal`, el mismo flujo del POS y de Ventas.
 * Abajo, las que esperan autorización en la sucursal.
 */
export function ReturnsBranchView() {
  const esCajera = esRolCaja(useAuthStore((s) => s.user?.role))
  const diasCaja = useEnabledModulesStore((s) => s.diasVentasCaja)
  const [query, setQuery] = useState('')
  const [buscando, setBuscando] = useState(false)
  const [resultados, setResultados] = useState<SalesDocument[] | null>(null)
  const [venta, setVenta] = useState<SalesDocument | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pendientes, setPendientes] = useState<ReturnDocument[]>([])

  const cargarPendientes = useCallback(() => {
    returnsApi.list({ status: 'PENDING', limit: 20 })
      .then(setPendientes)
      .catch(() => setPendientes([]))
  }, [])
  useEffect(() => { cargarPendientes() }, [cargarPendientes])

  const noEncontrado = esCajera
    ? (diasCaja > 0
      ? `Ticket no encontrado. Solo aparecen ventas de tu sucursal de los últimos ${diasCaja} días; para más antiguas pide al gerente.`
      : 'Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.')
    : 'No encontré esa venta.'

  async function buscar() {
    const raw = query.trim()
    setError(null)
    setResultados(null)
    if (!raw) { setError('Escribe o escanea el folio del ticket.'); return }
    setBuscando(true)
    try {
      const res = await salesApi.list(ES_FOLIO.test(raw) ? { folio_search: raw, limit: 10 } : { search: raw, limit: 10 })
      const items = res.items ?? []
      if (items.length === 0) { setError(noEncontrado); return }
      // Un folio exacto abre directo; varias coincidencias (o texto libre) se eligen.
      if (items.length === 1 && ES_FOLIO.test(raw)) abrir(items[0])
      else setResultados(items)
    } catch (e: any) {
      setError(errorDetailText(e?.response?.data?.detail, 'No pude buscar el ticket. Intenta de nuevo.'))
    } finally { setBuscando(false) }
  }

  function abrir(s: SalesDocument) {
    if (s.status === 'CANCELLED') { setError('Este ticket fue cancelado: no tiene nada que devolver.'); return }
    if (s.status === 'REFUNDED_TOTAL') { setError('Este ticket ya se devolvió completo.'); return }
    setError(null)
    setVenta(s)
  }

  async function abrirPendiente(r: ReturnDocument) {
    setError(null)
    try {
      setVenta(await salesApi.getById(r.sale_id))
    } catch (e: any) {
      setError(errorDetailText(e?.response?.data?.detail, 'No pude abrir el ticket de esa devolución.'))
    }
  }

  const cerrar = () => { setVenta(null); setResultados(null); setQuery(''); cargarPendientes() }

  return (
    <div className={`${ui.page} py-6`}>
      <div className="max-w-2xl mx-auto px-4 space-y-5">
        <h1 className={ui.pageTitle}>{BRANCH_COPY.pages.returns}</h1>

        {error && (
          <div role="alert" className="rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200/60 dark:border-rose-800/40 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
            {error}
          </div>
        )}

        <section className={`${ui.card} p-6 space-y-4`}>
          <div>
            <label htmlFor="devolucion-buscar" className={`block ${ui.kpiLabel} mb-2`}>Ticket a devolver</label>
            <input
              id="devolucion-buscar"
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && buscar()}
              className={ui.input}
              placeholder="Escanea el folio, o escribe cliente o producto"
            />
            {esCajera && diasCaja > 0 && (
              <p className={`text-xs ${ui.muted} mt-2`}>Ventas de tu sucursal de los últimos {diasCaja} días.</p>
            )}
          </div>
          <button onClick={buscar} disabled={buscando} className={`${ui.btnPrimary} w-full disabled:opacity-40`}>
            <i className={`fa-solid ${buscando ? 'fa-spinner fa-spin' : 'fa-magnifying-glass'} text-sm`} aria-hidden="true" />
            Buscar venta
          </button>

          {resultados && (
            <ul className="space-y-2" aria-label="Ventas encontradas">
              {resultados.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => abrir(s)}
                    className="w-full flex items-center justify-between gap-3 rounded-2xl bg-stone-50 dark:bg-slate-800/60 px-4 py-3 text-left"
                  >
                    <span className="min-w-0">
                      <span className="block font-mono text-sm font-bold">{saleLabel(s)}</span>
                      <span className={`block text-xs ${ui.muted} truncate`}>
                        {s.customer_name ?? 'Público general'} · {new Date(s.created_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
                        {!DEVOLVIBLE(s) && ' · sin piezas por devolver'}
                      </span>
                    </span>
                    <span className="text-sm font-semibold tabular-nums flex-shrink-0">{formatCurrency(s.total_amount)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {pendientes.length > 0 && (
          <section className={`${ui.card} p-6 space-y-3`} data-testid="pendientes">
            <p className={ui.sectionTitle}>Esperan autorización</p>
            <ul className="space-y-2">
              {pendientes.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 rounded-2xl bg-stone-50 dark:bg-slate-800/60 px-4 py-3">
                  <span className="min-w-0">
                    <span className="block font-mono text-sm font-bold">{returnLabel(r)}</span>
                    <span className={`block text-xs ${ui.muted} truncate`}>
                      {r.sale?.folio != null ? `Ticket ${r.sale.series ?? ''}-${r.sale.folio} · ` : ''}{r.reason}
                    </span>
                  </span>
                  <span className="flex items-center gap-3 flex-shrink-0">
                    <span className="text-sm font-semibold tabular-nums">{formatCurrency(Number(r.total_refunded))}</span>
                    <button type="button" onClick={() => abrirPendiente(r)} className={ui.btnSecondary}>
                      <i className="fa-solid fa-key text-xs" aria-hidden="true" /> Autorizar
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {venta && <ReturnModal initialSale={venta} onClose={cerrar} onSuccess={cerrar} />}
    </div>
  )
}
