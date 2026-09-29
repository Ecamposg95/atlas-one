import { useAuthStore } from '../../store/authStore'
import { vistaDeImpresora } from '../../utils/vistaDeImpresora'
import { PrinterSettings } from './PrinterSettings'
import { PrinterSettingsCajera } from './PrinterSettingsCajera'

/** `/printer-settings`: la pantalla completa para admin/dueño, la simple para la caja. */
export function PrinterSettingsPorRol() {
  const role = useAuthStore((s) => s.user?.role)
  return vistaDeImpresora(role) === 'admin' ? <PrinterSettings /> : <PrinterSettingsCajera />
}
