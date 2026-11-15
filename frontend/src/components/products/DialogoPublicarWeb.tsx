import { useState } from 'react'
import { productsApi } from '../../api/products'
import { useCanalTienda } from '../../hooks/useCanalTienda'
import { toast } from '../../store/toastStore'
import { Modal } from '../ui/Modal'

interface Props {
  producto: { id: string; name: string }
  onClose: () => void
}

/** Tras un alta: ofrece publicar el producto nuevo en la tienda web (solo admin/dueño con el canal activo). */
export function DialogoPublicarWeb({ producto, onClose }: Props) {
  const { puedePublicar } = useCanalTienda()
  const [enviando, setEnviando] = useState(false)
  if (!puedePublicar) return null

  const publicar = async () => {
    setEnviando(true)
    try {
      await productsApi.webPublish({ ids: [producto.id], published: true })
      toast.success('Publicado en la tienda web.')
      onClose()
    } catch {
      toast.error('No se pudo publicar en la tienda web. Puedes hacerlo después desde Productos.')
      setEnviando(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title="Tienda en línea"
      footer={<>
        <button type="button" className="dax-btn-secondary" onClick={onClose} disabled={enviando}>Ahora no</button>
        <button type="button" className="dax-btn-primary" onClick={publicar} disabled={enviando}>Sí, publicar</button>
      </>}
    >
      <p className="text-sm text-dax-muted">
        <span className="font-semibold">{producto.name}</span> ya está en el catálogo.
      </p>
      <p className="mt-2 text-sm">¿Lo publicamos también en la tienda web?</p>
    </Modal>
  )
}
