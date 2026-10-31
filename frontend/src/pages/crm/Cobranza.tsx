import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { customersApi, type CobranzaItem, type CobranzaResponse, type LedgerEntry, type UnpaidDocument } from '../../api/customers'
import { AbonoModal } from '../../components/crm/AbonoModal'
import { BarraFiltros } from '../../components/ui/BarraFiltros'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { ErrorState } from '../../components/ui/ErrorState'
import { KpiCard } from '../../components/ui/KpiCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { Modal } from '../../components/ui/Modal'
import { Spinner } from '../../components/ui/Spinner'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useSucursalesVendibles } from '../../hooks/useSucursalesVendibles'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'
import { toWaPhone } from '../../utils/phone'

type Bucket = 'current' | '31_60' | '61_90' | '91_plus'
const BUCKETS: { clave: Bucket; etiqueta: string; tono: string }[] = [
  { clave: 'current', etiqueta: '0-30', tono: 'text-dax-success' },
  { clave: '31_60', etiqueta: '31-60', tono: 'text-dax-warning' },
  { clave: '61_90', etiqueta: '61-90', tono: 'text-dax-warning' },
  { clave: '91_plus', etiqueta: '+90', tono: 'text-dax-danger' },
]
const fecha = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('es-MX') : '—')
const dias = (n: number) => (n === 1 ? '1 día' : `${n} días`)

/** Mensaje del recordatorio (spec 2026-10-29 §5): texto fijo, sin API ni registro. */
export const mensajeRecordatorio = (nombre: string, negocio: string, saldo: number) =>
  `Hola ${nombre}, te saludamos de ${negocio}. Tienes un saldo pendiente de ${formatCurrency(saldo)}. Puedes pasar a abonar cuando gustes. ¡Gracias!`

function Antiguedad({ a }: { a: CobranzaItem['antiguedad'] }) {
  return (
    <span className="inline-flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] font-semibold tabular-nums">
      {BUCKETS.filter((b) => a[b.clave] > 0).map((b) => (
        <span key={b.clave} className={b.tono}>{b.etiqueta}: {formatCurrency(a[b.clave])}</span>
      ))}
    </span>
  )
}

/**
 * Cuentas por cobrar (spec 2026-10-29 §3.2): quién debe, cuánto y desde
 * cuándo. Solo roles de oficina; se entra desde Clientes y desde el Inicio.
 */
