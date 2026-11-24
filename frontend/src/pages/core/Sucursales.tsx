import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { reportsApi, type CommandCenterStats, type DashboardData } from '../../api/reports'
import { organizationApi, type Branch } from '../../api/organization'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { confirm as confirmDialog } from '../../components/ui/ConfirmDialog'
import { toast } from '../../store/toastStore'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { formatCurrency } from '../../utils/currency'
import { todayStr } from '../../utils/dates'
import { errorDetailText } from '../../utils/errorDetail'

/**
 * Sucursales (pestaña de `/configuracion`). Une lo que eran dos pantallas:
 * el tablero "¿cómo va cada sucursal hoy?" (`/hq/branches`) y el alta y
 * edición que vivía en Empresa. `?sucursal=ID` abre el detalle de hoy de esa
 * sucursal debajo de la rejilla; los enlaces viejos `/hq/branches/:id`
 * redirigen aquí.
 */

const TIPOS: Branch['branch_type'][] = ['HQ', 'STORE', 'WAREHOUSE', 'OFFICE']
const TIPO: Record<string, string> = { HQ: 'Casa Matriz', STORE: 'Sucursal', WAREHOUSE: 'Almacén', OFFICE: 'Oficina' }

interface Formulario {
  name: string
  branch_type: Branch['branch_type']
  address: string
  phone: string
  can_sell: boolean
  is_active: boolean
}
const VACIO: Formulario = { name: '', branch_type: 'STORE', address: '', phone: '', can_sell: true, is_active: true }

/**
 * Lo que viaja al guardar. Al editar solo va lo que cambió: mandar el tipo de
 * la matriz sin `can_sell` le apagaba la venta (`update_branch` lo toma como
 * "pasa a ser matriz"), así que el tipo viaja únicamente si se tocó.
 */
export function cambiosDeSucursal(original: Branch | null, f: Formulario): Record<string, unknown> {
  const datos: Record<string, unknown> = {
    name: f.name.trim(),
    address: f.address.trim() || undefined,
    phone: f.phone.trim() || undefined,
  }
  if (!original) return { ...datos, branch_type: f.branch_type }
  if (f.branch_type !== original.branch_type) datos.branch_type = f.branch_type
  if (f.can_sell !== (original.can_sell ?? true)) datos.can_sell = f.can_sell
  if (f.is_active !== original.is_active) datos.is_active = f.is_active
  return datos
}

