import { useState } from 'react'
import { useAuthStore } from '../../store/authStore'
import { useCanalTienda } from '../../hooks/useCanalTienda'
import { vistaDeConfiguracion } from '../../utils/vistaDeConfiguracion'
import { PrinterSettings } from './PrinterSettings'
import { PrinterSettingsCajera } from './PrinterSettingsCajera'
import { TiendaEnLinea } from '../core/TiendaEnLinea'

/** `/configuracion`: la pantalla completa para quien responde por la sucursal, la de caja para la cajera. */
export function Configuracion() {
  const role = useAuthStore((s) => s.user?.role)
  const { puedePublicar } = useCanalTienda()
  const [pestana, setPestana] = useState<'impresora' | 'tienda'>('impresora')
  if (vistaDeConfiguracion(role) !== 'completa') return <PrinterSettingsCajera />
  if (!puedePublicar) return <PrinterSettings />
  return (
    <div className="space-y-4">
      <div className="flex gap-2" role="tablist">
        <button type="button" role="tab" aria-selected={pestana === 'impresora'} onClick={() => setPestana('impresora')}
          className={`${pestana === 'impresora' ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}>Impresora</button>
        <button type="button" role="tab" aria-selected={pestana === 'tienda'} onClick={() => setPestana('tienda')}
          className={`${pestana === 'tienda' ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}>Tienda en línea</button>
      </div>
      {pestana === 'impresora' ? <PrinterSettings /> : <TiendaEnLinea />}
    </div>
  )
}