export function Cobranza() {
  const esTelefono = useEsTelefono()
  const negocio = useAuthStore((s) => s.org?.name) ?? 'la tienda'
  const sucursales = useSucursalesVendibles(true)
  const [datos, setDatos] = useState<CobranzaResponse | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState(false)
  const [search, setSearch] = useState('')
  const [branchId, setBranchId] = useState('')
  const [bucket, setBucket] = useState('')
  const [order, setOrder] = useState<'saldo' | 'antiguedad'>('saldo')
  const [detalleId, setDetalleId] = useState<number | null>(null)
  const [tickets, setTickets] = useState<UnpaidDocument[]>([])
  const [asientos, setAsientos] = useState<LedgerEntry[]>([])
  const [abonando, setAbonando] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Boleto por cargador: solo la última petición pinta (las respuestas pueden llegar desordenadas).
  const seqCarga = useRef(0)
  const seqDetalle = useRef(0)

  const cargar = useCallback(async (q: string) => {
    const mio = ++seqCarga.current
    setCargando(true); setError(false)
    try {
      const r = await customersApi.cobranza({
        search: q.trim() || undefined,
        branch_id: branchId ? Number(branchId) : undefined,
        bucket: bucket || undefined,
        order, limit: 200,
      })
      if (mio === seqCarga.current) setDatos(r)
    } catch {
      if (mio === seqCarga.current) setError(true)
    } finally {
      if (mio === seqCarga.current) setCargando(false)
    }
  }, [branchId, bucket, order])

  // El temporizador del buscador llama siempre a la última versión de `cargar` (con los filtros vigentes).
  const cargarRef = useRef(cargar)
  cargarRef.current = cargar

  useEffect(() => {
    // Un cambio de filtro carga ya con el texto actual: el debounce pendiente sobra.
    if (timer.current) { clearTimeout(timer.current); timer.current = null }
    cargar(search) /* eslint-disable-line react-hooks/exhaustive-deps */
  }, [cargar])

  // El temporizador del buscador no debe disparar tras desmontar la pantalla.
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const onSearch = (v: string) => {
    setSearch(v)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => cargarRef.current(v), 400)
  }

  const abrir = async (id: number) => {
    const mio = ++seqDetalle.current
    setDetalleId(id); setTickets([]); setAsientos([])
    try {
      const [t, a] = await Promise.all([customersApi.getUnpaidDocuments(id), customersApi.getStatement(id, { limit: 30 })])
      if (mio !== seqDetalle.current) return
      setTickets(t); setAsientos(a)
    } catch {
      if (mio === seqDetalle.current) { setTickets([]); setAsientos([]) }
    }
  }

  const cerrarDetalle = () => { seqDetalle.current++; setDetalleId(null); setTickets([]); setAsientos([]) }

  const whatsapp = (c: CobranzaItem) => {
    const tel = toWaPhone(c.phone)
    if (!tel) return
    window.open(`https://wa.me/${tel}?text=${encodeURIComponent(mensajeRecordatorio(c.name, negocio, c.balance))}`, '_blank')
  }

  const pdf = async (c: CobranzaItem) => {
    try {
      const blob = await customersApi.getStatementPdf(c.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `EdoCuenta_${c.name.replace(/[^\w-]+/g, '_')}.pdf`; a.click()
      URL.revokeObjectURL(url)
    } catch { toast.error('No se pudo generar el PDF del estado de cuenta') }
  }

  const botonWa = (c: CobranzaItem, compacto = false) => {
    const tel = toWaPhone(c.phone)
    return (
      <button type="button" onClick={() => whatsapp(c)} disabled={!tel} title={tel ? 'Recordar por WhatsApp' : 'Sin teléfono'}
        aria-label="Recordar por WhatsApp"
        className={`${compacto ? 'dax-btn-icon' : 'dax-btn-secondary text-xs'} disabled:opacity-40`}>
        <i className="fa-brands fa-whatsapp" aria-hidden="true" />{!compacto && ' WhatsApp'}
      </button>
    )
  }

  const items = datos?.items ?? []
  // El detalle se deriva de la lista vigente: tras un abono muestra el saldo nuevo y,
  // si el cliente ya no debe (o el filtro lo saca), la pantalla lo cierra sola.
  const detalle = detalleId == null ? null : items.find((c) => c.id === detalleId) ?? null
  const r = datos?.resumen
  // Si el cliente salió de la lista, suelta también su id: que no reabra el detalle si reaparece tras otro filtro.
  useEffect(() => {
    if (detalleId != null && datos && !detalle) cerrarDetalle() /* eslint-disable-line react-hooks/exhaustive-deps */
  }, [detalleId, datos, detalle])

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-dax-text">Cuentas por cobrar</h1>}
        descripcion="Quién debe, cuánto y desde cuándo. El abono se aplica del ticket más viejo al más nuevo."
        acciones={<Link to="/customers" className="dax-btn-secondary text-xs"><i className="fa-solid fa-address-book" aria-hidden="true" /> Clientes</Link>}
      />

      {r && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="kpis-cobranza">
          <KpiCard etiqueta="Por cobrar" valor={formatCurrency(r.por_cobrar)} detalle={r.a_favor > 0 ? `A favor de clientes: ${formatCurrency(r.a_favor)}` : undefined} />
          <KpiCard etiqueta="Vencido a más de 30 días" valor={formatCurrency(r.vencido_30)} tono={r.vencido_30 > 0 ? 'danger' : undefined} />
          <KpiCard etiqueta="Clientes con deuda" valor={String(r.clientes)} />
        </div>
      )}

      <BarraFiltros>
        <input type="search" value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Nombre o teléfono" aria-label="Buscar" className="dax-input flex-1 min-w-[160px] text-sm" />
        {sucursales.length > 1 && (
          <select aria-label="Sucursal" value={branchId} onChange={(e) => setBranchId(e.target.value)} className="dax-input text-sm">
            <option value="">Todas las sucursales</option>
            {sucursales.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
        <select aria-label="Antigüedad" value={bucket} onChange={(e) => setBucket(e.target.value)} className="dax-input text-sm">
          <option value="">Toda antigüedad</option>
          {BUCKETS.map((b) => <option key={b.clave} value={b.clave}>{b.etiqueta} días</option>)}
        </select>
        <select aria-label="Orden" value={order} onChange={(e) => setOrder(e.target.value as 'saldo' | 'antiguedad')} className="dax-input text-sm">
          <option value="saldo">Mayor saldo primero</option>
          <option value="antiguedad">Más viejo primero</option>
        </select>
      </BarraFiltros>

      {error ? (
        <ErrorState message="No se pudieron cargar las cuentas por cobrar" onRetry={() => cargar(search)} />
      ) : esTelefono ? (
        <ListaTarjetas vacio={!cargando && items.length === 0} textoVacio="Nadie debe" cargando={cargando}>
          {items.map((c) => (
            <TarjetaFila key={c.id} titulo={c.name} subtitulo={c.branch_name ?? undefined}
              importe={<span className="text-dax-danger font-bold">{formatCurrency(c.balance)}</span>}
              estado={<Antiguedad a={c.antiguedad} />}
              datos={[{ etiqueta: 'Desde', valor: `${fecha(c.cargo_mas_viejo)} · ${dias(c.dias)}` }, { etiqueta: 'Último abono', valor: fecha(c.ultimo_abono) }]}
              onClick={() => abrir(c.id)}
              acciones={<>{botonWa(c)}<button type="button" onClick={() => abrir(c.id)} className="dax-btn-primary text-xs">Ver</button></>} />
          ))}
        </ListaTarjetas>
      ) : (
        <DaxCard>
          {cargando && !datos ? <div className="flex justify-center py-10"><Spinner /></div> : items.length === 0 ? (
            <p className="text-center text-dax-muted py-10">Nadie debe</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-dax-muted">
                  <th className="py-2">Cliente</th><th>Teléfono</th><th className="text-right">Saldo</th><th>Desde</th><th>Último abono</th><th>Sucursal</th><th>Antigüedad</th><th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className="border-t border-dax-border-dim cursor-pointer hover:brightness-110" onClick={() => abrir(c.id)}>
                    <td className="py-2 font-medium text-dax-text">{c.name}</td>
                    <td className="text-dax-muted">{c.phone ?? '—'}</td>
                    <td className="text-right tabular-nums font-bold text-dax-danger">{formatCurrency(c.balance)}</td>
                    <td className="text-dax-muted">{fecha(c.cargo_mas_viejo)} · {dias(c.dias)}</td>
                    <td className="text-dax-muted">{fecha(c.ultimo_abono)}</td>
                    <td className="text-dax-muted">{c.branch_name ?? '—'}</td>
                    <td><Antiguedad a={c.antiguedad} /></td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>{botonWa(c, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </DaxCard>
      )}

      {!error && datos && datos.total > items.length && (
        <p className="text-xs text-dax-muted text-center">Mostrando {items.length} de {datos.total} clientes. Afina la búsqueda o el filtro para ver el resto.</p>
      )}

      {detalle && (
        <Modal open onClose={cerrarDetalle} size="lg" title={detalle.name}
          footer={<>
            {botonWa(detalle)}
            <button type="button" onClick={() => pdf(detalle)} className="dax-btn-secondary text-xs"><i className="fa-solid fa-file-pdf" aria-hidden="true" /> Estado de cuenta</button>
            <button type="button" onClick={() => setAbonando(true)} className="dax-btn-primary text-xs flex-1 justify-center"><i className="fa-solid fa-money-bill-wave" aria-hidden="true" /> Registrar abono</button>
          </>}>
          <p className="text-sm text-dax-muted mb-3">Debe <span className="font-bold text-dax-danger">{formatCurrency(detalle.balance)}</span> · <Antiguedad a={detalle.antiguedad} /></p>
          <p className="dax-section-title mb-1">Tickets abiertos</p>
          {tickets.length === 0 ? <p className="text-xs text-dax-muted mb-3">Sin tickets abiertos</p> : (
            <ul className="mb-3 space-y-1">
              {tickets.map((t) => (
                <li key={t.id} className="flex justify-between text-sm"><span className="text-dax-text">{t.folio} · {fecha(t.created_at)}</span><span className="tabular-nums text-dax-danger">{formatCurrency(t.balance)}</span></li>
              ))}
            </ul>
          )}
          <p className="dax-section-title mb-1">Movimientos</p>
          <ul className="space-y-1 max-h-64 overflow-y-auto">
            {asientos.map((e) => (
              <li key={e.id} className="flex justify-between text-xs">
                <span className="text-dax-muted">{fecha(e.created_at)} · {e.description ?? '—'}</span>
                <span className={`tabular-nums font-semibold ${e.amount >= 0 ? 'text-dax-danger' : 'text-dax-success'}`}>{e.amount >= 0 ? '+' : ''}{formatCurrency(e.amount)}</span>
              </li>
            ))}
          </ul>
        </Modal>
      )}

      {abonando && detalle && (
        <AbonoModal customerId={detalle.id} customerName={detalle.name} onClose={() => setAbonando(false)}
          onDone={() => { cargar(search); abrir(detalle.id) }} />
      )}
    </div>
  )
}
