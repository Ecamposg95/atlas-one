import type { ReactNode } from 'react'
import type { ValuacionGrupo, ValuacionInventario } from '../../api/reports'
import { ListaTarjetas } from '../ui/ListaTarjetas'
import { TarjetaFila } from '../ui/TarjetaFila'
import { Spinner } from '../ui/Spinner'
import { formatCurrency } from '../../utils/currency'
import { porcentaje } from '../../utils/porcentaje'

/**
 * DistribucionValor — un panel de "¿cómo se reparte el valor de la tienda?".
 *
 * Pinta los grupos de una respuesta de `/reports/valor-inventario` (por
 * departamento, marca o sucursal) con su parte del valor a venta en
 * porcentaje y una barra. En escritorio es una tabla; en teléfono,
 * `TarjetaFila`. Con `onSeleccionar`, cada grupo con clave es un botón:
 * la pantalla lo usa para acotar otro panel (departamento → marcas). Los
 * grupos sin clave ("Sin departamento") no se pueden elegir: no hay id que
 * filtrar.
 *
 * Sin colores nuevos: la barra usa `bg-dax-accent` sobre `bg-dax-border-dim`.
 */
const piezasTxt = (n: number) => Math.round(n).toLocaleString('es-MX')
const pctTxt = (n: number) => `${n.toFixed(1)}%`

export interface DistribucionValorProps {
  titulo: string
  /** Cabecera de la primera columna: "Departamento", "Marca", "Sucursal". */
  etiqueta: string
  data: ValuacionInventario | null
  cargando: boolean
  telefono: boolean
  /** Clave del grupo elegido (se resalta); solo tiene sentido con `onSeleccionar`. */
  seleccionada?: string | null
  /** Si viene, cada grupo con clave es un botón. */
  onSeleccionar?: (g: ValuacionGrupo) => void
  onExportar: () => void
  /** Texto o chip bajo el título ("Marcas en Bolsas · Quitar"). */
  aviso?: ReactNode
  'data-testid'?: string
}

function Barra({ pct }: { pct: number }) {
  return (
    <span className="block h-1.5 w-full rounded-full bg-dax-border-dim" aria-hidden="true">
      <span className="block h-1.5 rounded-full bg-dax-accent" style={{ width: `${Math.min(100, pct)}%` }} />
    </span>
  )
}

export function DistribucionValor({
  titulo, etiqueta, data, cargando, telefono, seleccionada, onSeleccionar, onExportar, aviso,
  'data-testid': testId,
}: DistribucionValorProps) {
  const veCosto = data?.ve_costo ?? false
  const total = data?.totales.valor_venta ?? 0
  const grupos = data?.grupos ?? []
  const elegible = (g: ValuacionGrupo) => !!onSeleccionar && g.clave !== ''

  const nombre = (g: ValuacionGrupo) =>
    elegible(g) ? (
      <button
        type="button"
        className="dax-btn-ghost px-0 text-left font-medium"
        aria-pressed={seleccionada === g.clave}
        onClick={() => onSeleccionar!(g)}
      >
        {g.nombre}
      </button>
    ) : (
      <span className="font-medium">{g.nombre}</span>
    )

  return (
    <section className="dax-card" aria-label={titulo} data-testid={testId}>
      <header className="flex items-start justify-between gap-2 border-b border-dax-border-dim p-3">
        <div>
          <h2 className="text-sm font-bold">{titulo}</h2>
          {aviso}
        </div>
        <button type="button" onClick={onExportar} disabled={!data || cargando} className="dax-btn-secondary text-xs">
          <i className="fa-solid fa-file-csv mr-1" aria-hidden="true" /> CSV
        </button>
      </header>

      {telefono ? (
        <ListaTarjetas className="p-2" cargando={cargando && !data} vacio={grupos.length === 0} textoVacio="Sin existencias que valuar">
          {grupos.map((g) => {
            const pct = porcentaje(g.valor_venta, total)
            return (
              <TarjetaFila
                key={g.clave || 'sin'}
                titulo={g.nombre}
                subtitulo={`${piezasTxt(g.piezas)} piezas · ${g.skus} SKUs`}
                importe={formatCurrency(g.valor_venta)}
                estado={<span className="text-xs font-bold tabular-nums">{pctTxt(pct)}</span>}
                datos={[
                  { etiqueta: '% del valor', valor: <Barra pct={pct} /> },
                  ...(veCosto ? [{ etiqueta: 'A costo', valor: formatCurrency(g.valor_costo ?? 0) }] : []),
                  { etiqueta: 'Sin costo', valor: `${piezasTxt(g.piezas_sin_costo)} pz` },
                ]}
                onClick={elegible(g) ? () => onSeleccionar!(g) : undefined}
              />
            )
          })}
        </ListaTarjetas>
      ) : cargando && !data ? (
        <Spinner text="Calculando…" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-dax-muted">
                <th className="p-3">{etiqueta}</th>
                <th className="p-3 text-right">Piezas</th>
                <th className="p-3 text-right">Valor a venta</th>
                <th className="p-3 w-40">% del valor</th>
                {veCosto && <th className="p-3 text-right">Valor a costo</th>}
                <th className="p-3 text-right">Sin costo</th>
              </tr>
            </thead>
            <tbody>
              {grupos.length === 0 && (
                <tr><td colSpan={veCosto ? 6 : 5} className="p-8 text-center text-dax-muted">Sin existencias que valuar</td></tr>
              )}
              {grupos.map((g) => {
                const pct = porcentaje(g.valor_venta, total)
                const elegido = seleccionada != null && seleccionada === g.clave
                return (
                  <tr key={g.clave || 'sin'} className={`border-t border-dax-border-dim ${elegido ? 'bg-dax-accent-soft' : ''}`}>
                    <td className="p-3">{nombre(g)}</td>
                    <td className="p-3 text-right tabular-nums">{piezasTxt(g.piezas)}</td>
                    <td className="p-3 text-right tabular-nums">{formatCurrency(g.valor_venta)}</td>
                    <td className="p-3">
                      <span className="flex items-center gap-2">
                        <Barra pct={pct} />
                        <span className="w-14 text-right text-xs font-bold tabular-nums">{pctTxt(pct)}</span>
                      </span>
                    </td>
                    {veCosto && <td className="p-3 text-right tabular-nums">{formatCurrency(g.valor_costo ?? 0)}</td>}
                    <td className={`p-3 text-right tabular-nums ${g.piezas_sin_costo > 0 ? 'text-dax-warning' : ''}`}>{piezasTxt(g.piezas_sin_costo)}</td>
                  </tr>
                )
              })}
            </tbody>
            {data && grupos.length > 0 && (
              <tfoot>
                <tr className="border-t-2 border-dax-border-dim font-bold">
                  <td className="p-3">Total</td>
                  <td className="p-3 text-right tabular-nums">{piezasTxt(data.totales.piezas)}</td>
                  <td className="p-3 text-right tabular-nums">{formatCurrency(data.totales.valor_venta)}</td>
                  <td className="p-3 text-right text-xs tabular-nums">{total > 0 ? '100.0%' : '0.0%'}</td>
                  {veCosto && <td className="p-3 text-right tabular-nums">{formatCurrency(data.totales.valor_costo ?? 0)}</td>}
                  <td className="p-3 text-right tabular-nums">{piezasTxt(data.totales.piezas_sin_costo)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </section>
  )
}
