import { useCallback, useEffect, useRef, useState } from 'react'
import { reportsApi, type ValuacionGrupo, type ValuacionInventario } from '../../api/reports'
import { organizationApi, type Branch } from '../../api/organization'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { BarraFiltros } from '../../components/ui/BarraFiltros'
import { DistribucionValor } from '../../components/reports/DistribucionValor'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { csvValuacion, descargarCsv } from '../../utils/valuacionCsv'

/**
 * /hq/valor-inventario — ¿cuánto vale mi existencia hoy, y cómo se reparte?
 *
 * Totales arriba (los mismos de la tarjeta del inicio) y, debajo, la
 * distribución del valor a venta por departamento y por marca a la vez, con
 * porcentaje y barra. Tocar un departamento acota el panel de marcas a ese
 * departamento (`department_id`). Con más de una sucursal que vende y sin
 * filtro, un tercer panel reparte por sucursal. Cada panel exporta su CSV
 * (`utils/valuacionCsv`). El backend decide qué ve cada rol: `ve_costo=false`
 * (gerente) llega sin costo y ya limitado a su sucursal, así que aquí ni se
 * le ofrece el selector.
 */
const piezasTxt = (n: number) => Math.round(n).toLocaleString('es-MX')
const nombreArchivo = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\w-]+/g, '_')

export function HQValorInventario() {
  const user = useAuthStore((s) => s.user)
  const esGerente = user?.role === 'GERENTE'
  const telefono = useEsTelefono()

  const [branchId, setBranchId] = useState<number | ''>('')
  const [branches, setBranches] = useState<Branch[]>([])
  const [depto, setDepto] = useState<ValuacionGrupo | null>(null) // acota el panel de marcas
  const [porDepto, setPorDepto] = useState<ValuacionInventario | null>(null)
  const [porMarca, setPorMarca] = useState<ValuacionInventario | null>(null)
  const [porSucursal, setPorSucursal] = useState<ValuacionInventario | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (esGerente) return // el gerente solo ve su sucursal: sin selector
    organizationApi.getBranches().then(setBranches).catch(() => {})
  }, [esGerente])

  // Con más de una sucursal que vende y sin filtro, el valor también se reparte por sucursal.
  const venden = branches.filter((b) => b.can_sell !== false && b.is_active)
  const conSucursales = !esGerente && branchId === '' && venden.length > 1

  const reqId = useRef(0)
  const load = useCallback(async () => {
    const mio = ++reqId.current
    setLoading(true)
    const sucursal = branchId !== '' ? { branch_id: branchId } : {}
    const departamento = depto && depto.clave ? { department_id: depto.clave } : {}
    try {
      const [d, m, s] = await Promise.all([
        reportsApi.valorInventario({ agrupar: 'departamento', ...sucursal }),
        reportsApi.valorInventario({ agrupar: 'marca', ...sucursal, ...departamento }),
        conSucursales ? reportsApi.valorInventario({ agrupar: 'sucursal' }) : Promise.resolve<ValuacionInventario | null>(null),
      ])
      if (mio !== reqId.current) return // respuesta vieja: ya hay otra en camino
      setPorDepto(d)
      setPorMarca(m)
      setPorSucursal(s)
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
  }, [branchId, depto, conSucursales])

  useEffect(() => { load() }, [load])

  const exportar = (d: ValuacionInventario | null, sufijo = '') => () => {
    if (!d) { toast.warning('Todavía no hay datos que exportar.'); return }
    const fecha = new Date().toISOString().slice(0, 10)
    descargarCsv(csvValuacion(d), `valor-tienda-${d.agrupar}${sufijo}-${fecha}.csv`)
  }

  const veCosto = porDepto?.ve_costo ?? false
  const t = porDepto?.totales
  const costoIncompleto = (t?.piezas_sin_costo ?? 0) > 0

  return (
    <div className="space-y-4">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-bold">Valor de la tienda</h1>}
        descripcion="Existencia de hoy a precio de venta y a costo, y cómo se reparte por departamento y marca. Sin instantáneas: lo que ves es lo que hay ahora."
      />

      <BarraFiltros accion={<button type="button" onClick={load} className="dax-btn-primary">Actualizar</button>}>
        {!esGerente && (
          <label className="flex flex-col text-xs text-dax-muted">
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
            <p className="text-[10px] font-black uppercase tracking-widest text-dax-muted">Valor a precio de venta</p>
            <p className="text-xl font-bold tabular-nums">{formatCurrency(t.valor_venta)}</p>
          </div>
          {veCosto && (
            <div className="dax-card p-4">
              <p className="text-[10px] font-black uppercase tracking-widest text-dax-muted">Valor a costo</p>
              <p className="text-xl font-bold tabular-nums">{formatCurrency(t.valor_costo ?? 0)}</p>
              {costoIncompleto && (
                <p className="text-[10px] font-bold text-amber-400">incompleto: faltan costos</p>
              )}
            </div>
          )}
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest text-dax-muted">Piezas · SKUs</p>
            <p className="text-xl font-bold tabular-nums">{piezasTxt(t.piezas)} · {t.skus}</p>
          </div>
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest text-dax-muted">Sin costo</p>
            <p className={`text-xl font-bold tabular-nums ${costoIncompleto ? 'text-amber-400' : ''}`}>
              {piezasTxt(t.piezas_sin_costo)} pz · {t.skus_sin_costo} SKU{t.skus_sin_costo === 1 ? '' : 's'}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <DistribucionValor
          data-testid="distribucion-departamento"
          titulo="Por departamento"
          etiqueta="Departamento"
          data={porDepto}
          cargando={loading}
          telefono={telefono}
          seleccionada={depto?.clave ?? null}
          onSeleccionar={(g) => setDepto(depto?.clave === g.clave ? null : g)}
          onExportar={exportar(porDepto)}
          aviso={<p className="text-xs text-dax-muted">Toca un departamento para ver sus marcas</p>}
        />
        <DistribucionValor
          data-testid="distribucion-marca"
          titulo="Por marca"
          etiqueta="Marca"
          data={porMarca}
          cargando={loading}
          telefono={telefono}
          onExportar={exportar(porMarca, depto ? `-${nombreArchivo(depto.nombre)}` : '')}
          aviso={depto ? (
            <p className="text-xs text-dax-muted">
              Marcas en <strong className="text-dax-text">{depto.nombre}</strong> · % dentro del departamento
              <button type="button" className="dax-btn-ghost ml-2 text-xs" onClick={() => setDepto(null)}>Quitar</button>
            </p>
          ) : (
            <p className="text-xs text-dax-muted">Toda la existencia consultada</p>
          )}
        />
      </div>

      {conSucursales && (
        <DistribucionValor
          data-testid="distribucion-sucursal"
          titulo="Por sucursal"
          etiqueta="Sucursal"
          data={porSucursal}
          cargando={loading}
          telefono={telefono}
          onExportar={exportar(porSucursal)}
        />
      )}
    </div>
  )
}

export default HQValorInventario
