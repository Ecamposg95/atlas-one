// frontend/src/pages/reports/Reportes.tsx
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { reportsApi, type CommandCenterStats, type DashboardData } from '../../api/reports'
import { organizationApi, type Branch } from '../../api/organization'
import {
  GraficaBarras, GraficaDona, GraficaLinea, colorMetodo, etiquetaHora, recortarHoras, useTemaGrafica,
} from '../../components/graficas'
import { SalesHeatmap } from '../../components/reports/Heatmap'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { KpiCard } from '../../components/ui/KpiCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { Spinner } from '../../components/ui/Spinner'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { variacion } from '../../utils/variacion'
import {
  PRESETS, diasDelRango, etiquetaRango, etiquetasTendencia, presetActivo, rangoPreset, type Rango,
} from './presetsReportes'

/**
 * Reportes (spec 2026-10-23 §3.2): periodos y comparativos contra el periodo
 * anterior; el "hoy" vive en el Inicio. Un solo componente para todos:
 * `/hq/reports-hub` lo monta con `conSucursales` (selector, visible solo con
 * más de una sucursal) y `/reports` fijado a la sucursal del usuario (el
 * backend la impone a cajera y gerente por `resolver_ambito`). Datos:
 * `/reports/dashboard` en una llamada y, solo con selector,
 * `/reports/command-center/stats` para la comparativa de sucursales (es de
 * toda la organización y no tiene guardia de rol: una cajera no lo pide).
 * Sustituye a `finance/Reports.tsx` y `hq/HQReportsHub.tsx`; sin velocímetro,
 * conteo animado ni sondeo cada 30 s. Solo tokens `dax-*`.
 */
