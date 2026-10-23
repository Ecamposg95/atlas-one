import { useEffect, useState } from 'react'

import type { ProductoResumen } from '../../../api/conteos'
import { productsApi } from '../../../api/products'
import { ProductImageUploader } from '../../../components/products/ProductImageUploader'
import { DaxCard } from '../../../components/ui/DaxCard'
import { Modal } from '../../../components/ui/Modal'
import { toast } from '../../../store/toastStore'
import type { Brand, Department, Product } from '../../../types/products'
import { errorDetailText } from '../../../utils/errorDetail'
import { num } from './avance'
import { cambiosFicha, formDesde, type FormFicha } from './ficha'

const FORM_VACIO: FormFicha = {
  name: '', brand_id: '', model: '', description: '', department_id: '',
  size: '', color: '', barcode: '', price: '', cost: '',
}

/**
 * Ficha de la pieza que se está revisando, con todo lo que se corrige durante
 * el conteo sin ir al catálogo: del PRODUCTO nombre, marca, modelo,
 * descripción, departamento y foto; de ESTA TALLA talla, color, código de
 * barras, precio y costo. Cada bloque guarda por su API (PUT producto / PUT
 * variante) y solo viaja lo que cambió (`cambiosFicha`). Tras guardar avisa al
 * conteo para marcar la fila como corregida y recargar.
 *
 * Dos montajes: `modo="modal"` (teléfono y tablet, ventana del kit) y
 * `modo="panel"` (escritorio, tarjeta fija a la derecha de la lista, donde la
 * pistola sigue palomeando mientras se corrige).
 */
