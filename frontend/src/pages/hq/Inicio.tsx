// frontend/src/pages/hq/Inicio.tsx
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { reportsApi, type Inicio as DatosInicio, type ValuacionInventario } from '../../api/reports'
import { ValorTiendaCard } from '../../components/reports/ValorTiendaCard'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'

/**
 * Inicio del dueño (SP6, spec 2026-10-21 §3): UNA pantalla que responde sus
 * preguntas al entrar. Cada sección es una pregunta y enlaza a su detalle.
 * En perfil básico (FREE) pinta el subconjunto de hoy (preguntas 1, 2, 3, 4 y
 * 6) y pide `completo=false`; en completo pide las secciones nuevas (5, 7, 8).
 * Una llamada (`/reports/inicio`) + la tarjeta de valor de la tienda de SP3.
 * Sin gráficas: ninguna librería de gráficas viaja en este chunk.
 */

const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']

const hora = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) : ''
const fecha = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' }) : ''
const piezas = (n: number) => {
  const r = Math.round(n * 100) / 100
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}
const ventas = (n: number) => `${n} ${n === 1 ? 'venta' : 'ventas'}`
/** Enlaces de detalle por perfil: en básico, a las pantallas que SÍ están en su menú
 *  (Productos y Mis ventas); en completo, a Existencias (kardex, ajuste, costo) y Ventas HQ. */
const ENLACES = {
  basico:   { existencias: '/products', ventas: '/sales' },
  completo: { existencias: '/hq/inventory', ventas: '/hq/sales' },
} as const
const urlExistencias = (basico: boolean, sku: string, variantId: string) =>
  basico ? ENLACES.basico.existencias : `/hq/inventory?q=${encodeURIComponent(sku)}&variant=${encodeURIComponent(variantId)}`

function Cifra({ etiqueta, total, detalle, testId }: { etiqueta: string; total: number; detalle: string; testId: string }) {
  return (
    <div className="dax-card p-4" data-testid={testId}>
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">{etiqueta}</p>
      <p className="text-2xl font-bold text-white tabular-nums">{formatCurrency(total)}</p>
      <p className="text-xs text-slate-400">{detalle}</p>
    </div>
  )
}

/** Título de sección: la pregunta que responde y, si hay, el enlace a su detalle. */
function Titulo({ children, enlace }: { children: ReactNode; enlace?: { a: string; texto: string } }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">{children}</p>
      {enlace && (
        <Link to={enlace.a} className="text-[10px] font-bold text-indigo-400 hover:underline whitespace-nowrap max-md:inline-flex max-md:items-center max-md:min-h-[44px]">
          {enlace.texto}
        </Link>
      )}
    </div>
  )
}

const Vacio = ({ children }: { children: ReactNode }) => <p className="text-sm text-slate-400">{children}</p>
const Th = ({ children, der }: { children: ReactNode; der?: boolean }) => (
  <th className={`py-1 ${der ? 'text-right' : ''}`}>{children}</th>
)
const cabecera = 'text-left text-[10px] uppercase tracking-widest text-slate-500'
const fila = 'border-t border-slate-800/60'

function Corte({ corte }: { corte: DatosInicio['corte'] }) {
  if (corte.estado === 'abierto') {
    return (
      <div className="space-y-1" data-testid="corte">
        <p className="text-sm font-bold text-emerald-400">Turno abierto</p>
        <p className="text-sm text-slate-300">{corte.cajera ?? 'Sin nombre'} · desde las {hora(corte.abierto_en)}</p>
        <p className="text-sm text-slate-300">
          Efectivo esperado en caja:{' '}
          <span className="font-bold tabular-nums text-white">{formatCurrency(corte.efectivo_esperado)}</span>
        </p>
      </div>
    )
  }
  if (corte.estado === 'cerrado') {
    return (
      <div className="space-y-1" data-testid="corte">
        <p className="text-sm font-bold text-slate-300">Turno cerrado</p>
        <p className="text-sm text-slate-400">{corte.cajera ?? 'Sin nombre'} cerró a las {hora(corte.cerrado_en)}</p>
        <p className="text-sm text-slate-400">
          Contó <span className="font-bold tabular-nums text-white">{formatCurrency(corte.efectivo_contado)}</span>
        </p>
      </div>
    )
  }
  return <p className="text-sm text-slate-400" data-testid="corte">Nadie ha abierto turno.</p>
}

