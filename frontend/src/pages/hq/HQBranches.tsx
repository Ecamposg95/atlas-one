import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { reportsApi, type CommandCenterStats, type DashboardData } from '../../api/reports'
import { organizationApi, type Branch } from '../../api/organization'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { formatCurrency } from '../../utils/currency'
import { todayStr } from '../../utils/dates'

/**
 * Sucursales (SP6, pregunta 7 "¿cómo va cada sucursal?"): la rejilla de
 * tarjetas y, al elegir una, su detalle de hoy debajo, en la misma pantalla.
 * `/hq/branches/:branchId` monta esto mismo con esa sucursal elegida, así los
 * enlaces viejos a `HQBranchDetail` siguen abriendo.
 */

const TIPO: Record<string, string> = { HQ: 'Casa Matriz', STORE: 'Sucursal', WAREHOUSE: 'Almacén', OFFICE: 'Oficina' }

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
    { label: 'Ventas hoy', value: formatCurrency(datos?.kpis.sales ?? 0), color: 'text-emerald-400' },
    { label: 'Tickets', value: String(datos?.kpis.orders ?? 0), color: 'text-blue-400' },
    { label: 'Ticket promedio', value: formatCurrency(datos?.kpis.avg_ticket ?? 0), color: 'text-indigo-400' },
    { label: 'Pendientes', value: String(datos?.kpis.pending ?? 0), color: 'text-amber-400' },
  ]
  const top = datos?.top_products.slice(0, 5) ?? []
  const poca = datos?.low_stock ?? []
  const ultimas = datos?.recent_sales ?? []

  return (
    <div className="space-y-4" data-testid="detalle-sucursal">
      <div className="flex max-md:flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest">Hoy en</p>
          <p className="text-lg font-black text-white">{branch.name}</p>
          <p className="text-xs text-slate-500">{TIPO[branch.branch_type] ?? branch.branch_type}{branch.address ? ` · ${branch.address}` : ''}{branch.phone ? ` · ${branch.phone}` : ''}</p>
        </div>
        <button onClick={onCerrar} className="dax-btn-secondary text-xs max-md:min-h-[44px]"><i className="fa-solid fa-xmark" /> Cerrar</button>
      </div>

      {error ? (
        <DaxCard><p className="text-sm text-rose-300">{error}</p></DaxCard>
      ) : !datos ? (
        <Spinner text="Cargando sucursal..." />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {kpis.map((k) => (
              <div key={k.label} className="dax-card p-4">
                <p className="text-[10px] uppercase text-slate-500 font-bold tracking-widest">{k.label}</p>
                <p className={`text-2xl font-bold tabular-nums mt-1 ${k.color}`}>{k.value}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <DaxCard>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">Lo más vendido hoy</p>
              {top.length === 0 ? (
                <p className="text-sm text-slate-400">Sin ventas registradas hoy.</p>
              ) : (
                <ul className="space-y-1">
                  {top.map((p, i) => (
                    <li key={i} className="flex justify-between text-sm gap-2">
                      <span className="text-slate-300 truncate">{p.name}</span>
                      <span className="text-slate-500 tabular-nums shrink-0">{p.qty} pz</span>
                    </li>
                  ))}
                </ul>
              )}
            </DaxCard>
            <DaxCard>
              <p className="text-[10px] font-black uppercase tracking-widest text-amber-400 mb-3">Se está acabando</p>
              {esTelefono ? (
                <ListaTarjetas vacio={poca.length === 0} textoVacio="Nada se está acabando.">
                  {poca.map((p, i) => <TarjetaFila key={i} titulo={p.name} subtitulo={p.sku} importe={`${p.stock} pz`} />)}
                </ListaTarjetas>
              ) : poca.length === 0 ? (
                <p className="text-sm text-slate-400">Nada se está acabando.</p>
              ) : (
                <ul className="space-y-1">
                  {poca.map((p, i) => (
                    <li key={i} className="flex justify-between text-sm gap-2">
                      <span className="text-slate-300 truncate">{p.name} <span className="font-mono text-xs text-slate-500">{p.sku}</span></span>
                      <span className="text-amber-400 font-bold tabular-nums shrink-0">{p.stock}</span>
                    </li>
                  ))}
                </ul>
              )}
            </DaxCard>
          </div>

          <DaxCard>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">Últimas ventas</p>
            {esTelefono ? (
              <ListaTarjetas vacio={ultimas.length === 0} textoVacio="Sin ventas hoy.">
                {ultimas.map((s, i) => (
                  <TarjetaFila key={i} titulo={s.folio} subtitulo={`${s.time} · ${s.customer || 'Público general'}`} importe={formatCurrency(s.total)} />
                ))}
              </ListaTarjetas>
            ) : ultimas.length === 0 ? (
              <p className="text-sm text-slate-400">Sin ventas hoy.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[10px] text-slate-500 uppercase text-left">
                    <th className="pb-2">Hora</th><th className="pb-2">Folio</th><th className="pb-2">Cliente</th><th className="pb-2 text-right">Total</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {ultimas.map((s, i) => (
                    <tr key={i} className="border-t border-slate-800/60">
                      <td className="py-2 text-slate-500 font-mono">{s.time}</td>
                      <td className="py-2 font-mono text-indigo-400">{s.folio}</td>
                      <td className="py-2">{s.customer || 'Público general'}</td>
                      <td className="py-2 text-right font-bold text-emerald-400">{formatCurrency(s.total)}</td>
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

export function HQBranches() {
  const { branchId } = useParams<{ branchId: string }>()
  const navigate = useNavigate()
  const [branches, setBranches] = useState<Branch[]>([])
  const [stats, setStats] = useState<CommandCenterStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const today = todayStr()
    Promise.all([
      organizationApi.getBranches(),
      reportsApi.commandCenterStats({ start_date: today, end_date: today }),
    ]).then(([b, s]) => { setBranches(b); setStats(s) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const branchStats = (id: number) => stats?.branches?.find((b) => b.id === id)
  const elegida = branchId ? branches.find((b) => b.id === Number(branchId)) ?? null : null

  if (loading) return <Spinner text="Cargando sucursales..." />

  // "Abierta" es el estado que calcula el backend (turno abierto o ventas hoy), no `pending_cuts`.
  const abiertas = stats?.branches?.filter((b) => b.status === 'ONLINE').length ?? 0
  const alertas = stats?.alerts?.length ?? 0

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-store text-indigo-400 text-xl" />
            <h1 className="text-2xl font-black text-white">Sucursales</h1>
          </div>
        }
        descripcion="Cómo va cada sucursal hoy. Toca una para ver su detalle."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <DaxCard>
          <p className="text-[10px] uppercase text-slate-500 font-bold mb-1">Sucursales</p>
          <p className="text-2xl font-bold text-white tabular-nums">{branches.length}</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[10px] uppercase text-slate-500 font-bold mb-1">Abiertas hoy</p>
          <p className="text-2xl font-bold text-emerald-400 tabular-nums">{abiertas}</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[10px] uppercase text-slate-500 font-bold mb-1">Sin venta hoy</p>
          <p className="text-2xl font-bold text-slate-400 tabular-nums">{(stats?.branches?.length ?? 0) - abiertas}</p>
        </DaxCard>
        <DaxCard>
          <p className="text-[10px] uppercase text-slate-500 font-bold mb-1">Se está acabando</p>
          <p className="text-2xl font-bold text-amber-400 tabular-nums">{alertas}</p>
        </DaxCard>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {branches.map((b) => {
          const bStats = branchStats(b.id)
          const abierta = bStats?.status === 'ONLINE'
          const activa = elegida?.id === b.id
          return (
            <button
              key={b.id}
              type="button"
              onClick={() => navigate(activa ? '/hq/branches' : `/hq/branches/${b.id}`)}
              aria-pressed={activa}
              className={`text-left rounded-xl transition-opacity hover:opacity-90 max-md:min-h-[44px] ${activa ? 'ring-2 ring-indigo-500/60' : ''}`}
            >
              <DaxCard className="h-full">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="font-black text-white text-sm">{b.name}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">{TIPO[b.branch_type] ?? b.branch_type}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <div className={`flex items-center gap-1.5 text-xs font-semibold ${abierta ? 'text-emerald-400' : 'text-slate-600'}`}>
                      <i className="fa-solid fa-circle text-[8px]" />
                      {abierta ? 'Abierta' : 'Cerrada'}
                    </div>
                    <Badge variant={b.is_active ? 'green' : 'slate'}>{b.is_active ? 'Activa' : 'Inactiva'}</Badge>
                  </div>
                </div>

                {bStats ? (
                  <div className="space-y-1.5 text-sm border-t border-slate-700/30 pt-3">
                    <div className="flex justify-between text-slate-400">
                      <span>Ventas hoy</span>
                      <span className="text-emerald-400 font-semibold">{formatCurrency(bStats.total_sales)}</span>
                    </div>
                    <div className="flex justify-between text-slate-400">
                      <span>Turnos abiertos</span>
                      <span className="text-indigo-400 font-semibold">{bStats.pending_cuts ?? 0}</span>
                    </div>
                    {bStats.critical_stock > 0 && (
                      <div className="flex justify-between text-slate-400">
                        <span>Se está acabando</span>
                        <span className="text-amber-400 font-semibold">{bStats.critical_stock}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="border-t border-slate-700/30 pt-3 space-y-1.5 text-sm">
                    {b.phone && <div className="flex items-center gap-2 text-slate-500"><i className="fa-solid fa-phone text-xs" />{b.phone}</div>}
                    {b.address && <div className="flex items-center gap-2 text-slate-500 text-xs"><i className="fa-solid fa-location-dot" />{b.address}</div>}
                  </div>
                )}
              </DaxCard>
            </button>
          )
        })}
      </div>

      {branches.length === 0 && (
        <DaxCard>
          <div className="p-12 text-center text-slate-600">Sin sucursales configuradas</div>
        </DaxCard>
      )}

      {branchId && !elegida && (
        <DaxCard><p className="text-sm text-rose-300">Sucursal no encontrada.</p></DaxCard>
      )}
      {elegida && <Detalle branch={elegida} onCerrar={() => navigate('/hq/branches')} />}
    </div>
  )
}
