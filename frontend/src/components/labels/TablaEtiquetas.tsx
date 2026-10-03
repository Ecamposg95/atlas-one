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
 * Tocar el renglón entero lo marca (la casilla es chica y en mostrador se
 * falla); la vista previa vive en el botón del ojo. Cinco columnas, con el
 * nombre partido en dos líneas si hace falta, para que la tabla quepa en una
 * laptop sin scroll horizontal.
 *
 * En teléfono la tabla se vuelve tarjetas (la misma información, apilada).
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

function BotonPrevia({ item, activa, onVerPrevia }: { item: LabelCandidate; activa: boolean; onVerPrevia: (i: LabelCandidate) => void }) {
  return (
    <button
      type="button"
      className={`px-2 py-1 rounded-lg text-sm ${activa ? 'text-blue-300 bg-blue-500/15' : 'text-slate-400 hover:text-white'}`}
      disabled={!item.printable}
      onClick={(e) => { e.stopPropagation(); onVerPrevia(item) }}
      aria-label={`Ver etiqueta de ${item.sku}`}
      title="Ver cómo saldrá la etiqueta"
    >
      <i className="fa-regular fa-eye" />
    </button>
  )
}

/** "03/10 15:21" en la zona del navegador; la fecha viene en UTC. */
function horaDeAlta(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const dos = (n: number) => String(n).padStart(2, '0')
  return `${dos(d.getDate())}/${dos(d.getMonth() + 1)} ${dos(d.getHours())}:${dos(d.getMinutes())}`
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

  const detalle = (it: LabelCandidate) => [it.brand, it.size && `Talla ${it.size}`, it.color].filter(Boolean).join(' · ')

  if (esTelefono) {
    return (
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-xs text-slate-300 px-1">
          <input type="checkbox" className="rounded" checked={todoMarcado} onChange={onAlternarTodo} />
          Marcar todo lo imprimible ({imprimibles.length})
        </label>
        {items.map((it) => {
          const marcada = seleccion.has(it.variant_id)
          return (
            <div
              key={it.variant_id}
              onClick={() => it.printable && onAlternar(it.variant_id)}
              className={`rounded-xl border p-3 space-y-2 ${
                marcada ? 'border-blue-500/60 bg-blue-500/10' : 'border-slate-700/50'
              } ${it.printable ? 'cursor-pointer' : 'opacity-50'}`}
            >
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="rounded mt-0.5"
                  checked={marcada}
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
                <BotonPrevia item={it} activa={activa === it.variant_id} onVerPrevia={onVerPrevia} />
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400">
                {detalle(it) && <span>{detalle(it)}</span>}
                <span className="text-slate-300">{formatCurrency(it.price)}</span>
                <span>Exist. {it.stock}</span>
              </div>
              {!it.printable && (
                <p className="text-[11px] text-amber-300">
                  <i className="fa-solid fa-triangle-exclamation mr-1" />{it.reason}
                </p>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <TablaDesplazable sangrado={false}>
      <table className="dax-table text-sm w-full">
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
            <th>Prenda</th>
            <th>Código</th>
            <th className="text-right">Precio · Exist.</th>
            <th className="text-center">Etiquetas</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const marcada = seleccion.has(it.variant_id)
            return (
              <tr
                key={it.variant_id}
                onClick={() => it.printable && onAlternar(it.variant_id)}
                aria-selected={marcada}
                className={`${it.printable ? 'cursor-pointer' : 'opacity-50'} ${marcada ? 'bg-blue-500/10' : ''}`}
              >
                <td>
                  <input
                    type="checkbox"
                    className="rounded"
                    checked={marcada}
                    disabled={!it.printable}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => onAlternar(it.variant_id)}
                    aria-label={`Seleccionar ${it.sku}`}
                  />
                </td>
                <td>
                  <span className="text-slate-200 leading-snug">{it.sale_name || it.product_name}</span>
                  {detalle(it) && <span className="block text-[11px] text-slate-500">{detalle(it)}</span>}
                  {!it.printable && (
                    <span className="block text-[11px] text-amber-300">
                      <i className="fa-solid fa-triangle-exclamation mr-1" />{it.reason}
                    </span>
                  )}
                </td>
                <td className="font-mono text-xs">
                  <span className="block">{it.sku}</span>
                  <span className="block text-slate-500">{it.barcode || '—'}</span>
                  {it.created_at && (
                    <span className="block text-[10px] text-slate-600" title="Fecha de alta">
                      alta {horaDeAlta(it.created_at)}
                    </span>
                  )}
                </td>
                <td className="text-right whitespace-nowrap">
                  <span className="block">{formatCurrency(it.price)}</span>
                  <span className="block text-[11px] text-slate-500">{it.stock} pzas</span>
                </td>
                <td className="text-center whitespace-nowrap">
                  <CeldaCopias item={it} valor={copias[it.variant_id] ?? 0} onCopias={onCopias} />
                  <BotonPrevia item={it} activa={activa === it.variant_id} onVerPrevia={onVerPrevia} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </TablaDesplazable>
  )
}