function Detalle({ branch, onCerrar }: { branch: Branch; onCerrar: () => void }) {
  const esTelefono = useEsTelefono()
  const [datos, setDatos] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let vivo = true
    setDatos(null); setError('')
    const hoy = todayStr()
    reportsApi.dashboard({ start_date: hoy, end_date: hoy, branch_id: branch.id })
      .then((d) => { if (vivo) setDatos(d) })
      .catch(() => { if (vivo) setError('No se pudieron cargar los datos de la sucursal.') })
    return () => { vivo = false }
  }, [branch.id])

  const kpis = [
    { label: 'Ventas hoy', value: formatCurrency(datos?.kpis.sales ?? 0), color: 'text-dax-success' },
    { label: 'Tickets', value: String(datos?.kpis.orders ?? 0), color: 'text-dax-text' },
    { label: 'Ticket promedio', value: formatCurrency(datos?.kpis.avg_ticket ?? 0), color: 'text-dax-text' },
    { label: 'Pendientes', value: String(datos?.kpis.pending ?? 0), color: 'text-dax-warning' },
  ]
  const top = datos?.top_products.slice(0, 5) ?? []
  const poca = datos?.low_stock ?? []
  const ultimas = datos?.recent_sales ?? []

  return (
    <div className="space-y-4" data-testid="detalle-sucursal">
      <div className="flex max-md:flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[10px] text-dax-faint uppercase tracking-widest">Hoy en</p>
          <p className="text-lg font-black text-dax-text">{branch.name}</p>
          <p className="text-xs text-dax-faint">{TIPO[branch.branch_type] ?? branch.branch_type}{branch.address ? ` · ${branch.address}` : ''}{branch.phone ? ` · ${branch.phone}` : ''}</p>
        </div>
        <button onClick={onCerrar} className="dax-btn-secondary text-xs max-md:min-h-[44px]"><i className="fa-solid fa-xmark" /> Cerrar</button>
      </div>

      {error ? (
        <DaxCard><p className="text-sm text-dax-danger">{error}</p></DaxCard>
      ) : !datos ? (
        <Spinner text="Cargando sucursal..." />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {kpis.map((k) => (
              <div key={k.label} className="dax-card p-4">
                <p className="text-[10px] uppercase text-dax-faint font-bold tracking-widest">{k.label}</p>
                <p className={`text-2xl font-bold tabular-nums mt-1 ${k.color}`}>{k.value}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <DaxCard>
              <p className="text-[10px] font-black uppercase tracking-widest text-dax-faint mb-3">Lo más vendido hoy</p>
              {top.length === 0 ? (
                <p className="text-sm text-dax-muted">Sin ventas registradas hoy.</p>
              ) : (
                <ul className="space-y-1">
                  {top.map((p, i) => (
                    <li key={i} className="flex justify-between text-sm gap-2">
                      <span className="text-dax-text truncate">{p.name}</span>
                      <span className="text-dax-faint tabular-nums shrink-0">{p.qty} pz</span>
                    </li>
                  ))}
                </ul>
              )}
            </DaxCard>
            <DaxCard>
              <p className="text-[10px] font-black uppercase tracking-widest text-dax-warning mb-3">Se está acabando</p>
              {esTelefono ? (
                <ListaTarjetas vacio={poca.length === 0} textoVacio="Nada se está acabando.">
                  {poca.map((p, i) => <TarjetaFila key={i} titulo={p.name} subtitulo={p.sku} importe={`${p.stock} pz`} />)}
                </ListaTarjetas>
              ) : poca.length === 0 ? (
                <p className="text-sm text-dax-muted">Nada se está acabando.</p>
              ) : (
                <ul className="space-y-1">
                  {poca.map((p, i) => (
                    <li key={i} className="flex justify-between text-sm gap-2">
                      <span className="text-dax-text truncate">{p.name} <span className="font-mono text-xs text-dax-faint">{p.sku}</span></span>
                      <span className="text-dax-warning font-bold tabular-nums shrink-0">{p.stock}</span>
                    </li>
                  ))}
                </ul>
              )}
            </DaxCard>
          </div>

          <DaxCard>
            <p className="text-[10px] font-black uppercase tracking-widest text-dax-faint mb-3">Últimas ventas</p>
            {esTelefono ? (
              <ListaTarjetas vacio={ultimas.length === 0} textoVacio="Sin ventas hoy.">
                {ultimas.map((s, i) => (
                  <TarjetaFila key={i} titulo={s.folio} subtitulo={`${s.time} · ${s.customer || 'Público general'}`} importe={formatCurrency(s.total)} />
                ))}
              </ListaTarjetas>
            ) : ultimas.length === 0 ? (
              <p className="text-sm text-dax-muted">Sin ventas hoy.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[10px] text-dax-faint uppercase text-left">
                    <th className="pb-2">Hora</th><th className="pb-2">Folio</th><th className="pb-2">Cliente</th><th className="pb-2 text-right">Total</th>
                  </tr>
                </thead>
                <tbody className="text-dax-text">
                  {ultimas.map((s, i) => (
                    <tr key={i} className="border-t border-dax-border-dim">
                      <td className="py-2 text-dax-faint font-mono">{s.time}</td>
                      <td className="py-2 font-mono text-dax-accent-text">{s.folio}</td>
                      <td className="py-2">{s.customer || 'Público general'}</td>
                      <td className="py-2 text-right font-bold text-dax-success">{formatCurrency(s.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </DaxCard>
        </>
      )}
    </div>
  )
}

export function Sucursales() {
  const [params, setParams] = useSearchParams()
  const elegidaId = params.get('sucursal')
  const [branches, setBranches] = useState<Branch[]>([])
  const [stats, setStats] = useState<CommandCenterStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [errorCarga, setErrorCarga] = useState(false)
  const [modal, setModal] = useState<'crear' | 'editar' | null>(null)
  const [editando, setEditando] = useState<Branch | null>(null)
  const [form, setForm] = useState<Formulario>(VACIO)
  const [guardando, setGuardando] = useState(false)

  const cargarSucursales = () => organizationApi.getBranches().then(setBranches)

  useEffect(() => {
    const hoy = todayStr()
    // Las cifras de hoy son un extra: si fallan, la lista se sigue pudiendo administrar.
    reportsApi.commandCenterStats({ start_date: hoy, end_date: hoy }).then(setStats).catch(() => {})
    cargarSucursales().catch(() => setErrorCarga(true)).finally(() => setLoading(false))
  }, [])

  const elegir = (id: number | null) => {
    const p = new URLSearchParams(params)
    if (id == null) p.delete('sucursal')
    else p.set('sucursal', String(id))
    setParams(p, { replace: true })
  }

  const abrirAlta = () => { setForm(VACIO); setEditando(null); setModal('crear') }
  const abrirEdicion = (b: Branch) => {
    setForm({ name: b.name, branch_type: b.branch_type, address: b.address ?? '', phone: b.phone ?? '', can_sell: b.can_sell ?? true, is_active: b.is_active })
    setEditando(b); setModal('editar')
  }

  const guardar = async () => {
    setGuardando(true)
    try {
      const datos = cambiosDeSucursal(modal === 'crear' ? null : editando, form)
      if (modal === 'crear') await organizationApi.createBranch(datos as never)
      else if (editando) await organizationApi.updateBranch(editando.id, datos as never)
      setModal(null)
      toast.success(modal === 'crear' ? 'Sucursal creada' : 'Sucursal actualizada')
      cargarSucursales().catch(() => {})
    } catch (e: any) {
      // El tope del plan llega aquí como 403 con el motivo en español.
      toast.error(errorDetailText(e?.response?.data?.detail, 'Error al guardar la sucursal'))
    } finally { setGuardando(false) }
  }

  const eliminar = async (b: Branch) => {
    const ok = await confirmDialog({
      title: 'Eliminar sucursal',
      message: `¿Eliminar la sucursal "${b.name}"? Si ya tiene ventas o cortes no se puede borrar: desactívala desde Editar.`,
      variant: 'danger',
      confirmText: 'Eliminar',
    })
    if (!ok) return
    try {
      await organizationApi.deleteBranch(b.id)
      setBranches((prev) => prev.filter((x) => x.id !== b.id))
      if (String(b.id) === elegidaId) elegir(null)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'Error al eliminar la sucursal'))
    }
  }

  if (loading) return <Spinner text="Cargando sucursales..." />

  const deHoy = (id: number) => stats?.branches?.find((b) => b.id === id)
  const elegida = elegidaId ? branches.find((b) => b.id === Number(elegidaId)) ?? null : null
  // "Abierta" es el estado que calcula el backend (turno abierto o ventas hoy), no `pending_cuts`.
  const abiertas = stats?.branches?.filter((b) => b.status === 'ONLINE').length ?? 0
  const alertas = stats?.alerts?.length ?? 0
  const resumen = [
    { label: 'Sucursales', value: branches.length, color: 'text-dax-text' },
    { label: 'Abiertas hoy', value: abiertas, color: 'text-dax-success' },
    { label: 'Sin venta hoy', value: (stats?.branches?.length ?? 0) - abiertas, color: 'text-dax-muted' },
    { label: 'Se está acabando', value: alertas, color: 'text-dax-warning' },
  ]

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h2 className="text-lg font-black text-dax-text">Sucursales</h2>}
        descripcion="Cómo va cada sucursal hoy. Toca una para ver su detalle; el lápiz cambia sus datos."
        accionPrincipal={
          <button onClick={abrirAlta} className="dax-btn-primary text-xs"><i className="fa-solid fa-plus" /> Nueva sucursal</button>
        }
      />

      {errorCarga && (
        <DaxCard><p className="text-sm text-dax-danger">No se pudieron cargar las sucursales. Recarga la página.</p></DaxCard>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {resumen.map((k) => (
            <DaxCard key={k.label}>
              <p className="text-[10px] uppercase text-dax-faint font-bold mb-1">{k.label}</p>
              <p className={`text-2xl font-bold tabular-nums ${k.color}`}>{k.value}</p>
            </DaxCard>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {branches.map((b) => {
          const hoy = deHoy(b.id)
          const abierta = hoy?.status === 'ONLINE'
          const activa = elegida?.id === b.id
          return (
            <DaxCard key={b.id} className={`h-full ${activa ? 'ring-2 ring-dax-accent' : ''}`}>
              <div className="flex items-start justify-between gap-2 mb-3">
                <button
                  type="button"
                  onClick={() => elegir(activa ? null : b.id)}
                  aria-pressed={activa}
                  className="text-left min-w-0 flex-1 max-md:min-h-[44px] hover:opacity-80 transition-opacity"
                >
                  <p className="font-black text-dax-text text-sm truncate">{b.name}</p>
                  <p className="text-[10px] text-dax-faint mt-0.5">
                    {TIPO[b.branch_type] ?? b.branch_type}{b.can_sell === false ? ' · No vende' : ''}
                  </p>
                </button>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => abrirEdicion(b)} aria-label={`Editar ${b.name}`} className="dax-btn-icon text-dax-muted text-xs">
                    <i className="fa-solid fa-pen" />
                  </button>
                  {!b.is_headquarters && (
                    <button onClick={() => eliminar(b)} aria-label={`Eliminar ${b.name}`} className="dax-btn-icon text-dax-danger text-xs">
                      <i className="fa-solid fa-trash" />
                    </button>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between gap-2 mb-3">
                <span className={`flex items-center gap-1.5 text-xs font-semibold ${abierta ? 'text-dax-success' : 'text-dax-faint'}`}>
                  <i className="fa-solid fa-circle text-[8px]" />
                  {abierta ? 'Abierta' : 'Cerrada'}
                </span>
                <Badge variant={b.is_active ? 'green' : 'slate'}>{b.is_active ? 'Activa' : 'Inactiva'}</Badge>
              </div>

              {hoy ? (
                <div className="space-y-1.5 text-sm border-t border-dax-border-dim pt-3">
                  <div className="flex justify-between text-dax-muted">
                    <span>Ventas hoy</span>
                    <span className="text-dax-success font-semibold">{formatCurrency(hoy.total_sales)}</span>
                  </div>
                  <div className="flex justify-between text-dax-muted">
                    <span>Turnos abiertos</span>
                    <span className="text-dax-text font-semibold">{hoy.pending_cuts ?? 0}</span>
                  </div>
                  {hoy.critical_stock > 0 && (
                    <div className="flex justify-between text-dax-muted">
                      <span>Se está acabando</span>
                      <span className="text-dax-warning font-semibold">{hoy.critical_stock}</span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="border-t border-dax-border-dim pt-3 space-y-1.5 text-sm">
                  {b.phone && <div className="flex items-center gap-2 text-dax-faint"><i className="fa-solid fa-phone text-xs" />{b.phone}</div>}
                  {b.address && <div className="flex items-center gap-2 text-dax-faint text-xs"><i className="fa-solid fa-location-dot" />{b.address}</div>}
                </div>
              )}
            </DaxCard>
          )
        })}
      </div>

      {branches.length === 0 && !errorCarga && (
        <DaxCard><div className="p-12 text-center text-dax-faint">Sin sucursales configuradas</div></DaxCard>
      )}

      {elegidaId && !elegida && (
        <DaxCard><p className="text-sm text-dax-danger">Sucursal no encontrada.</p></DaxCard>
      )}
      {elegida && <Detalle branch={elegida} onCerrar={() => elegir(null)} />}

      <Modal
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === 'crear' ? 'Nueva sucursal' : 'Editar sucursal'}
        size="md"
        footer={<>
          <button onClick={() => setModal(null)} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={guardar} disabled={guardando || !form.name.trim()} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
            {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
          </button>
        </>}
      >
        <div className="space-y-3">
          <div>
            <label className="dax-label" htmlFor="suc-nombre">Nombre</label>
            <input id="suc-nombre" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="dax-input w-full" placeholder="Sucursal Centro" />
          </div>
          <div>
            <label className="dax-label" htmlFor="suc-tipo">Tipo</label>
            <select id="suc-tipo" value={form.branch_type} onChange={(e) => setForm((f) => ({ ...f, branch_type: e.target.value as Branch['branch_type'] }))} className="dax-input w-full">
              {TIPOS.map((t) => <option key={t} value={t}>{TIPO[t]}</option>)}
            </select>
          </div>
          <div>
            <label className="dax-label" htmlFor="suc-telefono">Teléfono</label>
            <input id="suc-telefono" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} className="dax-input w-full" />
          </div>
          <div>
            <label className="dax-label" htmlFor="suc-direccion">Dirección</label>
            <input id="suc-direccion" value={form.address} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} className="dax-input w-full" />
          </div>
          {modal === 'editar' && (
            <div className="space-y-2 pt-1">
              <label className="flex items-start gap-3 text-xs text-dax-text cursor-pointer">
                <input type="checkbox" className="w-4 h-4 mt-0.5" checked={form.can_sell} onChange={(e) => setForm((f) => ({ ...f, can_sell: e.target.checked }))} />
                <span>Vende
                  <span className="block text-[10px] text-dax-faint">Aparece en el punto de venta y cuenta para el tope de sucursales del plan.</span>
                </span>
              </label>
              <label className="flex items-start gap-3 text-xs text-dax-text cursor-pointer">
                <input type="checkbox" className="w-4 h-4 mt-0.5" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
                <span>Activa
                  <span className="block text-[10px] text-dax-faint">Desactívala en lugar de borrarla cuando ya tiene ventas o cortes.</span>
                </span>
              </label>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
