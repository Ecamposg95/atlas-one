import { useState, useEffect, useMemo, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { ImpersonationBanner } from './ImpersonationBanner'
import { AnnouncementBanner } from './AnnouncementBanner'
import { ForeignSessionBanner } from './ForeignSessionBanner'
import { Toaster } from '../ui/Toast'
import { useIsMobile } from '../../hooks/useIsMobile'
import { estiloCajon, cajonEsInerte } from '../../utils/cajonLateral'
import { routeTitle } from './navConfig'

export function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()

  const esMovil = useIsMobile()
  const [cajonAbierto, setCajonAbierto] = useState(false)
  const cajonRef = useRef<HTMLDivElement>(null)

  // El cajón se cierra al navegar. Sin esto queda abierto sobre la pantalla
  // nueva y se siente roto.
  useEffect(() => { setCajonAbierto(false) }, [location.pathname])

  // ...y con Escape, como cualquier diálogo.
  useEffect(() => {
    if (!cajonAbierto) return
    const alTeclear = (e: KeyboardEvent) => { if (e.key === 'Escape') setCajonAbierto(false) }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [cajonAbierto])

  // `translateX(-100%)` solo saca el cajón cerrado de la vista, no del árbol
  // de accesibilidad ni del orden de tabulación: un Tab desde el teclado o un
  // lector de pantalla lo recorren igual. `inert` sí lo excluye de ambos. No
  // se pasa como prop de JSX porque @types/react 18 no lo tipa y react-dom
  // 18.3.1 no conoce el atributo: comprobado contra el react-dom instalado,
  // DESCARTA `inert` por completo cuando el valor es booleano —tanto `true`
  // como `false`—, así que la propiedad no serviría ni para activarlo. Se
  // aplica directo sobre el nodo, que es la única vía que funciona aquí.
  useEffect(() => {
    const el = cajonRef.current
    if (!el) return
    if (cajonEsInerte(esMovil, cajonAbierto)) {
      el.setAttribute('inert', '')
    } else {
      el.removeAttribute('inert')
    }
  }, [esMovil, cajonAbierto])

  // Un solo nombre por pantalla: el título de la barra sale del mismo
  // `NavItem` que dibuja el menú (`navConfig.ALL_NAV`).
  const pageTitle = useMemo(() => routeTitle(location.pathname), [location.pathname])

  // Routes that need full viewport height with no padding/max-width container
  const isFullBleed = location.pathname === '/pos'

  // `h-dvh` y no `h-screen`: en iOS Safari `100vh` mide el viewport SIN la
  // barra de URL, así que el armazón queda 80-110 px más alto que la pantalla
  // visible y, con `overflow-hidden`, ese tramo (totales del POS, pie) es
  // inalcanzable. En escritorio dvh == vh: nada cambia.
  return (
    <div className="flex h-dvh overflow-hidden">
      <div
        ref={cajonRef}
        style={estiloCajon(esMovil, cajonAbierto)}
        role={esMovil ? 'dialog' : undefined}
        aria-modal={esMovil && cajonAbierto ? true : undefined}
        aria-label={esMovil ? 'Menú principal' : undefined}
        id="cajon-lateral"
      >
        <Sidebar collapsed={!esMovil && collapsed} onToggle={esMovil ? undefined : () => setCollapsed(c => !c)} />
      </div>

      {esMovil && cajonAbierto && (
        <div
          onClick={() => setCajonAbierto(false)}
          aria-hidden="true"
          style={{
            position: 'fixed', inset: 0, zIndex: 40,
            background: 'rgba(0,0,0,0.5)',
          }}
        />
      )}

      <div className="flex flex-col flex-1 overflow-hidden min-w-0">
        <ForeignSessionBanner />
        <ImpersonationBanner />
        <AnnouncementBanner />
        {/* ── Barra del teléfono ── */}
        {/* En escritorio no hay barra superior: el título ya lo trae cada
            pantalla, y el botón de contraer, el cambio de sucursal, el usuario
            y el cierre de sesión viven en el menú lateral. Por debajo de
            1024 px el menú es un cajón y esta barra es lo único que lo abre. */}
        {esMovil && (
          <header
            className="flex items-center gap-3 px-3 flex-shrink-0"
            style={{
              height: '52px',
              background: 'var(--dax-barra)',
              borderBottom: '1px solid var(--dax-border-dim)',
              backdropFilter: 'blur(20px)',
            }}
          >
            <button
              onClick={() => setCajonAbierto(a => !a)}
              aria-expanded={cajonAbierto}
              aria-controls="cajon-lateral"
              aria-label={cajonAbierto ? 'Cerrar menú' : 'Abrir menú'}
              title={cajonAbierto ? 'Cerrar menú' : 'Abrir menú'}
              className="dax-btn-icon flex-shrink-0"
            >
              <i className={`fa-solid ${cajonAbierto ? 'fa-xmark' : 'fa-bars'} text-sm`} aria-hidden="true" />
            </button>
            <span
              style={{ fontSize: '0.875rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '-0.01em', color: 'var(--dax-text)', lineHeight: 1 }}
              className="truncate"
            >
              {pageTitle}
            </span>
          </header>
        )}

        {/* ── Content ── */}
        {/* El recorte del full-bleed (`/pos`) solo se sostiene cuando hay alto
            de escritorio: por debajo de `lg` la pantalla se desplaza en vez de
            esconder lo que no cabe. En ≥ lg queda el `overflow-hidden` de
            siempre. */}
        <main className={`flex-1 ${isFullBleed ? 'overflow-y-auto lg:overflow-hidden' : 'overflow-y-auto'}`}>
          {isFullBleed ? (
            <Outlet />
          ) : (
            <div className="p-4 sm:p-6 lg:p-8 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] sm:pb-[calc(1.5rem+env(safe-area-inset-bottom,0px))] lg:pb-8 max-w-screen-2xl mx-auto">
              <div className="route-fade" key={location.pathname}>
                <Outlet />
              </div>
            </div>
          )}
        </main>
      </div>

      <Toaster />
    </div>
  )
}
