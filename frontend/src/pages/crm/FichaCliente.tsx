import { useCallback, useEffect, useState } from 'react'
import { customersApi, type FichaCliente as Ficha } from '../../api/customers'
import { formatCurrency } from '../../utils/currency'
import { fechaCorta, valorDeCampo } from './crmUtil'
import { SeguimientoLista } from './SeguimientoLista'

interface Props {
  customerId: number
  /** Cambia cuando el cliente se edita o abona, para releer la ficha. */
  version?: number
}

function Dato({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg p-2.5 bg-dax-elevated border border-dax-border-dim">
      <p className="text-[10px] font-bold uppercase tracking-wider text-dax-muted">{label}</p>
      <p className="text-sm font-semibold text-dax-text break-words">{children}</p>
    </div>
  )
}

const Titulo = ({ children }: { children: React.ReactNode }) => (
  <h3 className="text-[10px] font-bold uppercase tracking-widest text-dax-muted mb-1.5">{children}</h3>
)

/** Ficha 360: quién es, qué compra, qué trae pendiente. La caja no ve acumulados. */
export function FichaCliente({ customerId, version = 0 }: Props) {
  const [ficha, setFicha] = useState<Ficha | null>(null)
  const [error, setError] = useState(false)

  const cargar = useCallback(() => {
    customersApi.ficha(customerId).then((f) => { setFicha(f); setError(false) }).catch(() => setError(true))
  }, [customerId])
  useEffect(() => { cargar() }, [cargar, version])

  if (error) return <p className="text-sm text-dax-danger mb-4" role="alert">No se pudo cargar la ficha del cliente.</p>
  if (!ficha) return <p className="text-sm text-dax-muted mb-4">Cargando ficha…</p>

  const c = ficha.customer
  const r = ficha.resumen
  const propios = ficha.campos.filter((d) => c.campos?.[d.key] != null && c.campos?.[d.key] !== '')

  return (
    <div className="space-y-4 mb-4" data-testid="ficha-cliente">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Dato label="Tipo">{c.tipo === 'MAYOREO' ? 'Mayoreo' : 'Menudeo'}</Dato>
        <Dato label="Teléfono">{c.phone || '—'}</Dato>
        <Dato label="Cumpleaños">{fechaCorta(c.birthday)}</Dato>
        <Dato label={c.tipo === 'MAYOREO' ? 'Negocio' : 'Correo'}>{(c.tipo === 'MAYOREO' ? c.company : c.email) || '—'}</Dato>
        {c.has_credit && <Dato label="Crédito disponible">{formatCurrency(ficha.credito_disponible)}</Dato>}
        {ficha.vales_saldo > 0 && <Dato label="Vales de tienda">{formatCurrency(ficha.vales_saldo)}</Dato>}
        {propios.map((d) => <Dato key={d.key} label={d.label}>{valorDeCampo(d.tipo, c.campos?.[d.key])}</Dato>)}
      </div>
      {c.notes && <p className="text-sm text-dax-muted"><i className="fa-solid fa-note-sticky mr-1.5" aria-hidden="true" />{c.notes}</p>}

      {r && (
        <div>
          <Titulo>Compras</Titulo>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Dato label="Total comprado">{formatCurrency(r.total_comprado)}</Dato>
            <Dato label="Tickets">{r.tickets}</Dato>
            <Dato label="Ticket promedio">{formatCurrency(r.ticket_promedio)}</Dato>
            <Dato label="Última compra">
              {r.ultima_compra ? `${fechaCorta(r.ultima_compra)}${r.dias_sin_comprar != null ? ` · hace ${r.dias_sin_comprar} d` : ''}` : 'Sin compras'}
            </Dato>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <Titulo>{ficha.limitado ? 'Compras recientes en tu sucursal' : 'Últimas compras'}</Titulo>
          {ficha.compras.length === 0 ? <p className="text-sm text-dax-muted">Sin compras registradas.</p> : (
            <ul className="text-sm divide-y divide-dax-border-dim">
              {ficha.compras.map((v) => (
                <li key={v.id} className="flex justify-between gap-2 py-1.5">
                  <span className="text-dax-muted">{fechaCorta(v.created_at)} · <span className="font-mono">{v.series ?? ''}{v.series ? '-' : ''}{v.folio ?? '—'}</span></span>
                  <span className="font-semibold text-dax-text tabular-nums">{formatCurrency(v.total)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        {!ficha.limitado && (
          <div>
            <Titulo>Lo que más compra</Titulo>
            {ficha.productos.length === 0 ? <p className="text-sm text-dax-muted">Aún no hay datos.</p> : (
              <ul className="text-sm divide-y divide-dax-border-dim">
                {ficha.productos.map((p, i) => (
                  <li key={i} className="flex justify-between gap-2 py-1.5">
                    <span className="text-dax-text min-w-0 truncate">{p.descripcion ?? 'Producto'}</span>
                    <span className="text-dax-muted tabular-nums whitespace-nowrap">{p.piezas} pz · {formatCurrency(p.importe)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {ficha.vales.length > 0 && (
        <div>
          <Titulo>Vales de tienda con saldo</Titulo>
          <ul className="text-sm">
            {ficha.vales.map((v) => (
              <li key={v.code} className="flex justify-between py-1">
                <span className="font-mono text-dax-text">{v.code}</span>
                <span className="tabular-nums text-dax-text">{formatCurrency(v.balance)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <Titulo>Seguimiento</Titulo>
        <SeguimientoLista items={ficha.seguimiento} customerId={customerId} onCambio={cargar} />
      </div>
    </div>
  )
}