function SeAcaba({ datos, esTelefono, basico }: { datos: DatosInicio; esTelefono: boolean; basico: boolean }) {
  const navigate = useNavigate()
  const acabando = datos.poca_existencia.productos
  const enlaces = basico ? ENLACES.basico : ENLACES.completo
  return (
    <DaxCard>
      <Titulo enlace={{ a: enlaces.existencias, texto: basico ? 'Ver productos →' : 'Ver existencias →' }}>
        Se está acabando (quedan {datos.poca_existencia.umbral} o menos)
      </Titulo>
      {esTelefono ? (
        <ListaTarjetas vacio={acabando.length === 0} textoVacio="Nada se está acabando.">
          {acabando.map((p) => (
            <TarjetaFila key={p.variant_id} titulo={p.nombre} subtitulo={p.sku} importe={piezas(p.existencia)}
              onClick={() => navigate(urlExistencias(basico, p.sku, p.variant_id))} />
          ))}
        </ListaTarjetas>
      ) : acabando.length === 0 ? (
        <Vacio>Nada se está acabando.</Vacio>
      ) : (
        <table className="w-full text-sm">
          <thead><tr className={cabecera}><Th>Producto</Th><Th>Código</Th><Th der>Quedan</Th></tr></thead>
          <tbody>
            {acabando.map((p) => (
              <tr key={p.variant_id} className={fila}>
                <td className="py-1.5 text-slate-200"><Link to={urlExistencias(basico, p.sku, p.variant_id)} className="hover:underline">{p.nombre}</Link></td>
                <td className="py-1.5 font-mono text-xs text-slate-400">{p.sku}</td>
                <td className="py-1.5 text-right tabular-nums font-bold text-amber-400">{piezas(p.existencia)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </DaxCard>
  )
}

function MasVendido({ datos, esTelefono }: { datos: DatosInicio; esTelefono: boolean }) {
  const top = datos.top_semana
  return (
    <DaxCard>
      <Titulo enlace={{ a: '/hq/reports-hub', texto: 'Ver reportes →' }}>Lo que más se vendió (7 días)</Titulo>
      {esTelefono ? (
        <ListaTarjetas vacio={top.length === 0} textoVacio="Sin ventas esta semana.">
          {top.map((t) => (
            <TarjetaFila key={t.nombre} titulo={t.nombre} subtitulo={piezas(t.cantidad)} importe={formatCurrency(t.total)} />
          ))}
        </ListaTarjetas>
      ) : top.length === 0 ? (
        <Vacio>Sin ventas esta semana.</Vacio>
      ) : (
        <table className="w-full text-sm">
          <thead><tr className={cabecera}><Th>Producto</Th><Th der>Piezas</Th><Th der>Importe</Th></tr></thead>
          <tbody>
            {top.map((t) => (
              <tr key={t.nombre} className={fila}>
                <td className="py-1.5 text-slate-200">{t.nombre}</td>
                <td className="py-1.5 text-right tabular-nums text-slate-300">{piezas(t.cantidad)}</td>
                <td className="py-1.5 text-right tabular-nums font-bold text-white">{formatCurrency(t.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </DaxCard>
  )
}

function NoSeMueve({ datos, esTelefono }: { datos: NonNullable<DatosInicio['sin_movimiento']>; esTelefono: boolean }) {
  const navigate = useNavigate()
  const lista = datos.productos
  return (
    <DaxCard>
      <Titulo enlace={{ a: '/hq/inventory', texto: 'Ver existencias →' }}>
        No se mueve (sin venta en {datos.dias} días)
      </Titulo>
      {esTelefono ? (
        <ListaTarjetas vacio={lista.length === 0} textoVacio="Todo se ha vendido en ese plazo.">
          {lista.map((p) => (
            <TarjetaFila key={p.variant_id} titulo={p.nombre} subtitulo={p.sku}
              importe={formatCurrency(p.importe_venta)} estado={piezas(p.existencia)}
              onClick={() => navigate(urlExistencias(false, p.sku, p.variant_id))} />
          ))}
        </ListaTarjetas>
      ) : lista.length === 0 ? (
        <Vacio>Todo se ha vendido en ese plazo.</Vacio>
      ) : (
        <table className="w-full text-sm">
          <thead><tr className={cabecera}><Th>Producto</Th><Th>Código</Th><Th der>Existencia</Th><Th der>Parado</Th></tr></thead>
          <tbody>
            {lista.map((p) => (
              <tr key={p.variant_id} className={fila}>
                <td className="py-1.5 text-slate-200"><Link to={urlExistencias(false, p.sku, p.variant_id)} className="hover:underline">{p.nombre}</Link></td>
                <td className="py-1.5 font-mono text-xs text-slate-400">{p.sku}</td>
                <td className="py-1.5 text-right tabular-nums text-slate-300">{piezas(p.existencia)}</td>
                <td className="py-1.5 text-right tabular-nums font-bold text-white">{formatCurrency(p.importe_venta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </DaxCard>
  )
}

function Pendientes({ datos, esTelefono }: { datos: NonNullable<DatosInicio['pendientes']>; esTelefono: boolean }) {
  const nada = datos.devoluciones === 0 && datos.turnos_abiertos === 0 && datos.diferencias_caja.length === 0
  const enlace = 'max-md:inline-flex max-md:items-center max-md:min-h-[44px] hover:underline'
  return (
    <DaxCard>
      <Titulo>Pendientes</Titulo>
      {nada ? (
        <Vacio>Nada pendiente.</Vacio>
      ) : (
        <div className="space-y-3" data-testid="pendientes">
          {datos.devoluciones > 0 && (
            <Link to="/hq/returns" className={`block text-sm text-amber-300 ${enlace}`}>
              {datos.devoluciones === 1 ? '1 devolución por aprobar' : `${datos.devoluciones} devoluciones por aprobar`} →
            </Link>
          )}
          {datos.turnos_abiertos > 0 && (
            <Link to="/cash-history" className={`block text-sm text-amber-300 ${enlace}`}>
              {datos.turnos_abiertos === 1 ? '1 turno abierto desde hace más de un día' : `${datos.turnos_abiertos} turnos abiertos desde hace más de un día`} →
            </Link>
          )}
          {datos.diferencias_caja.length > 0 && (
            <div>
              <p className="text-xs font-bold text-slate-400 mb-1">Cortes que no cuadraron (7 días)</p>
              {esTelefono ? (
                <ListaTarjetas>
                  {datos.diferencias_caja.map((d) => (
                    <TarjetaFila key={d.session_id} titulo={`${d.sucursal} · ${d.cajera ?? 'Sin nombre'}`}
                      subtitulo={fecha(d.cerrado_en)}
                      importe={<span className={d.diferencia < 0 ? 'text-rose-400' : 'text-emerald-400'}>{formatCurrency(d.diferencia)}</span>}
                      datos={[{ etiqueta: 'Esperado', valor: formatCurrency(d.esperado) }, { etiqueta: 'Contado', valor: formatCurrency(d.contado) }]} />
                  ))}
                </ListaTarjetas>
              ) : (
                <table className="w-full text-sm">
                  <thead><tr className={cabecera}><Th>Fecha</Th><Th>Sucursal</Th><Th>Cajera</Th><Th der>Esperado</Th><Th der>Contado</Th><Th der>Diferencia</Th></tr></thead>
                  <tbody>
                    {datos.diferencias_caja.map((d) => (
                      <tr key={d.session_id} className={fila}>
                        <td className="py-1.5 text-slate-400">{fecha(d.cerrado_en)}</td>
                        <td className="py-1.5 text-slate-200">{d.sucursal}</td>
                        <td className="py-1.5 text-slate-300">{d.cajera ?? 'Sin nombre'}</td>
                        <td className="py-1.5 text-right tabular-nums text-slate-300">{formatCurrency(d.esperado)}</td>
                        <td className="py-1.5 text-right tabular-nums text-slate-300">{formatCurrency(d.contado)}</td>
                        <td className={`py-1.5 text-right tabular-nums font-bold ${d.diferencia < 0 ? 'text-rose-400' : 'text-emerald-400'}`}>{formatCurrency(d.diferencia)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}
    </DaxCard>
  )
}

function Sucursales({ lista }: { lista: NonNullable<DatosInicio['sucursales']> }) {
  const estadoCorte = (c: DatosInicio['corte']) =>
    c.estado === 'abierto' ? <span className="text-emerald-400">Turno abierto</span>
      : c.estado === 'cerrado' ? <span className="text-slate-400">Turno cerrado</span>
        : <span className="text-slate-500">Sin turno</span>
  return (
    <DaxCard>
      <Titulo enlace={{ a: '/hq/branches', texto: 'Ver sucursales →' }}>Cómo va cada sucursal (hoy)</Titulo>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="sucursales">
        {lista.map((s) => (
          <Link key={s.branch_id} to={`/hq/branches/${s.branch_id}`} className="block rounded-lg border border-slate-800/60 p-3 hover:border-indigo-500/40 max-md:min-h-[44px]">
            <p className="font-bold text-white text-sm">{s.nombre}</p>
            <p className="text-xl font-bold text-white tabular-nums">{formatCurrency(s.ventas_hoy)}</p>
            <p className="text-xs text-slate-400">{ventas(s.tickets_hoy)} · {estadoCorte(s.corte)}</p>
            {s.poca_existencia > 0 && (
              <p className="text-xs text-amber-400 mt-1">{s.poca_existencia === 1 ? '1 producto se está acabando' : `${s.poca_existencia} productos se están acabando`}</p>
            )}
          </Link>
        ))}
      </div>
    </DaxCard>
  )
}

export function Inicio() {
  const esTelefono = useEsTelefono()
  const loaded = useEnabledModulesStore((s) => s.loaded)
  const load = useEnabledModulesStore((s) => s.load)
  const perfilUi = useEnabledModulesStore((s) => s.perfilUi)
  const [datos, setDatos] = useState<DatosInicio | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [valuacion, setValuacion] = useState<ValuacionInventario | null>(null)
  const [valuacionError, setValuacionError] = useState<string | null>(null)

  // Espera al contexto: con el default 'completo' del store una FREE pediría
  // las secciones de paga para cambiarlas un segundo después.
  useEffect(() => {
    if (!loaded) void load()
  }, [loaded, load])

  useEffect(() => {
    if (!loaded) return
    let vivo = true
    reportsApi.inicio({ completo: perfilUi !== 'basico' })
      .then((d) => { if (vivo) setDatos(d) })
      .catch((e: any) => {
        if (vivo) setError(errorDetailText(e?.response?.data?.detail, 'No se pudo cargar el resumen. Vuelve a intentar en unos segundos.'))
      })
    reportsApi.valorInventario({ agrupar: 'sucursal' })
      .then((v) => { if (vivo) setValuacion(v) })
      .catch((e: any) => {
        if (vivo) setValuacionError(errorDetailText(e?.response?.data?.detail, 'No se pudo calcular el valor de la tienda.'))
      })
    return () => { vivo = false }
  }, [loaded, perfilUi])

  const metodos = datos
    ? [
        ...ORDEN_METODOS.filter((m) => m in datos.por_metodo_hoy),
        ...Object.keys(datos.por_metodo_hoy).filter((m) => !ORDEN_METODOS.includes(m)),
      ]
    : []
  const basico = perfilUi === 'basico'
  const conUtilidad = datos?.utilidad_bruta_hoy != null
  const sinCosto = datos?.venta_sin_costo_hoy ?? 0
  const conCosto = Math.max(0, (datos?.hoy.total ?? 0) - sinCosto)

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-white">¿Cómo voy?</h1>}
        descripcion="Lo vendido, la caja, lo que se acaba y lo que hay que atender."
      />

      {error ? (
        <DaxCard><p className="text-sm text-rose-300">{error}</p></DaxCard>
      ) : !datos ? (
        <Spinner size="lg" text="Cargando…" />
      ) : (
        <>
          <div className={`grid grid-cols-1 sm:grid-cols-3 ${conUtilidad ? 'lg:grid-cols-4' : ''} gap-3`}>
            <Cifra etiqueta="Hoy" total={datos.hoy.total} detalle={ventas(datos.hoy.tickets)} testId="cifra-hoy" />
            <Cifra etiqueta="Ayer" total={datos.ayer.total} detalle={ventas(datos.ayer.tickets)} testId="cifra-ayer" />
            <Cifra etiqueta="Últimos 7 días" total={datos.semana.total} detalle={ventas(datos.semana.tickets)} testId="cifra-semana" />
            {conUtilidad && (
              <Cifra etiqueta="Utilidad bruta de hoy" total={datos.utilidad_bruta_hoy as number}
                detalle={sinCosto > 0 ? `sobre ${formatCurrency(conCosto)} con costo · ${formatCurrency(sinCosto)} vendidos sin costo` : 'sobre lo que tiene costo'}
                testId="cifra-utilidad" />
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <DaxCard>
              <Titulo enlace={{ a: basico ? ENLACES.basico.ventas : ENLACES.completo.ventas, texto: 'Ver ventas →' }}>Cómo te pagaron hoy</Titulo>
              {metodos.length === 0 ? (
                <Vacio>Sin cobros hoy.</Vacio>
              ) : (
                <ul className="space-y-1">
                  {metodos.map((m) => (
                    <li key={m} data-testid="metodo" className="flex justify-between text-sm">
                      <span className="text-slate-300">{METODOS[m] ?? m}</span>
                      <span className="font-bold tabular-nums text-white">{formatCurrency(datos.por_metodo_hoy[m])}</span>
                    </li>
                  ))}
                </ul>
              )}
            </DaxCard>
            <DaxCard>
              <Titulo enlace={{ a: '/cash-history', texto: 'Ver corte →' }}>Caja</Titulo>
              <Corte corte={datos.corte} />
            </DaxCard>
          </div>

          {datos.pendientes && <Pendientes datos={datos.pendientes} esTelefono={esTelefono} />}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <SeAcaba datos={datos} esTelefono={esTelefono} basico={basico} />
            <MasVendido datos={datos} esTelefono={esTelefono} />
          </div>

          {datos.sin_movimiento && <NoSeMueve datos={datos.sin_movimiento} esTelefono={esTelefono} />}
          {datos.sucursales && <Sucursales lista={datos.sucursales} />}
        </>
      )}

      <ValorTiendaCard
        valorVenta={valuacion?.totales.valor_venta ?? 0}
        valorCosto={valuacion ? valuacion.totales.valor_costo : null}
        piezas={valuacion?.totales.piezas ?? 0}
        piezasSinCosto={valuacion?.totales.piezas_sin_costo ?? 0}
        skusSinCosto={valuacion?.totales.skus_sin_costo ?? 0}
        cargando={!valuacion && !valuacionError}
        error={valuacionError}
      />
    </div>
  )
}
