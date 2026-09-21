/**
 * MobileLayout — shell propio para las rutas /mobile y /portal.
 *
 * Sustituye al Layout de escritorio (sidebar de 244px + topbar) en teléfono:
 * header compacto, contenido scrolleable y bottom-nav por rol con targets de
 * 44px+ y safe-areas de iOS. En pantallas grandes el contenido se centra en
 * una columna tipo teléfono para que comanda/portal sigan siendo usables
 * desde la tablet o el escritorio.
 */
import { useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { Toaster } from '../ui/Toast'
import { confirm as confirmDialog } from '../ui/ConfirmDialog'
import { AtlasMark } from '../atlas-one'
import { navMovilPorRol } from '../../utils/navMovil'

export function MobileLayout() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const org = useAuthStore((s) => s.org)
  const logout = useAuthStore((s) => s.logout)
  // El destino de "Menú" depende del preset, igual que en escritorio.
  const { preset, loaded, load, enabledModules } = useEnabledModulesStore()
  useEffect(() => { if (!loaded) load() }, [loaded, load])
  const items = navMovilPorRol(user?.role, preset, loaded ? enabledModules : undefined)

  const handleLogout = async () => {
    const ok = await confirmDialog({
      title: 'Cerrar sesión',
      message: 'Volverás a la pantalla de acceso.',
      variant: 'info',
      confirmText: 'Cerrar sesión',
    })
    if (!ok) return
    logout()
    navigate('/login')
  }

  return (
    <div
      className="flex flex-col h-dvh w-full max-w-screen-sm mx-auto"
      style={{ background: 'var(--dax-bg)', color: 'var(--dax-text)' }}
    >
      {/* Header compacto con safe-area superior */}
      <header
        className="flex items-center justify-between gap-3 px-4 flex-shrink-0"
        style={{
          paddingTop: 'calc(env(safe-area-inset-top, 0px) + 10px)',
          paddingBottom: '10px',
          borderBottom: '1px solid var(--dax-border-dim)',
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <AtlasMark size={22} color="var(--dax-text)" accent="var(--p-accent)" />
          <span className="font-bold text-sm truncate">{org?.name ?? 'Atlas One'}</span>
        </div>
        <button
          onClick={handleLogout}
          aria-label="Cerrar sesión"
          className="min-h-[44px] min-w-[44px] grid place-items-center rounded-lg"
          style={{ color: 'var(--dax-text-muted)' }}
        >
          <i className="fa-solid fa-arrow-right-from-bracket" />
        </button>
      </header>

      {/* Contenido */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-3 h-full">
          <Outlet />
        </div>
      </main>

      {/* Bottom nav con safe-area inferior */}
      <nav
        aria-label="Navegación principal"
        className="flex items-stretch flex-shrink-0"
        style={{
          borderTop: '1px solid var(--dax-border-dim)',
          background: 'var(--dax-card-solid)',
          paddingBottom: 'env(safe-area-inset-bottom, 0px)',
        }}
      >
        {items.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            end={it.end}
            className="flex-1 flex flex-col items-center justify-center gap-1 min-h-[56px] text-[11px] font-semibold"
            style={({ isActive }) => ({
              color: isActive ? 'var(--dax-accent)' : 'var(--dax-text-muted)',
            })}
          >
            <i className={`fa-solid ${it.icon} text-lg`} aria-hidden="true" />
            {it.label}
          </NavLink>
        ))}
      </nav>

      <Toaster />
    </div>
  )
}

export default MobileLayout
