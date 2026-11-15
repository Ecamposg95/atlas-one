import { useCallback, useEffect, useRef, useState } from 'react'
import { productsApi } from '../../api/products'
import { toast } from '../../store/toastStore'
import type { ImagenProducto } from '../../types/products'

interface Props {
  productId: string
  /** Foto heredada (campo `image_url`): el servidor la adopta en la galería al primer cambio. */
  imagenHeredada?: string | null
}

/** Galería del producto para la tienda web: subir, reordenar, elegir principal y quitar. */
export function GaleriaProducto({ productId, imagenHeredada }: Props) {
  const [imagenes, setImagenes] = useState<ImagenProducto[]>([])
  const [cargando, setCargando] = useState(true)
  const [ocupado, setOcupado] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const recargar = useCallback(async () => {
    try { setImagenes(await productsApi.listImages(productId)) }
    catch { toast.error('No se pudo cargar la galería.') }
    finally { setCargando(false) }
  }, [productId])
  useEffect(() => { recargar() }, [recargar])

  const correr = async (fn: () => Promise<unknown>, fallo: string) => {
    setOcupado(true)
    try { await fn() } catch { toast.error(fallo) }
    await recargar()
    setOcupado(false)
  }

  const subir = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    await correr(() => productsApi.addImage(productId, f), 'No se pudo subir la foto.')
    if (inputRef.current) inputRef.current.value = ''
  }
  const reordenar = (idx: number, delta: number) => {
    const ids = imagenes.map((i) => i.id)
    const j = idx + delta
    if (j < 0 || j >= ids.length) return
    ;[ids[idx], ids[j]] = [ids[j], ids[idx]]
    const principal = imagenes.find((i) => i.is_primary)?.id ?? ids[0]
    return correr(() => productsApi.orderImages(productId, ids, principal), 'No se pudo reordenar.')
  }
  const hacerPrincipal = (id: string) =>
    correr(() => productsApi.orderImages(productId, imagenes.map((i) => i.id), id), 'No se pudo cambiar la principal.')
  const quitar = (id: string) =>
    correr(() => productsApi.removeImage(productId, id), 'No se pudo quitar la foto.')

  const soloHeredada = !cargando && imagenes.length === 0 && !!imagenHeredada

  return (
    <div className="space-y-2" aria-label="Galería de la tienda web">
      <label className="block text-xs text-dax-muted">Galería para la tienda web</label>
      {soloHeredada && (
        <div className="flex items-center gap-3">
          <img src={imagenHeredada!} alt="Foto principal actual" className="w-20 h-20 rounded-lg object-cover border border-dax-border" />
          <span className="text-xs text-dax-muted">Foto principal actual</span>
        </div>
      )}
      <ul className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {imagenes.map((img, i) => (
          <li key={img.id} className="rounded-lg border border-dax-border p-2 space-y-2">
            <img src={img.url} alt={img.alt ?? ''} className="w-full aspect-square object-cover rounded" />
            {img.is_primary && <span className="dax-badge dax-badge-green text-[10px]">Principal</span>}
            <div className="flex flex-wrap gap-1">
              <button type="button" className="dax-btn-icon" aria-label="Mover antes" disabled={ocupado || i === 0} onClick={() => reordenar(i, -1)}><i className="fa-solid fa-arrow-left" /></button>
              <button type="button" className="dax-btn-icon" aria-label="Mover después" disabled={ocupado || i === imagenes.length - 1} onClick={() => reordenar(i, 1)}><i className="fa-solid fa-arrow-right" /></button>
              {!img.is_primary && <button type="button" className="dax-btn-secondary text-xs" disabled={ocupado} onClick={() => hacerPrincipal(img.id)}>Hacer principal</button>}
              <button type="button" className="dax-btn-icon" aria-label="Quitar foto" disabled={ocupado} onClick={() => quitar(img.id)}><i className="fa-solid fa-trash" /></button>
            </div>
          </li>
        ))}
      </ul>
      <input ref={inputRef} type="file" accept="image/*" className="hidden" aria-label="Agregar foto a la galería" onChange={subir} />
      <button type="button" className="dax-btn-secondary text-xs" disabled={ocupado} onClick={() => inputRef.current?.click()}>
        <i className="fa-solid fa-plus" /> Agregar foto
      </button>
    </div>
  )
}
