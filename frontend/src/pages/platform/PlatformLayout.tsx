import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useTheme } from '../../context/ThemeContext'
import { Toaster } from '../../components/ui/Toast'
import { ImpersonationBanner } from '../../components/layout/ImpersonationBanner'
import { CommandPalette } from '../../components/platform/CommandPalette'
import { NAV_PLATFORM, NAV_ADMIN, MOBILE_PRIMARY_PATHS, splitMobileNav } from './platformNav'
import '../../styles/platform-v2.css'

function initials(input?: string | null): string {
  if (!input) return 'SA'
  const parts = input.trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return input.slice(0, 2).toUpperCase()
}

export function PlatformLayout() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const mobileNav = splitMobileNav([...NAV_PLATFORM, ...NAV_ADMIN], MOBILE_PRIMARY_PATHS)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  // ⌘K / Ctrl+K global hotkey.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Escape cierra la hoja "Más" (barra inferior de teléfono).
  useEffect(() => {
    if (!sheetOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSheetOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sheetOpen])

  const displayName = user?.full_name || user?.username || 'atlas@ops'

  return (
    <div className="pv2">
      <div className="pv2-layout">
        {/* ── Sidebar ─────────────────────────────────────────────── */}
        <aside className="pv2-sidebar" aria-label="Platform navigation">
          <div className="brand">
            <div className="mark">A</div>
            <div className="name">Atlas</div>
            <div className="env">V2</div>
          </div>

          <button
            type="button"
            className="nav-item pv2-kbar-trigger"
            onClick={() => setPaletteOpen(true)}
            aria-label="Abrir búsqueda"
            title="Buscar (⌘K)"
          >
            <i className="fa-solid fa-magnifying-glass" />
            <span>Buscar</span>
            <kbd
              style={{
                marginLeft: 'auto',
                padding: '1px 6px',
                border: '1px solid var(--p-border)',
                borderRadius: 4,
                background: 'var(--p-surface-2)',
                color: 'var(--p-muted)',
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                fontWeight: 500,
                lineHeight: 1.4,
              }}
            >⌘K</kbd>
          </button>

          <div>
            <div className="group-label">Platform</div>
            {NAV_PLATFORM.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
              >
                <i className={'fa-solid ' + item.icon} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>

          <div>
            <div className="group-label">Admin</div>
            {NAV_ADMIN.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
              >
                <i className={'fa-solid ' + item.icon} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>

          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <button
              type="button"
              className="nav-item"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
              title={theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
            >
              <i className={'fa-solid ' + (theme === 'dark' ? 'fa-sun' : 'fa-moon')} />
              <span>{theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}</span>
            </button>
            <NavLink to="/hq/operations" className="nav-item">
              <i className="fa-solid fa-arrow-left" />
              <span>Salir al App</span>
            </NavLink>
          </div>

          <div className="footer">
            <div className="avatar">{initials(displayName)}</div>
            <div className="meta">
              <span className="nm">{displayName}</span>
              <span className="role">Superadmin</span>
            </div>
            <button
              type="button"
              className="logout-btn"
              onClick={handleLogout}
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
            >
              <i className="fa-solid fa-right-from-bracket" />
            </button>
          </div>
        </aside>

        {/* ── Main surface ────────────────────────────────────────── */}
        <div className="pv2-surface">
          <ImpersonationBanner />
          <div className="pv2-content">
            <Outlet />
          </div>
        </div>
      </div>

      {/* Teléfono (≤480 px): barra inferior con 4 primarias + "Más" */}
      <nav className="pv2-bottombar" aria-label="Navegación móvil">
        {mobileNav.primary.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => 'bb-item' + (isActive ? ' active' : '')}
            onClick={() => setSheetOpen(false)}
          >
            <i className={'fa-solid ' + item.icon} />
            <span>{item.label}</span>
          </NavLink>
        ))}
        <button type="button" className={'bb-item' + (sheetOpen ? ' active' : '')} onClick={() => setSheetOpen((v) => !v)} aria-label="Más opciones">
          <i className="fa-solid fa-ellipsis" />
          <span>Más</span>
        </button>
      </nav>

      {sheetOpen && (
        <>
          <div className="pv2-sheet-backdrop" onClick={() => setSheetOpen(false)} />
          <div className="pv2-sheet" role="dialog" aria-label="Más navegación">
            {mobileNav.rest.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
                onClick={() => setSheetOpen(false)}
              >
                <i className={'fa-solid ' + item.icon} />
                <span>{item.label}</span>
              </NavLink>
            ))}
            <button type="button" className="nav-item" onClick={() => { setSheetOpen(false); toggleTheme() }}>
              <i className={'fa-solid ' + (theme === 'dark' ? 'fa-sun' : 'fa-moon')} />
              <span>{theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}</span>
            </button>
            <NavLink to="/hq/operations" className="nav-item" onClick={() => setSheetOpen(false)}>
              <i className="fa-solid fa-arrow-left" />
              <span>Salir al App</span>
            </NavLink>
            <button type="button" className="nav-item" onClick={handleLogout}>
              <i className="fa-solid fa-right-from-bracket" />
              <span>Cerrar sesión</span>
            </button>
          </div>
        </>
      )}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <Toaster />
    </div>
  )
}
