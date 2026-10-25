import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { productsApi } from '../../api/products'
import type { Product } from '../../types/products'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { formatCurrency } from '../../utils/currency'

// Formateador compartido: centavos incluidos — redondear al peso mostraba
// precios incorrectos frente al cliente ($25.50 aparecía como $26).
const money = (n: number) => formatCurrency(n)

/** Accent del preset actual (leído del CSS): violeta bar, marrón café, naranja restaurant… */
function presetAccent(): string {
  if (typeof document === 'undefined') return '#8b4a2b'
  return getComputedStyle(document.documentElement).getPropertyValue('--p-accent').trim() || '#8b4a2b'
}

export function MenuVisual() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [cat, setCat] = useState<string>('__all__')
  const accent = presetAccent()

  useEffect(() => {
    let alive = true
    setLoading(true)
    productsApi.list({ limit: 300, is_active: true })
      .then((r) => { if (alive) setProducts(r.items) })
      .catch(() => { if (alive) setFailed(true) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const categories = useMemo(() => {
    const set = new Set<string>()
    products.forEach((p) => set.add(p.department_name || p.department?.name || 'Sin categoría'))
    return Array.from(set).sort()
  }, [products])

  const visible = useMemo(() => {
    if (cat === '__all__') return products
    return products.filter((p) => (p.department_name || p.department?.name || 'Sin categoría') === cat)
  }, [products, cat])

  const grouped = useMemo(() => {
    const map = new Map<string, Product[]>()
    visible.forEach((p) => {
      const k = p.department_name || p.department?.name || 'Sin categoría'
      if (!map.has(k)) map.set(k, [])
      map.get(k)!.push(p)
    })
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [visible])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500 font-semibold">Gastro · Menú</p>
        <div className="flex items-center gap-3 mt-1">
          <i className="fa-solid fa-book-open text-xl" style={{ color: accent }} />
          <h1 className="text-2xl font-black text-white">Menú visual</h1>
        </div>
        <p className="text-sm text-slate-400 mt-0.5">El catálogo del negocio, listo para la barra. {products.length} productos.</p>
      </div>

      {/* Categorías */}
      <div className="flex flex-wrap gap-2">
        {['__all__', ...categories].map((c) => {
          const on = cat === c
          return (
            <button key={c} onClick={() => setCat(c)}
              className="px-3.5 py-1.5 rounded-full text-[13px] font-semibold border transition-colors"
              style={on
                ? { background: accent, borderColor: accent, color: '#fff' }
                : { background: 'transparent', borderColor: 'rgba(148,163,184,0.25)', color: '#cbd5e1' }}>
              {c === '__all__' ? 'Todo' : c}
            </button>
          )
        })}
      </div>

      {failed ? (
        <DaxCard><p className="text-sm text-slate-400 text-center py-6">No se pudo cargar el menú.</p></DaxCard>
      ) : loading ? (
        <Spinner size="lg" text="Cargando menú..." />
      ) : products.length === 0 ? (
        <DaxCard>
          <p className="text-sm text-slate-400 text-center py-6">
            No hay productos. <Link to="/products" style={{ color: accent }}>Agrega productos al catálogo →</Link>
          </p>
        </DaxCard>
      ) : (
        grouped.map(([category, items]) => (
          <section key={category}>
            <p className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold mb-3">
              {category} <span className="text-slate-600">· {items.length}</span>
            </p>
            <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {items.map((p) => (
                <DaxCard key={p.id} padding={false} className="overflow-hidden flex flex-col">
                  <div className="h-24 bg-slate-800 relative"
                    style={p.image_url ? { background: `center/cover no-repeat url(${p.image_url})` } : undefined}>
                    {!p.image_url && (
                      <span className="absolute inset-0 grid place-items-center text-slate-600 text-2xl">
                        <i className="fa-solid fa-utensils" />
                      </span>
                    )}
                  </div>
                  <div className="p-3 flex flex-col gap-1 flex-1">
                    <span className="text-[13px] font-semibold text-white leading-tight">{p.name}</span>
                    <span className="mt-auto text-[15px] font-bold tabular-nums" style={{ color: accent }}>{money(p.price)}</span>
                  </div>
                </DaxCard>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
