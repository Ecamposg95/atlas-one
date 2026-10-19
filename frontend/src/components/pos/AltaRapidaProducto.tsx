import { Modal } from '../ui/Modal'
import { FormularioProducto } from '../products/FormularioProducto'

/**
 * Alta rápida desde el POS en modo básico: el formulario único (corto por
 * `campos_producto`) dentro del Modal del kit. POS.tsx lo carga con `lazy()`
 * para que el formulario no viaje en `POS-*.js` (presupuesto de la ruta
 * crítica). El toast de "Producto creado." ya lo da el formulario.
 */
export default function AltaRapidaProducto({ onClose, onCreado }: { onClose: () => void; onCreado: () => void }) {
  return (
    <Modal open onClose={onClose} size="xl" closeOnBackdrop={false} closeOnEscape={false} title="Nuevo producto">
      <FormularioProducto mode="create" presentacion="modal" onDone={() => onCreado()} onCancel={onClose} />
    </Modal>
  )
}
