import type { GrupoPlan, RenglonPlan } from '../../../../api/cargas'
import { DaxCard } from '../../../../components/ui/DaxCard'
import { ListaTarjetas } from '../../../../components/ui/ListaTarjetas'
import { StatusChip, type Tone } from '../../../../components/ui/StatusChip'
import { TarjetaFila } from '../../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../../hooks/useIsMobile'
import { formatCurrency } from '../../../../utils/currency'
import { CLASES, cantidad } from '../formato'

const TONO: Record<RenglonPlan['clase'], Tone> = {
  EXISTE: 'sky', SUMA: 'amber', NUEVO: 'green', YA_CARGADO: 'slate', IGNORADO: 'slate',
}
const apagado = (r: RenglonPlan) => r.clase === 'YA_CARGADO' || r.clase === 'IGNORADO'
const dinero = (v: string | null) => (v == null ? '—' : formatCurrency(v))

/** El plan agrupado por producto: tallas × piezas, precio, costo y clase. Tabla en PC, tarjetas en teléfono. */
export function TablaPlan({ grupos }: { grupos: GrupoPlan[] }) {
  const esTelefono = useEsTelefono()
  if (esTelefono) {
    return (
      <ListaTarjetas vacio={grupos.length === 0} textoVacio="El plan no tiene renglones.">
        {grupos.map((g) => (
          <div key={g.grupo} className="space-y-2">
            <h3 className="text-sm font-black text-dax-text px-1">{g.titulo}</h3>
            {g.renglones.map((r) => (
              <div key={r.orden} className={apagado(r) ? 'opacity-60' : ''}>
                <TarjetaFila
                  titulo={`${r.talla ?? 'Única'}${r.color ? ` · ${r.color}` : ''} × ${cantidad(r.cantidad)}`}
                  subtitulo={r.sku ?? undefined}
                  estado={<StatusChip tone={TONO[r.clase]} label={CLASES[r.clase]} />}
                  datos={[{ etiqueta: 'Precio', valor: dinero(r.precio) }, { etiqueta: 'Costo', valor: dinero(r.costo) }]}
                />
              </div>
            ))}
          </div>
        ))}
      </ListaTarjetas>
    )
  }
  return (
    <DaxCard padding={false}>
      <table className="w-full text-sm">
        <thead className="text-xs text-dax-muted uppercase">
          <tr>
            <th className="text-left p-3">Producto</th><th className="text-left p-3">SKU</th>
            <th className="text-left p-3">Talla</th><th className="text-right p-3">Piezas</th>
            <th className="text-right p-3">Precio</th><th className="text-right p-3">Costo</th>
            <th className="text-left p-3">Clase</th>
          </tr>
        </thead>
        <tbody>
          {grupos.length === 0 && (
            <tr><td colSpan={7} className="p-6 text-center text-dax-muted">El plan no tiene renglones.</td></tr>
          )}
          {grupos.map((g) => g.renglones.map((r, i) => (
            <tr key={`${g.grupo}-${r.orden}`} className={`border-t border-dax-border-dim ${apagado(r) ? 'opacity-60' : ''}`}>
              <td className="p-3 text-dax-text font-semibold">{i === 0 ? g.titulo : ''}</td>
              <td className="p-3 text-dax-muted">{r.sku ?? '—'}</td>
              <td className="p-3 text-dax-text">{r.talla ?? '—'}{r.color ? ` · ${r.color}` : ''}</td>
              <td className="p-3 text-right tabular-nums text-dax-text">{cantidad(r.cantidad)}</td>
              <td className="p-3 text-right tabular-nums text-dax-text">{dinero(r.precio)}</td>
              <td className="p-3 text-right tabular-nums text-dax-text">{dinero(r.costo)}</td>
              <td className="p-3"><StatusChip tone={TONO[r.clase]} label={CLASES[r.clase]} /></td>
            </tr>
          )))}
        </tbody>
      </table>
    </DaxCard>
  )
}
