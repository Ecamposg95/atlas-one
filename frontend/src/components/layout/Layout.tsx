import { useState, useEffect, useMemo, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { BranchSwitcher } from './BranchSwitcher'
import { ImpersonationBanner } from './ImpersonationBanner'
import { AnnouncementBanner } from './AnnouncementBanner'
import { ForeignSessionBanner } from './ForeignSessionBanner'
import { Toaster } from '../ui/Toast'
import { useAuthStore } from '../../store/authStore'
import { useTheme } from '../../context/ThemeContext'
import { useIsMobile } from '../../hooks/useIsMobile'
import { estiloCajon, cajonEsInerte } from '../../utils/cajonLateral'
import type { Role } from '../../types/auth'
import { routeTitle } from './navConfig'

const ADMIN_ROLES: Role[] = ['ADMINISTRADOR', 'DUEÑO']

const ROLE_LABEL: Record<Role, string> = {
  ADMINISTRADOR:     'Administrador',
  DUEÑO:             'Dueño',
  GERENTE:           'Gerente',
  CAJERO:            'Cajero',
  VENDEDOR:          'Vendedor',
  SOPORTE_OPERATIVO: 'Soporte',
  CLIENTE:           'Cliente',
}

export function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const { user, org } = useAuthStore()
  const location = useLocation()
  const { theme } = useTheme()
  const role = (user?.role ?? 'CAJERO') as Role

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

  const userInitial = ((user?.full_name || user?.username) ?? 'U').charAt(0).toUpperCase()
  const userName = user?.full_name || user?.username || ''
  const isAdmin = ADMIN_ROLES.includes(role)

  // Routes that need full viewport height with no padding/max-width container
  const isFullBleed = location.pathname === '/pos'

  // `h-dvh` y no `h-screen`: en iOS Safari `100vh` mide el viewport SIN la
  // barra de URL, así que el armazón queda 80-110 px más alto que la pantalla
  // visible y, con `overflow-hidden`, ese tramo (totales del POS, pie) es
  // inalcanzable. En escritorio dvh == vh: nada cambia.
  return (
    <div className="flex h-dvh overflow-hidden" style={{ background: 'var(--dax-bg)' }}>
      <div
        ref={cajonRef}
        style={estiloCajon(esMovil, cajonAbierto)}
        role={esMovil ? 'dialog' : undefined}
        aria-modal={esMovil && cajonAbierto ? true : undefined}
        aria-label={esMovil ? 'Menú principal' : undefined}
        id="cajon-lateral"
      >
        <Sidebar collapsed={!esMovil && collapsed} />
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
        {/* ── Topbar ── */}
        <header
          className="flex items-center justify-between px-5 flex-shrink-0"
          style={{
            height: '60px',
            background: theme === 'dark' ? 'rgba(11,11,34,0.85)' : 'rgba(246,245,241,0.88)',
            borderBottom: '1px solid var(--dax-border-dim)',
            backdropFilter: 'blur(12px)',
          }}
        >
          {/* LEFT — hamburger + page context */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => (esMovil ? setCajonAbierto(a => !a) : setCollapsed(c => !c))}
              aria-expanded={esMovil ? cajonAbierto : undefined}
              aria-controls={esMovil ? 'cajon-lateral' : undefined}
              className="transition-colors p-1.5 rounded-lg flex-shrink-0 dax-btn-icon"
              style={{ color: 'rgba(148,163,184,0.6)' }}
              onMouseEnter={e => ((e.currentTarget as HTMLElement).style.color = 'white')}
              onMouseLeave={e => ((e.currentTarget as HTMLElement).style.color = 'rgba(148,163,184,0.6)')}
              title={
                esMovil
                  ? (cajonAbierto ? 'Cerrar menú' : 'Abrir menú')
                  : (collapsed ? 'Expandir menú' : 'Contraer menú')
              }
            >
              <i
                className={`fa-solid ${
                  esMovil
                    ? (cajonAbierto ? 'fa-xmark' : 'fa-bars')
                    : (collapsed ? 'fa-indent' : 'fa-outdent')
                } text-sm`}
              />
            </button>

            <div className="flex flex-col min-w-0">
              {/* En teléfono se conserva el título de la pantalla (I-9); el
                  nombre de la organización solo cabe desde sm. */}
              <span
                className="hidden sm:block"
                style={{ fontSize: '0.6rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.2em', color: 'var(--dax-text-faint)', lineHeight: 1 }}
              >
                {org?.name ?? 'Atlas One'}
              </span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span
                  style={{ fontSize: '0.875rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '-0.01em', color: 'var(--dax-text)', lineHeight: 1 }}
                  className="truncate"
                >
                  {pageTitle}
                </span>
              </div>
            </div>
          </div>

          {/* RIGHT — branch switcher + session dot + user chip + clock */}
          <div className="flex items-center gap-3 flex-shrink-0">
            {isAdmin && <BranchSwitcher />}

            <div className="flex items-center gap-1.5">
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ background: '#34d399', boxShadow: '0 0 6px #34d399' }}
              />
              <span
                className="hidden md:block text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: 'rgba(52,211,153,0.7)' }}
              >
                Activo
              </span>
            </div>

            {user && (
              <div className="flex items-center gap-2">
                <div className="hidden md:flex flex-col items-end">
                  <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--dax-text)', lineHeight: 1.2 }}>
                    {userName}
                  </span>
                  <span style={{ fontSize: '0.55rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--dax-text-faint)', lineHeight: 1.2 }}>
                    {ROLE_LABEL[role]}
                  </span>
                </div>
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-black text-white flex-shrink-0"
                  style={{ background: 'linear-gradient(135deg, var(--p-accent), var(--p-accent-hover))' }}
                >
                  {userInitial}
                </div>
              </div>
            )}

            {/* En teléfono el reloj cede su sitio al título de la pantalla. */}
            <div className="hidden sm:block"><Clock /></div>
          </div>
        </header>

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

        {/* ── Footer ── */}
        {/* El pie decorativo pide ~437 px de ancho (leyenda + reloj con fecha):
            a 390 px desborda de lado y se lleva 40 px de alto útil. Se oculta
            por debajo de `sm`; de ahí en adelante se ve igual que siempre, con
            el hueco de la barra de inicio sumado a su alto fijo (0 px en
            escritorio). */}
        <footer
          className="hidden sm:flex items-center justify-center gap-6 flex-shrink-0 px-6"
          style={{
            height: 'calc(40px + env(safe-area-inset-bottom, 0px))',
            paddingBottom: 'env(safe-area-inset-bottom, 0px)',
            background: theme === 'dark' ? 'rgba(11,11,34,0.5)' : 'rgba(241,240,234,0.6)',
            borderTop: '1px solid var(--dax-border-dim)',
          }}
        >
          <span style={{ fontSize: '0.68rem', color: 'var(--dax-text-faint)', fontWeight: 500 }}>
            Desarrollado con ❤️ por{' '}
            <span style={{ color: 'var(--dax-accent)', fontWeight: 800 }}>Atlas Tech</span>
          </span>
          <FooterClock />
        </footer>
      </div>

      <Toaster />
    </div>
  )
}

function Clock() {
  const [time, setTime] = useState('')
  useEffect(() => {
    const fmt = () =>
      new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })
    setTime(fmt())
    const id = setInterval(() => setTime(fmt()), 10_000)
    return () => clearInterval(id)
  }, [])
  return (
    <span
      className="font-mono text-sm tabular-nums font-semibold flex-shrink-0"
      style={{ color: 'rgba(148,163,184,0.7)' }}
    >
      {time}
    </span>
  )
}

function FooterClock() {
  const [dt, setDt] = useState('')
  useEffect(() => {
    const fmt = () =>
      new Date().toLocaleString('es-MX', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: true,
      })
    setDt(fmt())
    const id = setInterval(() => setDt(fmt()), 1_000)
    return () => clearInterval(id)
  }, [])
  return (
    <span
      className="font-mono tabular-nums"
      style={{ fontSize: '0.65rem', fontWeight: 600, color: 'rgba(100,116,139,0.45)' }}
    >
      {dt}
    </span>
  )
}