const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']
const piezas = (n: number) => {
  const r = Math.round(n * 100) / 100
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`

/** Título de sección: la pregunta que responde y una nota a la derecha. */
function Titulo({ children, nota }: { children: ReactNode; nota?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 mb-3">
      <p className="dax-section-title">{children}</p>
      {nota && <p className="text-xs text-dax-faint text-right">{nota}</p>}
    </div>
  )
}
const Vacio = ({ children }: { children: ReactNode }) => <p className="text-sm text-dax-muted">{children}</p>

export function Reportes({ conSucursales = false }: { conSucursales?: boolean }) {
  const esTelefono = useEsTelefono()
  const tema = useTemaGrafica()
  // Los presets usan la fecha local del navegador (no UTC), como el resto de filtros de fecha.
  const [rango, setRango] = useState<Rango>(() => rangoPreset('7d'))
  const [desde, setDesde] = useState(rango.inicio)
  const [hasta, setHasta] = useState(rango.fin)
  const [sucursal, setSucursal] = useState<number | ''>('')
  const [sucursales, setSucursales] = useState<Branch[]>([])
  const [data, setData] = useState<DashboardData | null>(null)
  const [cc, setCc] = useState<CommandCenterStats | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportando, setExportando] = useState(false)

  useEffect(() => {
    if (!conSucursales) return
    organizationApi.getBranches()
      .then((bs) => setSucursales(bs.filter((b) => b.is_active !== false)))
      .catch(() => { /* sin lista no hay selector; el reporte sigue */ })
  }, [conSucursales])

  useEffect(() => {
    let vivo = true
    setCargando(true)
    setError(null)
    const params = {
      start_date: rango.inicio, end_date: rango.fin,
      ...(conSucursales && sucursal !== '' ? { branch_id: sucursal } : {}),
    }
    const peticiones: Promise<unknown>[] = [reportsApi.dashboard(params).then((d) => { if (vivo) setData(d) })]
    if (conSucursales) {
      peticiones.push(
        reportsApi.commandCenterStats({ start_date: rango.inicio, end_date: rango.fin })
          .then((c) => { if (vivo) setCc(c) })
          .catch(() => { if (vivo) setCc(null) }),
      )
    }
    Promise.all(peticiones)
      .catch((e: any) => {
        if (!vivo) return
        setData(null)
        setError(errorDetailText(e?.response?.data?.detail, 'No se pudieron cargar los reportes. Vuelve a intentar en unos segundos.'))
      })
      .finally(() => { if (vivo) setCargando(false) })
    return () => { vivo = false }
  }, [rango, sucursal, conSucursales])

  const aplicar = (r: Rango) => { setDesde(r.inicio); setHasta(r.fin); setRango(r) }
  const aplicarFechas = () => {
    if (!desde || !hasta) return
    if (hasta < desde) { setError('La fecha final no puede ser anterior a la inicial.'); return }
    aplicar({ inicio: desde, fin: hasta })
  }
  const exportar = async () => {
    setExportando(true)
    try {
      await reportsApi.exportCsv({
        start_date: rango.inicio, end_date: rango.fin,
        branch_id: conSucursales && sucursal !== '' ? sucursal : undefined,
      })
    } catch {
      setError('No se pudo exportar el CSV.')
    } finally {
      setExportando(false)
    }
  }

  const activo = presetActivo(rango)
  const dias = diasDelRango(rango)
  const etiquetaPeriodo = etiquetaRango(rango)
  const k = data?.kpis
  // "Tiene costos": algo de lo vendido en el periodo lleva costo (spec §3.2).
  const conCosto = k ? Math.max(0, (k.gross_sales ?? k.sales) - (k.sales_without_cost ?? 0)) : 0
  const conUtilidad = k?.gross_profit != null && conCosto > 0

  const metodos = useMemo(() => {
    const crudo = data?.charts.payments ?? {}
    const claves = [...ORDEN_METODOS.filter((m) => m in crudo), ...Object.keys(crudo).filter((m) => !ORDEN_METODOS.includes(m))]
    return claves.map((m) => ({ clave: m, nombre: METODOS[m] ?? m, total: crudo[m].total, count: crudo[m].count, color: colorMetodo(m, tema) }))
  }, [data, tema])
  const totalMetodos = metodos.reduce((s, m) => s + m.total, 0)

  // Las 24 horas sumadas en el periodo; la gráfica pinta el promedio por día del rango.
  const horas = useMemo(() => (data?.charts.hourly.data ?? []).map((neta, hora) => ({ hora, neta })), [data])
  const ventana = useMemo(() => recortarHoras(horas), [horas])
  const sinHoras = horas.every((h) => h.neta === 0)
  const etiquetasHoras = useMemo(() => horas.slice(ventana.desde, ventana.hasta + 1).map((h) => etiquetaHora(h.hora)), [horas, ventana])
  const valoresHoras = useMemo(() => horas.slice(ventana.desde, ventana.hasta + 1).map((h) => h.neta / dias), [horas, ventana, dias])

  const tendencia = data?.charts.trend
  const previa = data?.charts.trend_previous
  const etiquetasTendenciaDia = useMemo(
    () => etiquetasTendencia(rango, tendencia?.data.length ?? 0, tendencia?.labels ?? []),
    [rango, tendencia],
  )
  const seriesTendencia = useMemo(() => [
    { nombre: 'Este periodo', valores: tendencia?.data ?? [] },
    ...(previa ? [{ nombre: 'Periodo anterior', valores: previa.data, comparativo: true }] : []),
  ], [tendencia, previa])
  const partesDona = useMemo(() => metodos.map((m) => ({ nombre: m.nombre, valor: m.total, color: m.color })), [metodos])

  const sucursalesCc = useMemo(() => {
    if (!conSucursales || !cc) return []
    return cc.branches.filter((b) => !b.is_hq || b.total_sales > 0).sort((a, b) => b.total_sales - a.total_sales)
  }, [cc, conSucursales])

  const etiquetasSucursales = useMemo(() => sucursalesCc.map((b) => b.name), [sucursalesCc])
  const valoresSucursales = useMemo(() => sucursalesCc.map((b) => b.total_sales), [sucursalesCc])

  const top = data?.top_products ?? []
  const maxTop = Math.max(0, ...top.map((p) => p.total ?? 0))
  const heatmap = data?.charts.heatmap ?? []

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-dax-text">Reportes</h1>}
        descripcion="Periodos y comparativos contra el periodo anterior. Lo de hoy está en el Inicio."
        acciones={(
          <button type="button" onClick={exportar} disabled={exportando || cargando || !data} className="dax-btn-secondary text-xs">
            <i className={`fa-solid ${exportando ? 'fa-spinner fa-spin' : 'fa-file-arrow-down'}`} aria-hidden="true" />{' '}
            {exportando ? 'Exportando…' : 'Exportar CSV'}
          </button>
        )}
      />

      <BarraFiltros
        className="items-center"
        accion={<button type="button" onClick={aplicarFechas} className="dax-btn-primary text-xs">Aplicar</button>}
      >
        <div className="flex flex-wrap gap-1" role="group" aria-label="Periodo">
          {PRESETS.map((p) => (
            <button
              key={p.clave}
              type="button"
              onClick={() => aplicar(rangoPreset(p.clave))}
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
        {conSucursales && sucursales.length > 1 && (
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
      </BarraFiltros>

      {error && <p role="alert" className="text-sm text-dax-danger">{error}</p>}

      {cargando && !data ? (
        <Spinner text="Cargando reportes…" />
      ) : !data || !k ? (
        !error && <DaxCard><Vacio>Sin datos para el periodo.</Vacio></DaxCard>
      ) : (
        <>
          {/* Cifras del periodo con variación contra el anterior */}
          <div className={`grid grid-cols-1 sm:grid-cols-2 ${conUtilidad ? 'lg:grid-cols-5' : 'lg:grid-cols-4'} gap-3`}>
            <KpiCard etiqueta="Venta neta" valor={formatCurrency(k.sales)} detalle={etiquetaPeriodo}
              variacion={variacion(k.sales, k.prev_sales ?? 0, 'vs periodo anterior')} data-testid="kpi-venta" />
            <KpiCard etiqueta="Tickets" valor={String(k.orders)} detalle={plural(k.orders, 'venta', 'ventas')}
              variacion={variacion(k.orders, k.prev_orders ?? 0, 'vs periodo anterior')} data-testid="kpi-tickets" />
            <KpiCard etiqueta="Ticket promedio" valor={formatCurrency(k.avg_ticket)}
              variacion={variacion(k.avg_ticket, k.prev_avg_ticket ?? 0, 'vs periodo anterior')} data-testid="kpi-promedio" />
            <KpiCard etiqueta="Devoluciones" valor={formatCurrency(k.returns ?? 0)} detalle={plural(k.returns_count ?? 0, 'devolución', 'devoluciones')}
              variacion={variacion(k.returns ?? 0, k.prev_returns ?? 0, 'vs periodo anterior', true)} data-testid="kpi-devoluciones" />
            {conUtilidad && (
              <KpiCard etiqueta="Utilidad bruta" valor={formatCurrency(k.gross_profit as number)}
                detalle={`sobre ${formatCurrency(conCosto)} con costo${(k.sales_without_cost ?? 0) > 0 ? ` · ${formatCurrency(k.sales_without_cost as number)} sin costo` : ''}`}
                variacion={variacion(k.gross_profit as number, k.prev_gross_profit ?? 0, 'vs periodo anterior')} data-testid="kpi-utilidad" />
            )}
          </div>

          {/* Tendencia (8) · Cómo me pagaron (4) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <DaxCard className="lg:col-span-8">
              <Titulo nota="El periodo anterior, en gris">¿Cómo fue cada día?</Titulo>
              {data.charts.trend.data.length === 0 ? <Vacio>Sin ventas en el periodo.</Vacio> : (
                <GraficaLinea etiquetas={etiquetasTendenciaDia} series={seriesTendencia} />
              )}
            </DaxCard>
            <DaxCard className="lg:col-span-4">
              <Titulo>¿Cómo me pagaron?</Titulo>
              {metodos.length === 0 ? <Vacio>Sin cobros en el periodo.</Vacio> : (
                <div className="space-y-3">
                  <GraficaDona
                    partes={partesDona}
                    alto={200}
                    centro={(
                      <>
                        <span className="dax-kpi-label">Total</span>
                        <span className="text-base font-black tabular-nums text-dax-text">{formatCurrency(totalMetodos)}</span>
                      </>
                    )}
                  />
                  <ul className="space-y-1">
                    {metodos.map((m) => (
                      <li key={m.clave} data-testid="metodo" className="flex justify-between text-sm">
                        <span className="text-dax-muted">{m.nombre} <span className="text-dax-faint">· {plural(m.count, 'cobro', 'cobros')}</span></span>
                        <span className="font-bold tabular-nums text-dax-text">{formatCurrency(m.total)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </DaxCard>
          </div>

          {/* Ventas por hora (5) · Día y hora (7) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <DaxCard className="lg:col-span-5">
              <Titulo nota={dias > 1 ? `Promedio por hora en ${dias} días` : etiquetaPeriodo}>¿A qué hora vendo más?</Titulo>
              {sinHoras ? <Vacio>Sin ventas en el periodo.</Vacio> : (
                <GraficaBarras
                  etiquetas={etiquetasHoras}
                  valores={valoresHoras}
                  alto={220}
                  nombre="Venta por hora"
                />
              )}
            </DaxCard>
            <DaxCard className="lg:col-span-7">
              <Titulo>¿Qué días y a qué horas vendo más?</Titulo>
              {heatmap.length === 0 ? <Vacio>Sin desglose por día y hora para este periodo.</Vacio> : (
                <SalesHeatmap data={heatmap} hourStart={ventana.desde} hourEnd={ventana.hasta} />
              )}
            </DaxCard>
          </div>

          {/* Sucursales: solo con selector y más de una */}
          {sucursalesCc.length > 1 && (
            <DaxCard>
              <Titulo nota="Venta neta del periodo">¿Cómo va cada sucursal?</Titulo>
              <div data-testid="sucursales">
                <GraficaBarras
                  etiquetas={etiquetasSucursales}
                  valores={valoresSucursales}
                  horizontal
                  alto={Math.max(120, 36 * sucursalesCc.length + 40)}
                  nombre="Venta neta"
                />
                <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
                  {sucursalesCc.map((b) => (
                    <li key={b.id} className="flex justify-between border-t border-dax-border-dim py-1">
                      <span className="text-dax-muted">{b.name}</span>
                      <span className="font-bold tabular-nums text-dax-text">{formatCurrency(b.total_sales)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </DaxCard>
          )}

          {/* Lo más vendido */}
          <DaxCard>
            <Titulo nota="Por piezas; la barra es su parte del importe">¿Qué se vendió más?</Titulo>
            {top.length === 0 ? <Vacio>Sin ventas en el periodo.</Vacio> : esTelefono ? (
              <div data-testid="top">
                <ListaTarjetas>
                  {top.map((p, i) => (
                    <TarjetaFila key={`${p.name}-${i}`} titulo={`${i + 1}. ${p.name}`} subtitulo={piezas(p.qty)} importe={formatCurrency(p.total ?? 0)} />
                  ))}
                </ListaTarjetas>
              </div>
            ) : (
              <table className="w-full text-sm" data-testid="top">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-widest text-dax-faint">
                    <th className="py-1 w-8">#</th>
                    <th className="py-1">Producto</th>
                    <th className="py-1 text-right">Piezas</th>
                    <th className="py-1 text-right">Importe</th>
                    <th className="py-1 w-32"><span className="sr-only">Proporción del importe</span></th>
                  </tr>
                </thead>
                <tbody>
                  {top.map((p, i) => (
                    <tr key={`${p.name}-${i}`} className="border-t border-dax-border-dim">
                      <td className="py-1.5 text-dax-faint tabular-nums">{i + 1}</td>
                      <td className="py-1.5 text-dax-text">{p.name}</td>
                      <td className="py-1.5 text-right tabular-nums text-dax-muted">{piezas(p.qty)}</td>
                      <td className="py-1.5 text-right tabular-nums font-bold text-dax-text">{formatCurrency(p.total ?? 0)}</td>
                      <td className="py-1.5 pl-3">
                        <div className="h-1.5 rounded-full bg-dax-border-dim overflow-hidden">
                          <div className="h-full rounded-full bg-dax-accent"
                            style={{ width: `${maxTop > 0 ? ((p.total ?? 0) / maxTop) * 100 : 0}%` }} /* estilo dinámico: el ancho es el dato */ />
                        </div>
                      </td>
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
