import { Link, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useCanalTienda } from '../../hooks/useCanalTienda'
import { esCentroDeAjustes, vistaDeConfiguracion } from '../../utils/vistaDeConfiguracion'
import { PrinterSettings } from './PrinterSettings'
import { PrinterSettingsCajera } from './PrinterSettingsCajera'
import { TiendaEnLinea } from '../core/TiendaEnLinea'
import { Organization } from '../core/Organization'
import { Sucursales } from '../core/Sucursales'
import { MiPlanYPagos } from '../core/MiPlanYPagos'

/**
 * `/configuracion`. Tres vistas según el rol:
 *   - administrador y dueño: el centro único de ajustes (empresa, sucursales,
 *     ventas y caja, ticket, impresoras, tienda en línea, plan y pagos, y accesos). Lo que
 *     antes eran `/organization` y `/hq/branches` vive aquí, en `?tab=`;
 *   - gerente: la configuración completa de su sucursal (impresoras, cajón, ticket);
 *   - caja: su impresora, la prueba y el cajón.
 */
export type PestanaAjustes = 'empresa' | 'sucursales' | 'ventas' | 'ticket' | 'impresoras' | 'tienda' | 'plan' | 'mas'

const PESTANAS: { id: PestanaAjustes; icon: string; label: string }[] = [
  { id: 'empresa', icon: 'fa-building', label: 'Empresa' },
  { id: 'sucursales', icon: 'fa-store', label: 'Sucursales' },
  { id: 'ventas', icon: 'fa-cash-register', label: 'Ventas y caja' },
  { id: 'ticket', icon: 'fa-receipt', label: 'Ticket' },
  { id: 'impresoras', icon: 'fa-print', label: 'Impresoras' },
  { id: 'tienda', icon: 'fa-globe', label: 'Tienda en línea' },
  { id: 'plan', icon: 'fa-credit-card', label: 'Mi plan y pagos' },
  { id: 'mas', icon: 'fa-ellipsis', label: 'Más' },
]

const ACCESOS = [
  { a: '/users', icon: 'fa-users', titulo: 'Usuarios', texto: 'Altas, roles, sucursal y contraseñas.' },
  { a: '/departments', icon: 'fa-layer-group', titulo: 'Departamentos', texto: 'Cómo se agrupa el catálogo.' },
  { a: '/brands', icon: 'fa-tags', titulo: 'Marcas', texto: 'Marcas del catálogo y sus logos.' },
]

function CentroDeAjustes() {
  const { puedePublicar } = useCanalTienda()
  const [params, setParams] = useSearchParams()
  const visibles = PESTANAS.filter((p) => p.id !== 'tienda' || puedePublicar)
  const pedida = params.get('tab') as PestanaAjustes | null
  const pestana: PestanaAjustes = visibles.some((p) => p.id === pedida) ? pedida! : 'empresa'

  // Cambiar de pestaña suelta lo que era de la anterior (`?sucursal=`).
  const ir = (id: PestanaAjustes) => setParams({ tab: id }, { replace: true })

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-gear text-dax-accent-text text-xl" aria-hidden="true" />
        <h1 className="text-2xl font-black text-dax-text">Configuración</h1>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Secciones de configuración">
        {visibles.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            aria-selected={pestana === p.id}
            onClick={() => ir(p.id)}
            className={`${pestana === p.id ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}
          >
            <i className={`fa-solid ${p.icon}`} aria-hidden="true" /> {p.label}
          </button>
        ))}
      </div>

      {(pestana === 'empresa' || pestana === 'ventas' || pestana === 'ticket') && <Organization key={pestana} seccion={pestana} />}
      {pestana === 'sucursales' && <Sucursales />}
      {pestana === 'impresoras' && <PrinterSettings incrustada />}
      {pestana === 'tienda' && <TiendaEnLinea />}
      {pestana === 'plan' && <MiPlanYPagos />}
      {pestana === 'mas' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {ACCESOS.map((x) => (
            <Link key={x.a} to={x.a} className="block dax-card p-4 max-md:min-h-[44px] hover:opacity-90 transition-opacity">
              <p className="text-sm font-black text-dax-text"><i className={`fa-solid ${x.icon} mr-2 text-dax-accent-text`} aria-hidden="true" />{x.titulo}</p>
              <p className="text-xs text-dax-muted mt-1">{x.texto}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

export function Configuracion() {
  const role = useAuthStore((s) => s.user?.role)
  if (vistaDeConfiguracion(role) !== 'completa') return <PrinterSettingsCajera />
  // El gerente configura su sucursal; la tienda en línea y la empresa son de administrador y dueño.
  return esCentroDeAjustes(role) ? <CentroDeAjustes /> : <PrinterSettings />
}
