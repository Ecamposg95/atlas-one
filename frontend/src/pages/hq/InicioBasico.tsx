// frontend/src/pages/hq/InicioBasico.tsx
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { reportsApi, type InicioBasico as DatosInicio, type ValuacionInventario } from '../../api/reports'
import { ValorTiendaCard } from '../../components/reports/ValorTiendaCard'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'

/**
 * Inicio básico (modo básico, spec 2026-10-18 §4.2): una sola pantalla que
 * responde "¿cómo voy?" para la dueña de una tienda FREE. Una llamada
 * (`/reports/inicio-basico`) + la tarjeta de valor de la tienda de SP3. Sin
 * gráficas: ninguna librería de gráficas viaja en este chunk.
 */

const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']

const hora = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) : ''
const piezas = (n: number) => {
  const r = Math.round(n * 100) / 100
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}
const ventas = (n: number) => `${n} ${n === 1 ? 'venta' : 'ventas'}`

function Cifra({ etiqueta, total, tickets, testId }: { etiqueta: string; total: number; tickets: number; testId: string }) {
  return (
    <div className="dax-card p-4" data-testid={testId}>
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">{etiqueta}</p>
      <p className="text-2xl font-bold text-white tabular-nums">{formatCurrency(total)}</p>
      <p className="text-xs text-slate-400">{ventas(tickets)}</p>
    </div>
  )
}

function Titulo({ children, enlace }: { children: ReactNode; enlace?: { a: string; texto: string } }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">{children}</p>
      {enlace && (
        <Link to={enlace.a} className="text-[10px] font-bold text-indigo-400 hover:underline whitespace-nowrap">
          {enlace.texto}
        </Link>
      )}
    </div>
  )
}

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

export function InicioBasico() {
  const esTelefono = useEsTelefono()
  const [datos, setDatos] = useState<DatosInicio | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [valuacion, setValuacion] = useState<ValuacionInventario | null>(null)
  const [valuacionError, setValuacionError] = useState<string | null>(null)

  useEffect(() => {
    let vivo = true
    reportsApi.inicioBasico()
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
  }, [])

  const metodos = datos
    ? [
        ...ORDEN_METODOS.filter((m) => m in datos.por_metodo_hoy),
        ...Object.keys(datos.por_metodo_hoy).filter((m) => !ORDEN_METODOS.includes(m)),
      ]
    : []
  const acabando = datos?.poca_existencia.productos ?? []
  const top = datos?.top_semana ?? []

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-white">¿Cómo voy?</h1>}
        descripcion="Lo vendido, la caja y lo que se está acabando."
      />

      {error ? (
        <DaxCard><p className="text-sm text-rose-300">{error}</p></DaxCard>
      ) : !datos ? (
        <Spinner size="lg" text="Cargando…" />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Cifra etiqueta="Hoy" total={datos.hoy.total} tickets={datos.hoy.tickets} testId="cifra-hoy" />
            <Cifra etiqueta="Ayer" total={datos.ayer.total} tickets={datos.ayer.tickets} testId="cifra-ayer" />
            <Cifra etiqueta="Últimos 7 días" total={datos.semana.total} tickets={datos.semana.tickets} testId="cifra-semana" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <DaxCard>
              <Titulo>Cómo te pagaron hoy</Titulo>
              {metodos.length === 0 ? (
                <p className="text-sm text-slate-400">Sin cobros hoy.</p>
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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <DaxCard>
              <Titulo enlace={{ a: '/products', texto: 'Ver productos →' }}>
                Se está acabando (quedan {datos.poca_existencia.umbral} o menos)
              </Titulo>
              {esTelefono ? (
                <ListaTarjetas vacio={acabando.length === 0} textoVacio="Nada se está acabando.">
                  {acabando.map((p) => (
                    <TarjetaFila key={p.variant_id} titulo={p.nombre} subtitulo={p.sku} importe={piezas(p.existencia)} />
                  ))}
                </ListaTarjetas>
              ) : acabando.length === 0 ? (
                <p className="text-sm text-slate-400">Nada se está acabando.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-widest text-slate-500">
                      <th className="py-1">Producto</th><th className="py-1">Código</th><th className="py-1 text-right">Quedan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {acabando.map((p) => (
                      <tr key={p.variant_id} className="border-t border-slate-800/60">
                        <td className="py-1.5 text-slate-200">{p.nombre}</td>
                        <td className="py-1.5 font-mono text-xs text-slate-400">{p.sku}</td>
                        <td className="py-1.5 text-right tabular-nums font-bold text-amber-400">{piezas(p.existencia)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </DaxCard>
            <DaxCard>
              <Titulo>Lo que más se vendió (7 días)</Titulo>
              {esTelefono ? (
                <ListaTarjetas vacio={top.length === 0} textoVacio="Sin ventas esta semana.">
                  {top.map((t) => (
                    <TarjetaFila key={t.nombre} titulo={t.nombre} subtitulo={piezas(t.cantidad)} importe={formatCurrency(t.total)} />
                  ))}
                </ListaTarjetas>
              ) : top.length === 0 ? (
                <p className="text-sm text-slate-400">Sin ventas esta semana.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-widest text-slate-500">
                      <th className="py-1">Producto</th><th className="py-1 text-right">Piezas</th><th className="py-1 text-right">Importe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top.map((t) => (
                      <tr key={t.nombre} className="border-t border-slate-800/60">
                        <td className="py-1.5 text-slate-200">{t.nombre}</td>
                        <td className="py-1.5 text-right tabular-nums text-slate-300">{piezas(t.cantidad)}</td>
                        <td className="py-1.5 text-right tabular-nums font-bold text-white">{formatCurrency(t.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </DaxCard>
          </div>
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
