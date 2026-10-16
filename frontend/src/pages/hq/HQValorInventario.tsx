import { useCallback, useEffect, useRef, useState } from 'react'
import { reportsApi, type AgruparValuacion, type ValuacionInventario } from '../../api/reports'
import { organizationApi, type Branch } from '../../api/organization'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { BarraFiltros } from '../../components/ui/BarraFiltros'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { csvValuacion, descargarCsv, ETIQUETA_GRUPO } from '../../utils/valuacionCsv'

/**
 * /hq/valor-inventario — ¿cuánto vale mi existencia hoy, y dónde?
 *
 * Desglose del mismo dato que la tarjeta del inicio: por sucursal,
 * departamento o marca, con filtro de sucursal y exportación CSV armada en
 * el cliente (`utils/valuacionCsv`). El backend decide qué ve cada rol:
 * `ve_costo=false` (gerente) llega sin la columna de costo y ya limitado a su
 * sucursal, así que aquí ni se le ofrece el selector.
 */
const piezasTxt = (n: number) => Math.round(n).toLocaleString('es-MX')

export function HQValorInventario() {
  const user = useAuthStore((s) => s.user)
  const esGerente = user?.role === 'GERENTE'
  const telefono = useEsTelefono()

  const [agrupar, setAgrupar] = useState<AgruparValuacion>('sucursal')
  const [branchId, setBranchId] = useState<number | ''>('')
  const [branches, setBranches] = useState<Branch[]>([])
  const [data, setData] = useState<ValuacionInventario | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (esGerente) return // el gerente solo ve su sucursal: sin selector
    organizationApi.getBranches().then(setBranches).catch(() => {})
  }, [esGerente])

  const reqId = useRef(0)
  const load = useCallback(async () => {
    const mio = ++reqId.current
    setLoading(true)
    try {
      const res = await reportsApi.valorInventario({
        agrupar,
        ...(branchId !== '' ? { branch_id: branchId } : {}),
      })
      if (mio !== reqId.current) return // respuesta vieja: ya hay otra en camino
      setData(res)
      setError(null)
    } catch (e: any) {
      if (mio !== reqId.current) return
      setError(errorDetailText(
        e?.response?.data?.detail,
        'No se pudo calcular el valor de la tienda. Vuelve a intentar en unos segundos.',
      ))
    } finally {
      if (mio === reqId.current) setLoading(false)
    }
  }, [agrupar, branchId])

  useEffect(() => { load() }, [load])

  const exportar = () => {
    if (!data) { toast.warning('Todavía no hay datos que exportar.'); return }
    const fecha = new Date().toISOString().slice(0, 10)
    descargarCsv(csvValuacion(data), `valor-tienda-${data.agrupar}-${fecha}.csv`)
  }

  const veCosto = data?.ve_costo ?? false
  const t = data?.totales
  const grupos = data?.grupos ?? []
  const costoIncompleto = (t?.piezas_sin_costo ?? 0) > 0

  return (
    <div className="space-y-4">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-bold">Valor de la tienda</h1>}
        descripcion="Existencia de hoy a precio de venta y a costo. Sin instantáneas: lo que ves es lo que hay ahora."
        acciones={
          <button type="button" onClick={exportar} disabled={!data || loading} className="dax-btn-secondary">
            <i className="fa-solid fa-file-csv mr-1" aria-hidden="true" /> Exportar CSV
          </button>
        }
      />

      <BarraFiltros accion={<button type="button" onClick={load} className="dax-btn-primary">Actualizar</button>}>
        <label className="flex flex-col text-xs" style={{ color: 'var(--dax-text-muted)' }}>
          Agrupar por
          <select className="dax-input w-44" value={agrupar} onChange={(e) => setAgrupar(e.target.value as AgruparValuacion)}>
            <option value="sucursal">Sucursal</option>
            <option value="departamento">Departamento</option>
            <option value="marca">Marca</option>
          </select>
        </label>
        {!esGerente && (
          <label className="flex flex-col text-xs" style={{ color: 'var(--dax-text-muted)' }}>
            Sucursal
            <select
              className="dax-input w-52"
              value={branchId}
              onChange={(e) => setBranchId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">Todas las que venden</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}{b.can_sell === false ? ' (no vende)' : ''}
                </option>
              ))}
            </select>
          </label>
        )}
      </BarraFiltros>

      {error && (
        <div className="dax-card rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 flex items-start gap-3">
          <i className="fas fa-triangle-exclamation text-rose-400 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-rose-200 flex-1">{error}</p>
          <button type="button" onClick={load} className="dax-btn-secondary text-xs">Reintentar</button>
        </div>
      )}

      {t && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Valor a precio de venta</p>
            <p className="text-xl font-bold tabular-nums">{formatCurrency(t.valor_venta)}</p>
          </div>
          {veCosto && (
            <div className="dax-card p-4">
              <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Valor a costo</p>
              <p className="text-xl font-bold tabular-nums">{formatCurrency(t.valor_costo ?? 0)}</p>
              {costoIncompleto && (
                <p className="text-[10px] font-bold text-amber-400">incompleto: faltan costos</p>
              )}
            </div>
          )}
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Piezas · SKUs</p>
            <p className="text-xl font-bold tabular-nums">{piezasTxt(t.piezas)} · {t.skus}</p>
          </div>
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Sin costo</p>
            <p className={`text-xl font-bold tabular-nums ${costoIncompleto ? 'text-amber-400' : ''}`}>
              {piezasTxt(t.piezas_sin_costo)} pz · {t.skus_sin_costo} SKU{t.skus_sin_costo === 1 ? '' : 's'}
            </p>
          </div>
        </div>
      )}

      {telefono ? (
        <ListaTarjetas cargando={loading && !data} vacio={grupos.length === 0} textoVacio="Sin existencias que valuar">
          {grupos.map((g) => (
            <TarjetaFila
              key={g.clave || 'sin'}
              titulo={g.nombre}
              subtitulo={`${piezasTxt(g.piezas)} piezas · ${g.skus} SKUs`}
              importe={formatCurrency(g.valor_venta)}
              datos={[
                ...(veCosto ? [{ etiqueta: 'A costo', valor: formatCurrency(g.valor_costo ?? 0) }] : []),
                { etiqueta: 'Sin costo', valor: `${piezasTxt(g.piezas_sin_costo)} pz` },
              ]}
            />
          ))}
        </ListaTarjetas>
      ) : (
        <div className="dax-card overflow-x-auto">
          {loading && !data ? (
            <Spinner text="Calculando…" />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  <th className="p-3">{ETIQUETA_GRUPO[data?.agrupar ?? agrupar]}</th>
                  <th className="p-3 text-right">Piezas</th>
                  <th className="p-3 text-right">SKUs</th>
                  <th className="p-3 text-right">Valor a venta</th>
                  {veCosto && <th className="p-3 text-right">Valor a costo</th>}
                  <th className="p-3 text-right">Piezas sin costo</th>
                </tr>
              </thead>
              <tbody>
                {grupos.length === 0 && (
                  <tr><td colSpan={veCosto ? 6 : 5} className="p-8 text-center" style={{ color: 'var(--dax-text-muted)' }}>Sin existencias que valuar</td></tr>
                )}
                {grupos.map((g) => (
                  <tr key={g.clave || 'sin'} style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
                    <td className="p-3 font-medium">{g.nombre}</td>
                    <td className="p-3 text-right tabular-nums">{piezasTxt(g.piezas)}</td>
                    <td className="p-3 text-right tabular-nums">{g.skus}</td>
                    <td className="p-3 text-right tabular-nums">{formatCurrency(g.valor_venta)}</td>
                    {veCosto && <td className="p-3 text-right tabular-nums">{formatCurrency(g.valor_costo ?? 0)}</td>}
                    <td className={`p-3 text-right tabular-nums ${g.piezas_sin_costo > 0 ? 'text-amber-400' : ''}`}>{piezasTxt(g.piezas_sin_costo)}</td>
                  </tr>
                ))}
              </tbody>
              {t && grupos.length > 0 && (
                <tfoot>
                  <tr className="font-bold" style={{ borderTop: '2px solid var(--dax-border-dim)' }}>
                    <td className="p-3">Total</td>
                    <td className="p-3 text-right tabular-nums">{piezasTxt(t.piezas)}</td>
                    <td className="p-3 text-right tabular-nums">{t.skus}</td>
                    <td className="p-3 text-right tabular-nums">{formatCurrency(t.valor_venta)}</td>
                    {veCosto && <td className="p-3 text-right tabular-nums">{formatCurrency(t.valor_costo ?? 0)}</td>}
                    <td className="p-3 text-right tabular-nums">{piezasTxt(t.piezas_sin_costo)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          )}
        </div>
      )}
    </div>
  )
}

export default HQValorInventario
