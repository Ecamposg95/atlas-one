import { Link } from 'react-router-dom'

import type { Etiqueta, ResumenAplicacion } from '../../../../api/cargas'
import { DaxCard } from '../../../../components/ui/DaxCard'
import { ListaTarjetas } from '../../../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../../hooks/useIsMobile'
import { formatCurrency } from '../../../../utils/currency'
import { cantidad } from '../formato'

/** Carga aplicada: qué entró y las etiquetas por imprimir. */
export function ResumenEtiquetas({ cargaId, folio, etiquetas, resumen }: {
  cargaId: string; folio: number; etiquetas: Etiqueta[]
  /** Solo llega justo después de autorizar; al reabrir una carga aplicada no hay. */
  resumen?: ResumenAplicacion | null
}) {
  const esTelefono = useEsTelefono()
  return (
    <div className="space-y-3">
      <DaxCard>
        <p className="text-sm text-dax-text font-semibold">
          {resumen
            ? `Carga aplicada: ${resumen.productos_nuevos} productos nuevos, ${resumen.variantes_nuevas} variantes nuevas, ${cantidad(resumen.piezas)} piezas, ${formatCurrency(resumen.valor_costo)} a costo.`
            : `Carga #${folio} aplicada.`}
        </p>
        <Link to={`/labels?carga=${cargaId}&folio=${folio}`}
          className="dax-btn-primary justify-center mt-3 w-full sm:w-auto max-md:min-h-[44px]">
          <i className="fa-solid fa-print" /> Imprimir etiquetas
        </Link>
      </DaxCard>
      {esTelefono ? (
        <ListaTarjetas vacio={etiquetas.length === 0} textoVacio="No hay etiquetas por imprimir.">
          {etiquetas.map((e, i) => (
            <TarjetaFila key={`${e.sku}-${e.talla}-${i}`}
              titulo={`${e.marca} · ${e.producto}`} subtitulo={e.sku}
              importe={formatCurrency(e.precio)}
              datos={[{ etiqueta: 'Talla', valor: e.talla ?? '—' }, { etiqueta: 'Código', valor: e.barcode ?? '—' },
                { etiqueta: 'Piezas', valor: cantidad(e.piezas) }]} />
          ))}
        </ListaTarjetas>
      ) : (
        <DaxCard padding={false}>
          <table className="w-full text-sm">
            <thead className="text-xs text-dax-muted uppercase">
              <tr>
                <th className="text-left p-3">Marca</th><th className="text-left p-3">Producto</th>
                <th className="text-left p-3">SKU</th><th className="text-left p-3">Talla</th>
                <th className="text-left p-3">Código</th><th className="text-right p-3">Piezas</th>
                <th className="text-right p-3">Precio</th>
              </tr>
            </thead>
            <tbody>
              {etiquetas.length === 0 && (
                <tr><td colSpan={7} className="p-6 text-center text-dax-muted">No hay etiquetas por imprimir.</td></tr>
              )}
              {etiquetas.map((e, i) => (
                <tr key={`${e.sku}-${e.talla}-${i}`} className="border-t border-dax-border-dim">
                  <td className="p-3 text-dax-text">{e.marca}</td><td className="p-3 text-dax-text">{e.producto}</td>
                  <td className="p-3 text-dax-muted">{e.sku}</td><td className="p-3 text-dax-text">{e.talla ?? '—'}</td>
                  <td className="p-3 text-dax-muted">{e.barcode ?? '—'}</td>
                  <td className="p-3 text-right tabular-nums text-dax-text">{cantidad(e.piezas)}</td>
                  <td className="p-3 text-right tabular-nums text-dax-text">{formatCurrency(e.precio)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DaxCard>
      )}
    </div>
  )
}
