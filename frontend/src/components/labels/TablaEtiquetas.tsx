import type { LabelCandidate } from '../../api/labels'
import { TablaDesplazable } from '../ui/TablaDesplazable'
import { formatCurrency } from '../../utils/currency'
import { MAX_COPIAS } from '../../pages/labels/lote'

/**
 * Los candidatos a etiquetar, con su casilla y sus copias.
 *
 * Las filas que NO se pueden imprimir se muestran apagadas con su motivo a la
 * vista, nunca escondidas: esconderlas deja a la tienda buscando una prenda que
 * no aparece nunca y sin saber por qué.
 *
 * En teléfono la tabla se vuelve tarjetas (la misma información, apilada): una
 * rejilla de diez columnas a 390 px no se lee ni con scroll horizontal.
 */

interface Props {
  items: LabelCandidate[]
  copias: Record<string, number>
  seleccion: ReadonlySet<string>
  /** Fila cuya etiqueta se está viendo. */
  activa: string | null
  onAlternar: (variantId: string) => void
  onAlternarTodo: () => void
  onCopias: (variantId: string, valor: string) => void
  onVerPrevia: (item: LabelCandidate) => void
  esTelefono: boolean
}

function CeldaCopias({
  item, valor, onCopias,
}: { item: LabelCandidate; valor: number; onCopias: (id: string, v: string) => void }) {
  return (
    <input
      type="number"
      min={0}
      max={MAX_COPIAS}
      step={1}
      inputMode="numeric"
      className="dax-input w-16 text-sm text-center"
      value={valor}
      disabled={!item.printable}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onCopias(item.variant_id, e.target.value)}
      aria-label={`Copias de ${item.sku}`}
      title={`0 a ${MAX_COPIAS}. Cero = no imprimir este renglón.`}
    />
  )
}

export function TablaEtiquetas({
  items, copias, seleccion, activa, onAlternar, onAlternarTodo, onCopias, onVerPrevia, esTelefono,
}: Props) {
  const imprimibles = items.filter((i) => i.printable)
  const todoMarcado = imprimibles.length > 0 && imprimibles.every((i) => seleccion.has(i.variant_id))

  if (items.length === 0) {
    return (
      <p className="text-sm text-slate-500 text-center py-10">
        Nada que etiquetar con estos filtros.
      </p>
    )
  }

  if (esTelefono) {
    return (
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-xs text-slate-300 px-1">
          <input type="checkbox" className="rounded" checked={todoMarcado} onChange={onAlternarTodo} />
          Marcar todo lo imprimible ({imprimibles.length})
        </label>
        {items.map((it) => (
          <div
            key={it.variant_id}
            onClick={() => it.printable && onVerPrevia(it)}
            className={`rounded-xl border p-3 space-y-2 ${
              activa === it.variant_id ? 'border-blue-500/60 bg-blue-500/5' : 'border-slate-700/50'
            } ${it.printable ? '' : 'opacity-50'}`}
          >
            <div className="flex items-start gap-2">
              <input
                type="checkbox"
                className="rounded mt-0.5"
                checked={seleccion.has(it.variant_id)}
                disabled={!it.printable}
                onClick={(e) => e.stopPropagation()}
                onChange={() => onAlternar(it.variant_id)}
                aria-label={`Seleccionar ${it.sku}`}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-white leading-snug">{it.sale_name || it.product_name}</p>
                <p className="text-[11px] text-slate-500 font-mono">{it.sku} · {it.barcode || 'sin código'}</p>
              </div>
              <CeldaCopias item={it} valor={copias[it.variant_id] ?? 0} onCopias={onCopias} />
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400">
              {it.brand && <span>{it.brand}</span>}
              {it.size && <span>Talla {it.size}</span>}
              {it.color && <span>{it.color}</span>}
              <span className="text-slate-300">{formatCurrency(it.price)}</span>
              <span>Exist. {it.stock}</span>
            </div>
            {!it.printable && (
              <p className="text-[11px] text-amber-300">
                <i className="fa-solid fa-triangle-exclamation mr-1" />{it.reason}
              </p>
            )}
          </div>
        ))}
      </div>
    )
  }

  return (
    <TablaDesplazable sangrado={false}>
      <table className="dax-table text-sm">
        <thead>
          <tr>
            <th className="w-8">
              <input
                type="checkbox"
                className="rounded"
                checked={todoMarcado}
                onChange={onAlternarTodo}
                aria-label="Marcar todo lo imprimible"
              />
            </th>
            <th>SKU</th>
            <th>Código</th>
            <th>Marca</th>
            <th>Nombre de venta</th>
            <th>Talla</th>
            <th>Color</th>
            <th className="text-right">Precio</th>
            <th className="text-right">Exist.</th>
            <th className="text-center">Etiquetas</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr
              key={it.variant_id}
              onClick={() => it.printable && onVerPrevia(it)}
              className={`${it.printable ? 'cursor-pointer' : 'opacity-50'} ${
                activa === it.variant_id ? 'bg-blue-500/10' : ''
              }`}
            >
              <td>
                <input
                  type="checkbox"
                  className="rounded"
                  checked={seleccion.has(it.variant_id)}
                  disabled={!it.printable}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => onAlternar(it.variant_id)}
                  aria-label={`Seleccionar ${it.sku}`}
                />
              </td>
              <td className="font-mono text-xs whitespace-nowrap">{it.sku}</td>
              <td className="font-mono text-xs whitespace-nowrap">
                {it.barcode || <span className="text-slate-600">—</span>}
              </td>
              <td className="text-xs whitespace-nowrap">{it.brand}</td>
              <td className="min-w-[16rem]">
                <span className="text-slate-200">{it.sale_name || it.product_name}</span>
                {!it.printable && (
                  <span className="block text-[11px] text-amber-300">
                    <i className="fa-solid fa-triangle-exclamation mr-1" />{it.reason}
                  </span>
                )}
              </td>
              <td className="text-xs whitespace-nowrap">{it.size}</td>
              <td className="text-xs whitespace-nowrap">{it.color}</td>
              <td className="text-right whitespace-nowrap">{formatCurrency(it.price)}</td>
              <td className="text-right whitespace-nowrap">{it.stock}</td>
              <td className="text-center">
                <CeldaCopias item={it} valor={copias[it.variant_id] ?? 0} onCopias={onCopias} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TablaDesplazable>
  )
}
