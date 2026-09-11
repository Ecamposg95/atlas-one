import { useState } from 'react'
import type {
  AttentionItem,
  AttentionKey,
  AttentionLists,
} from '../../../types/platformOverview'
import { formatCurrency } from '../../../utils/currency'
import { attentionChips, fmtCloseAt } from './orgFormat'

const SECTIONS: { key: AttentionKey; title: string; fmt: (i: AttentionItem) => string }[] = [
  { key: 'no_cut', title: 'Sin corte >14 h', fmt: (i) => `${i.value ?? 0} h` },
  // `detail` de cut_difference es el last_close_at ISO del corte — sin fecha,
  // "$480" no dice si es de hoy o de hace tres días.
  { key: 'cut_difference', title: 'Cortes con diferencia',
    fmt: (i) => `${formatCurrency(i.value ?? 0)} · ${fmtCloseAt(i.detail)}` },
  { key: 'oldest_returns', title: 'Devoluciones pendientes', fmt: (i) => formatCurrency(i.value ?? 0) },
  { key: 'cancelled_today', title: 'Canceladas hoy', fmt: (i) => formatCurrency(i.value ?? 0) },
]

interface Props {
  attention: AttentionLists
  variant: 'panel' | 'strip'
  /** Saltar a la organización de un renglón (abre el modo Organización en ella). */
  onPickOrg?: (orgId: number) => void
}

function ItemRow({
  item,
  texto,
  onPickOrg,
}: {
  item: AttentionItem
  texto: string
  onPickOrg?: (orgId: number) => void
}) {
  const contenido = (
    <>
      <span className="nm">{item.name} <span className="hint">· {item.org_name}</span></span>
      <span className="val">{texto}</span>
    </>
  )
  if (!onPickOrg) return <div className="item" title={item.detail}>{contenido}</div>
  return (
    <button
      type="button"
      className="item"
      title={`${item.detail} · ver ${item.org_name}`}
      onClick={() => onPickOrg(item.org_id)}
    >
      {contenido}
    </button>
  )
}

/** Los pendientes del día de TODAS las organizaciones. Cada renglón trae su
 *  organización: la tira nunca suma el dinero de dos clientes distintos. */
export function AttentionPanel({ attention, variant, onPickOrg }: Props) {
  // En la tira, el chip abre el detalle de su lista (y lo vuelve a cerrar).
  const [abierta, setAbierta] = useState<AttentionKey | null>(null)

  if (variant === 'strip') {
    const chips = attentionChips(attention)
    if (chips.length === 0) return null
    const seccion = abierta ? SECTIONS.find((s) => s.key === abierta) : undefined
    return (
      <section aria-label="Atención hoy">
        <div className="pv2-attention-strip">
          {chips.map((c) => (
            <button
              key={c.key}
              type="button"
              className={`pv2-chip ${c.tone}`}
              aria-expanded={abierta === c.key}
              onClick={() => setAbierta(abierta === c.key ? null : c.key)}
            >
              <i className="fa-solid fa-triangle-exclamation" aria-hidden="true" /> {c.label}
            </button>
          ))}
        </div>
        {seccion && (
          <div className="pv2-attention-card" style={{ marginTop: 10 }}>
            <div className="head">
              <span>{seccion.title}</span>
              <span className="mono">{attention[seccion.key].length}</span>
            </div>
            {attention[seccion.key].map((i) => (
              <ItemRow key={`${seccion.key}-${i.id}`} item={i} texto={seccion.fmt(i)} onPickOrg={onPickOrg} />
            ))}
          </div>
        )}
      </section>
    )
  }

  return (
    <aside className="pv2-attention" aria-label="Atención hoy">
      {SECTIONS.map((s) => {
        const items = attention[s.key]
        return (
          <div key={s.key} className="pv2-attention-card">
            <div className="head"><span>{s.title}</span><span className="mono">{items.length}</span></div>
            {items.length === 0
              ? <div className="pv2-attention-empty">Nada que atender</div>
              : items.map((i) => (
                <ItemRow key={`${s.key}-${i.id}`} item={i} texto={s.fmt(i)} onPickOrg={onPickOrg} />
              ))}
          </div>
        )
      })}
    </aside>
  )
}