export function FichaProducto({ producto, open, onClose, onCorregida, modo = 'modal', onEditando }: {
  producto: ProductoResumen | null
  open: boolean
  onClose: () => void
  /** Se llama tras guardar (o cambiar la foto); el padre marca la línea como corregida y recarga. */
  onCorregida: (producto: ProductoResumen) => Promise<void> | void
  modo?: 'modal' | 'panel'
  /** El padre no cambia de pieza mientras se edita en el panel. */
  onEditando?: (editando: boolean) => void
}) {
  const [editando, setEditando] = useState(false)
  const [marcas, setMarcas] = useState<Brand[]>([])
  const [departamentos, setDepartamentos] = useState<Department[]>([])
  const [completo, setCompleto] = useState<Product | null>(null)
  const [original, setOriginal] = useState<FormFicha>(FORM_VACIO)
  const [form, setForm] = useState<FormFicha>(FORM_VACIO)
  const [guardando, setGuardando] = useState(false)

  // Al cambiar de pieza (no al recargar la misma: el objeto se renueva con la lista) se vuelve a la vista.
  const variantId = producto?.variant_id ?? null
  useEffect(() => { setEditando(false); setCompleto(null) }, [open, variantId])
  useEffect(() => { onEditando?.(editando) }, [editando, onEditando])

  const abrirEditor = async () => {
    if (!producto) return
    try {
      const [p, bs, ds] = await Promise.all([productsApi.getById(producto.product_id), productsApi.getBrands(), productsApi.getDepartments()])
      setMarcas(bs); setDepartamentos(ds); setCompleto(p)
      const f = formDesde(p, producto.variant_id)
      setOriginal(f); setForm(f)
      setEditando(true)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir la ficha'))
    }
  }

  const guardar = async () => {
    if (!producto) return
    const c = cambiosFicha(original, form)
    if (c.error) { toast.warning(c.error); return }
    if (!c.producto && !c.variante) { toast.info('Sin cambios'); setEditando(false); return }
    setGuardando(true)
    try {
      if (c.producto) await productsApi.update(producto.product_id, c.producto)
      if (c.variante) await productsApi.updateVariant(producto.variant_id, c.variante)
      await onCorregida(producto)
      toast.success('Ficha corregida')
      if (modo === 'modal') onClose(); else setEditando(false)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo guardar la ficha'))
    } finally {
      setGuardando(false)
    }
  }

  const fotoCambiada = async (p: Product) => { setCompleto(p); if (producto) await onCorregida(producto) }

  if (!producto || !open) return null

  const campo = (etiqueta: string, k: keyof FormFicha, extra?: { tipo?: string; filas?: number }) => (
    <label className="block"><span className="text-xs text-slate-400">{etiqueta}</span>
      {extra?.filas ? (
        <textarea className="dax-input w-full" rows={extra.filas} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
      ) : (
        <input className="dax-input w-full" type={extra?.tipo ?? 'text'} inputMode={extra?.tipo === 'number' ? 'decimal' : undefined}
          min={extra?.tipo === 'number' ? 0 : undefined} step={extra?.tipo === 'number' ? '0.01' : undefined}
          value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
      )}
    </label>
  )

  const vista = (
    <div className="flex gap-3">
      {producto.foto && <img src={producto.foto} alt="" className="h-24 w-24 rounded object-cover" />}
      <dl className="text-sm space-y-1 flex-1 min-w-0">
        <div><dt className="text-xs text-slate-400">Nombre de venta</dt><dd className="text-white font-bold">{producto.nombre}</dd></div>
        <div><dt className="text-xs text-slate-400">Marca · modelo</dt><dd className="text-slate-200">{[producto.marca, producto.modelo].filter(Boolean).join(' · ') || '—'}</dd></div>
        <div><dt className="text-xs text-slate-400">Talla · color</dt><dd className="text-slate-200">{[producto.talla, producto.color].filter(Boolean).join(' · ') || '—'}</dd></div>
        <div><dt className="text-xs text-slate-400">Departamento</dt><dd className="text-slate-200">{producto.departamento || '—'}</dd></div>
        <div><dt className="text-xs text-slate-400">Descripción</dt><dd className="text-slate-200 whitespace-pre-wrap">{producto.descripcion || '—'}</dd></div>
        <div><dt className="text-xs text-slate-400">SKU · código</dt><dd className="text-slate-200 font-mono text-xs">{producto.sku} · {producto.barcode ?? 'sin código'}</dd></div>
        <div><dt className="text-xs text-slate-400">Precio</dt><dd className="text-slate-200">${num(producto.precio).toLocaleString('es-MX')}</dd></div>
      </dl>
    </div>
  )

  const editor = (
    <div className="space-y-4">
      <section className="space-y-2">
        <h3 className="text-xs font-bold uppercase text-slate-400">Producto</h3>
        {campo('Nombre', 'name')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="block"><span className="text-xs text-slate-400">Marca</span>
            <select className="dax-input w-full" value={form.brand_id} onChange={(e) => setForm({ ...form, brand_id: e.target.value })}>
              <option value="">Sin marca</option>
              {marcas.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select></label>
          {campo('Modelo', 'model')}
        </div>
        <label className="block"><span className="text-xs text-slate-400">Departamento</span>
          <select className="dax-input w-full" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
            <option value="">Sin departamento</option>
            {departamentos.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select></label>
        {campo('Descripción', 'description', { filas: 3 })}
        {completo && <ProductImageUploader product={completo} onUpdated={(p) => void fotoCambiada(p)} />}
      </section>
      <section className="space-y-2">
        <h3 className="text-xs font-bold uppercase text-slate-400">Esta talla · {producto.sku}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {campo('Talla', 'size')}
          {campo('Color', 'color')}
        </div>
        {campo('Código de barras', 'barcode')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {campo('Precio', 'price', { tipo: 'number' })}
          {campo('Costo', 'cost', { tipo: 'number' })}
        </div>
      </section>
    </div>
  )

  const pie = editando ? (<>
    <button type="button" onClick={() => setEditando(false)} className="dax-btn-secondary flex-1">Cancelar</button>
    <button type="button" onClick={guardar} disabled={guardando} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
      {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Guardar'}
    </button>
  </>) : (<>
    <button type="button" onClick={onClose} className="dax-btn-secondary flex-1">{modo === 'modal' ? 'Está bien' : 'Cerrar'}</button>
    <button type="button" onClick={abrirEditor} className="dax-btn-primary flex-1 justify-center"><i className="fa-solid fa-pen" /> Corregir</button>
  </>)

  if (modo === 'panel') {
    return (
      <DaxCard>
        <h2 className="text-sm font-bold text-white mb-2">{editando ? 'Corregir ficha' : 'Ficha de la pieza'}</h2>
        {editando ? editor : vista}
        <div className="mt-3 flex gap-2">{pie}</div>
      </DaxCard>
    )
  }
  return (
    <Modal open={open} onClose={onClose} title={editando ? 'Corregir ficha' : 'Ficha de la pieza'} size="md" footer={pie}>
      {editando ? editor : vista}
    </Modal>
  )
}
