import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { FormularioProducto } from '../../components/products/FormularioProducto'
import { destinoDeRegreso } from './volver'

/**
 * Página de alta/edición de producto (`/products/new`, `/products/:id/edit`).
 * Solo decide el modo y a dónde volver; el formulario es `FormularioProducto`.
 * Acepta `?volver=/ruta` para regresar a quien la abrió (por defecto, `/products`).
 */
export function ProductForm() {
  const navigate = useNavigate()
  const { search } = useLocation()
  const { id } = useParams<{ id?: string }>()
  const volver = () => navigate(destinoDeRegreso(search, '/products'))
  return (
    <FormularioProducto
      mode={id ? 'edit' : 'create'}
      productId={id}
      presentacion="pagina"
      onDone={volver}
      onCancel={volver}
    />
  )
}
