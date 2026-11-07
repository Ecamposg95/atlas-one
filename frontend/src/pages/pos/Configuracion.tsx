import { useAuthStore } from '../../store/authStore'
import { vistaDeConfiguracion } from '../../utils/vistaDeConfiguracion'
import { PrinterSettings } from './PrinterSettings'
import { PrinterSettingsCajera } from './PrinterSettingsCajera'

/** `/configuracion`: la pantalla completa para quien responde por la sucursal, la de caja para la cajera. */
export function Configuracion() {
  const role = useAuthStore((s) => s.user?.role)
  return vistaDeConfiguracion(role) === 'completa' ? <PrinterSettings /> : <PrinterSettingsCajera />
}
