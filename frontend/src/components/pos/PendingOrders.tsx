import { useEffect, useCallback, useState } from 'react'
import { parkedTicketsApi } from '../../api/sales'
import { usePOSStore } from '../../store/posStore'
import type { CartItem } from '../../types/sales'
import { formatCurrency } from '../../utils/currency'

interface Props {
  onLoadOrder: (parkedId: string) => void
}

/** Resumen de un parked ticket para la UI: items totales y monto.
 *  cart_json es JSONB libre — calculamos sobre `items` si vienen, else 0.
 */
function summarize(cartJson: Record<string, unknown> | null | undefined) {
  const items = Array.isArray((cartJson as { items?: unknown })?.items)
    ? (cartJson as { items: CartItem[] }).items
    : []
  const itemCount = items.reduce((acc, c) => acc + (Number(c.quantity) || 0), 0)
  const total = items.reduce((acc, c) => acc + (Number(c.subtotal) || 0), 0)
  return { itemCount, total }
}

export function PendingOrders({ onLoadOrder }: Props) {
  const { parkedTickets, setParkedTickets } = usePOSStore()
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const fetchParked = useCallback(async () => {
    try {
      const list = await parkedTicketsApi.list()
      setParkedTickets(list)
    } catch {
      // silencioso
    }
  }, [setParkedTickets])

  const handleDelete = async (id: string) => {
    try {
      await parkedTicketsApi.remove(id)
      setParkedTickets(parkedTickets.filter((o) => o.id !== id))
    } catch {
      // silencioso
    } finally {
      setDeletingId(null)
    }
  }

  useEffect(() => {
    fetchParked()
    const interval = setInterval(fetchParked, 10_000)
    return () => clearInterval(interval)
  }, [fetchParked])

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--dax-border-dim)' }}>
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-pause text-dax-warning text-sm" />
          <span className="text-sm font-bold text-dax-text">Tickets Pausados</span>
          {parkedTickets.length > 0 && (
            <span className="bg-dax-warning text-black text-[10px] font-black px-1.5 py-0.5 rounded-full">
              {parkedTickets.length}
            </span>
          )}
        </div>
        <button
          onClick={fetchParked}
          className="text-dax-muted hover:text-dax-text text-sm min-h-[40px] min-w-[40px] flex items-center justify-center rounded-lg"
        >
          <i className="fa-solid fa-rotate-right" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {parkedTickets.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <i className="fa-solid fa-pause text-dax-faint text-3xl mb-3" />
            <p className="text-dax-muted text-sm">Sin tickets pausados</p>
            <p className="text-dax-faint text-xs mt-1">Se actualiza cada 10 seg.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {parkedTickets.map((ticket) => {
              const { itemCount, total } = summarize(ticket.cart_json)
              const ts = ticket.parked_at
                ? new Date(ticket.parked_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })
                : ''
              return (
                <div key={ticket.id} className="dax-card p-3 flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono text-dax-accent-text truncate">{ticket.id.slice(-8).toUpperCase()}</p>
                    <p className="text-base text-dax-text font-bold tabular-nums">{formatCurrency(total)}</p>
                    <p className="text-xs text-dax-muted truncate">
                      {itemCount} {itemCount === 1 ? 'artículo' : 'artículos'}
                      {ticket.notes ? ` · ${ticket.notes}` : ''}
                    </p>
                    <p className="text-xs text-dax-faint">{ts}</p>
                  </div>
                  {deletingId === ticket.id ? (
                    <div className="flex gap-1 flex-shrink-0">
                      <button
                        onClick={() => handleDelete(ticket.id)}
                        className="dax-btn-primary text-xs px-2 py-1"
                        title="Confirmar descarte"
                      >
                        <i className="fa-solid fa-check" />
                      </button>
                      <button
                        onClick={() => setDeletingId(null)}
                        className="text-dax-muted hover:text-dax-text text-xs px-2 transition-colors"
                        title="Cancelar"
                      >
                        <i className="fa-solid fa-xmark" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => setDeletingId(ticket.id)}
                        className="text-dax-faint hover:text-dax-danger text-xs flex-shrink-0 transition-colors"
                        title="Descartar ticket"
                      >
                        <i className="fa-solid fa-trash" />
                      </button>
                      <button
                        onClick={() => onLoadOrder(ticket.id)}
                        className="dax-btn-primary text-xs flex-shrink-0 min-h-[44px]"
                      >
                        <i className="fa-solid fa-arrow-right" /> Reanudar
                      </button>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
