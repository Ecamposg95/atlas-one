import { useRef, useState } from 'react'
import { productsApi } from '../../api/products'
import type { Product } from '../../types/products'

interface Props {
  product: Product
  onUpdated: (updated: Product) => void
}

export function ProductImageUploader({ product, onUpdated }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    setUploading(true)
    try {
      const updated = await productsApi.uploadImage(product.id, file)
      onUpdated(updated)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Error al subir imagen')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const handleDelete = async () => {
    setError(null)
    setUploading(true)
    try {
      const updated = await productsApi.deleteImage(product.id)
      onUpdated(updated)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Error al eliminar imagen')
    } finally {
      setUploading(false)
    }
  }

  // Strip cache-bust query string for display purposes
  const imageUrl = product.image_url ?? null

  return (
    <div className="sm:col-span-2 space-y-2">
      <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>
        Imagen del producto
      </label>

      {imageUrl ? (
        <div className="flex items-center gap-3">
          <img
            src={imageUrl}
            alt="Imagen del producto"
            className="w-20 h-20 rounded-lg object-cover border"
            style={{ borderColor: 'var(--dax-border)' }}
          />
          <div className="flex flex-col gap-2">
            <button
              type="button"
              disabled={uploading}
              onClick={() => inputRef.current?.click()}
              className="text-xs px-3 py-1.5 rounded-lg font-medium transition-colors"
              style={{ background: 'var(--dax-surface-raised)', color: 'var(--dax-text)', border: '1px solid var(--dax-border)' }}
            >
              {uploading ? 'Subiendo…' : 'Cambiar imagen'}
            </button>
            <button
              type="button"
              disabled={uploading}
              onClick={handleDelete}
              className="text-xs px-3 py-1.5 rounded-lg font-medium text-red-400 hover:text-red-300 transition-colors"
              style={{ background: 'transparent', border: '1px solid rgba(239,68,68,0.3)' }}
            >
              Eliminar imagen
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
          className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg font-medium transition-colors"
          style={{ background: 'var(--dax-surface-raised)', color: 'var(--dax-text-muted)', border: '1px dashed var(--dax-border)' }}
        >
          <i className="fa-solid fa-image" />
          {uploading ? 'Subiendo…' : 'Subir imagen'}
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={handleFileChange}
      />

      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}
    </div>
  )
}
