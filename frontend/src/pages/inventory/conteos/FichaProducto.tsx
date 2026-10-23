import { useEffect, useState } from 'react'

import type { ProductoResumen } from '../../../api/conteos'
import { productsApi } from '../../../api/products'
import { Modal } from '../../../components/ui/Modal'
import { toast } from '../../../store/toastStore'
import type { Brand } from '../../../types/products'
import { errorDetailText } from '../../../utils/errorDetail'
import { num } from './avance'

/**
 * Ficha de la pieza recién palomeada, para verificar que la descripción es la
 * correcta, y un formulario corto para corregirla ahí mismo (nombre, marca,
 * modelo, descripción: lo que se lee en la etiqueta y el ticket). Guarda con
 * `PUT /products/{id}` y avisa al conteo para marcar la fila como corregida.
 */
export function FichaProducto({ producto, open, onClose, onCorregida }: {
  producto: ProductoResumen | null
  open: boolean
  onClose: () => void
  /** Se llama tras guardar; el padre marca la línea como corregida y recarga. */
  onCorregida: (producto: ProductoResumen) => Promise<void> | void
}) {
  const [editando, setEditando] = useState(false)
  const [marcas, setMarcas] = useState<Brand[]>([])
  const [form, setForm] = useState({ name: '', brand_id: '', model: '', description: '' })
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!open || !producto) return
    setEditando(false)
    // El nombre base del producto no viaja en el resumen (viene el nombre de venta);
    // se lee del catálogo al abrir el editor para no adivinarlo.
    setForm({
      name: producto.nombre.includes(' · ') ? '' : producto.nombre,
      brand_id: producto.marca_id ?? '', model: producto.modelo ?? '', description: producto.descripcion ?? '',
    })
  }, [open, producto])

  const abrirEditor = async () => {
    if (!producto) return
    try {
      const [p, bs] = await Promise.all([productsApi.getById(producto.product_id), productsApi.getBrands()])
      setMarcas(bs)
      setForm({ name: p.name ?? '', brand_id: p.brand_id ?? '', model: p.model ?? '', description: p.description ?? '' })
      setEditando(true)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir la ficha'))
    }
  }

  const guardar = async () => {
    if (!producto || !form.name.trim()) { toast.warning('El nombre no puede quedar vacío'); return }
    setGuardando(true)
    try {
      await productsApi.update(producto.product_id, {
        name: form.name.trim(), brand_id: form.brand_id || null, model: form.model.trim() || null,
        description: form.description.trim() || null,
      })
      await onCorregida(producto)
      toast.success('Ficha corregida')
      onClose()
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo guardar la ficha'))
    } finally {
      setGuardando(false)
    }
  }

  if (!producto) return null
  return (
    <Modal open={open} onClose={onClose} title={editando ? 'Corregir ficha' : 'Ficha de la pieza'} size="md"
      footer={editando ? (<>
        <button type="button" onClick={() => setEditando(false)} className="dax-btn-secondary flex-1">Cancelar</button>
        <button type="button" onClick={guardar} disabled={guardando} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
          {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Guardar'}
        </button>
      </>) : (<>
        <button type="button" onClick={onClose} className="dax-btn-secondary flex-1">Está bien</button>
        <button type="button" onClick={abrirEditor} className="dax-btn-primary flex-1 justify-center"><i className="fa-solid fa-pen" /> Corregir</button>
      </>)}>
      {!editando ? (
        <div className="flex gap-3">
          {producto.foto && <img src={producto.foto} alt="" className="h-24 w-24 rounded object-cover" />}
          <dl className="text-sm space-y-1 flex-1">
            <div><dt className="text-xs text-slate-400">Nombre de venta</dt><dd className="text-white font-bold">{producto.nombre}</dd></div>
            <div><dt className="text-xs text-slate-400">Marca · modelo</dt><dd className="text-slate-200">{[producto.marca, producto.modelo].filter(Boolean).join(' · ') || '—'}</dd></div>
            <div><dt className="text-xs text-slate-400">Talla · color</dt><dd className="text-slate-200">{[producto.talla, producto.color].filter(Boolean).join(' · ') || '—'}</dd></div>
            <div><dt className="text-xs text-slate-400">Descripción</dt><dd className="text-slate-200 whitespace-pre-wrap">{producto.descripcion || '—'}</dd></div>
            <div><dt className="text-xs text-slate-400">SKU · código · precio</dt><dd className="text-slate-200">{producto.sku} · {producto.barcode ?? 'sin código'} · ${num(producto.precio).toLocaleString('es-MX')}</dd></div>
          </dl>
        </div>
      ) : (
        <div className="space-y-3">
          <label className="block"><span className="text-xs text-slate-400">Nombre</span>
            <input className="dax-input w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="block"><span className="text-xs text-slate-400">Marca</span>
            <select className="dax-input w-full" value={form.brand_id} onChange={(e) => setForm({ ...form, brand_id: e.target.value })}>
              <option value="">Sin marca</option>
              {marcas.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select></label>
          <label className="block"><span className="text-xs text-slate-400">Modelo</span>
            <input className="dax-input w-full" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} /></label>
          <label className="block"><span className="text-xs text-slate-400">Descripción</span>
            <textarea className="dax-input w-full" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        </div>
      )}
    </Modal>
  )
}
