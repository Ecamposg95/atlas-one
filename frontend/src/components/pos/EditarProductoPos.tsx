import { Modal } from '../ui/Modal'
import { FormularioProducto } from '../products/FormularioProducto'
import type { Product } from '../../types/products'

/**
 * Edición desde el POS con el formulario único (SP1-c): el mismo
 * `FormularioProducto` de Productos, dentro del Modal del kit. POS.tsx y la
 * ficha lo cargan con `lazy()` para que el formulario no viaje en `POS-*.js`
 * (presupuesto de la ruta crítica). Sin cerrar con Escape ni con el fondo:
 * un clic accidental no debe tirar lo capturado.
 */
export default function EditarProductoPos({ productId, variantId, onClose, onGuardado }: {
  productId: string
  /** Talla desde la que se abrió la ficha (selector de la ficha); el formulario la pone principal. */
  variantId?: string | null
  onClose: () => void
  onGuardado: (producto: Product) => void
}) {
  return (
    <Modal open onClose={onClose} size="xl" closeOnBackdrop={false} closeOnEscape={false} title="Editar producto">
      <FormularioProducto
        mode="edit"
        productId={productId}
        variantId={variantId ?? undefined}
        presentacion="modal"
        onDone={onGuardado}
        onCancel={onClose}
      />
    </Modal>
  )
}
