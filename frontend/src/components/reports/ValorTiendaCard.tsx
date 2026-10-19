import { Link } from 'react-router-dom'
import { formatCurrency } from '../../utils/currency'

/**
 * ValorTiendaCard — "¿cuánto vale mi tienda hoy?" en el inicio del dueño.
 *
 * Dos cifras que SIEMPRE van juntas: valor a precio de venta (completo) y
 * valor a costo (solo SKUs con costo > 0). Si hay piezas sin costo, el costo
 * está incompleto: la cifra grande es la de venta y el costo baja a
 * secundaria con el aviso "N piezas sin costo", para que un catálogo
 * importado sin costos nunca se lea como "mi tienda vale $0". Con el costo
 * completo, la cifra grande es el costo (lo invertido) y la venta queda al
 * lado. `valorCosto === null` = el rol no ve costos (gerente): venta y piezas.
 */
export interface ValorTiendaCardProps {
  valorVenta: number
  valorCosto: number | null
  piezas: number
  piezasSinCosto: number
  skusSinCosto: number
  cargando?: boolean
  error?: string | null
}

const piezasTxt = (n: number) => {
  const r = Math.round(n)
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}

export function ValorTiendaCard({
  valorVenta, valorCosto, piezas, piezasSinCosto, skusSinCosto, cargando = false, error = null,
}: ValorTiendaCardProps) {
  const costoIncompleto = piezasSinCosto > 0
  const costoPrincipal = valorCosto !== null && !costoIncompleto
  const principal = costoPrincipal ? (valorCosto as number) : valorVenta
  const etiquetaPrincipal = costoPrincipal ? 'Valor a costo' : 'Valor a precio de venta'

  return (
    <section
      className="dax-card p-5 rounded-2xl border-t-2 border-t-amber-500/50 relative overflow-hidden"
      aria-label="Valor de la tienda"
      data-testid="valor-tienda"
    >
      <div className="flex justify-between items-start gap-2 mb-1">
        <p className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Valor de la tienda</p>
        <Link to="/hq/valor-inventario" className="text-[10px] font-bold text-amber-400 hover:underline whitespace-nowrap max-md:inline-flex max-md:items-center max-md:min-h-[44px]">
          Ver desglose →
        </Link>
      </div>
      {error ? (
        <p className="text-sm text-rose-300">{error}</p>
      ) : cargando ? (
        <p className="text-sm text-slate-500">Calculando…</p>
      ) : (
        <>
          <p className="text-[9px] uppercase tracking-wider text-slate-500">{etiquetaPrincipal}</p>
          <h2 className="text-2xl md:text-3xl font-bold text-white tabular-nums" data-testid="valor-principal">
            {formatCurrency(principal)}
          </h2>
          <div className="mt-1 flex flex-wrap justify-between gap-x-3 gap-y-1 text-xs font-mono">
            <span className="text-slate-400">{piezasTxt(piezas)}</span>
            {valorCosto !== null && !costoPrincipal && (
              <span className="text-slate-400">
                A costo: <span className="text-white font-bold tabular-nums" data-testid="valor-costo">{formatCurrency(valorCosto)}</span>
              </span>
            )}
            {costoPrincipal && (
              <span className="text-slate-400">
                A venta: <span className="text-white font-bold tabular-nums" data-testid="valor-venta">{formatCurrency(valorVenta)}</span>
              </span>
            )}
          </div>
          {costoIncompleto && valorCosto !== null && (
            <p className="mt-1 text-[10px] font-bold text-amber-400" role="status">
              {piezasTxt(piezasSinCosto)} sin costo ({skusSinCosto} {skusSinCosto === 1 ? 'SKU' : 'SKUs'}): el valor a costo está incompleto.
            </p>
          )}
        </>
      )}
    </section>
  )
}

export default ValorTiendaCard
