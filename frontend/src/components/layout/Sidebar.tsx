import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { useBranchCountStore, esTiendaUnica } from '../../store/branchCountStore'
import { returnsApi } from '../../api/returns'
import { confirm } from '../ui/ConfirmDialog'
import { useTheme } from '../../context/ThemeContext'
import { useIsMobile } from '../../hooks/useIsMobile'
import { AtlasMark } from '../atlas-one'
import type { Role } from '../../types/auth'
import { BRANCH_ROLES, urlActiva, visibleNavItems, type NavItem } from './navVisibility'
import { ALL_NAV, ROLE_ROUTES, HQ_NAV_GROUPS, BRANCH_NAV_GROUPS, GASTRO_PRESETS } from './navConfig'

const APPROVER_ROLES: Role[] = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE']
const RETURNS_URLS = new Set(['/returns'])

/** Cómo llamar al acceso sin sucursal fija. Con una sola tienda, "HQ Global"
 *  no nombra nada que la dueña reconozca. */
function rotuloAccesoGlobal(unaSolaSucursal: boolean): string {
  return unaSolaSucursal ? 'Toda la tienda' : 'Todas las sucursales'
}

/** Hook que polea el conteo de devoluciones pendientes cada 60s para roles aprobadores. */
function usePendingReturnsCount(role: Role): number {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!APPROVER_ROLES.includes(role)) return
    let cancelled = false
    const fetch = () => {
      returnsApi.list({ status: 'PENDING' })
        .then((data) => { if (!cancelled) setCount(Array.isArray(data) ? data.length : 0) })
        .catch(() => { /* silencioso */ })
    }
    fetch()
    const id = setInterval(fetch, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [role])
  return count
}

// ── Ítem de navegación ──────────────────────────────────────────
// Solo capa visual (clases `sb-item*` de index.css): la lógica de qué ítems
// se ven vive en `visibleNavItems` y en los grupos de navConfig.
function NavPill({ item, active, pendingReturns }: {
  item: NavItem; active: boolean; pendingReturns: number
}) {
  const showReturnsBadge = RETURNS_URLS.has(item.url) && pendingReturns > 0
  return (
    <Link to={item.url} aria-current={active ? 'page' : undefined} className="sb-item">
      <i className={`fa-solid ${item.icon} sb-item-icono`} aria-hidden="true" />
      <span className="sb-item-rotulo">{item.label}</span>
      {showReturnsBadge && (
        <span className="sb-item-aviso">{pendingReturns > 99 ? '99+' : pendingReturns}</span>
      )}
    </Link>
  )
}

type Seccion = { header: string; items: NavItem[] }

// Lista del menú: secciones rotuladas con sus ítems debajo.
function ListaNav({ secciones, activa, pendingReturns }: {
  secciones: Seccion[]; activa: string | null | undefined; pendingReturns: number
}) {
  return (
    <nav style={{ flex: 1, overflowY: 'auto', padding: '16px 10px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
        {secciones.map((section) => (
          <div key={section.header}>
            <p className="sb-seccion">{section.header}</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {section.items.map((item) => (
                <NavPill
                  key={item.url}
                  item={item}
                  active={item.url === activa}
                  pendingReturns={pendingReturns}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </nav>
  )
}

// ── BRANCH NAV — grupos de sucursal ─────────────────────────────
function BranchNav({ items, pendingReturns }: { items: NavItem[]; pendingReturns: number }) {
  const { pathname } = useLocation()
  const activa = urlActiva(pathname, items.map((it) => it.url))
  const grouped: Seccion[] = []
  const placed = new Set<string>()

  for (const g of BRANCH_NAV_GROUPS) {
    const gItems = items.filter((it) => g.urls.includes(it.url))
    if (gItems.length > 0) {
      grouped.push({ header: g.header, items: gItems })
      gItems.forEach((it) => placed.add(it.url))
    }
  }
  // Mismo respaldo que HQNav: lo que no cae en ningún grupo va a "Más" en vez
  // de desaparecer. Sin esto, la cajera con permiso de Devoluciones (y el
  // gerente con Recetas) se quedaban sin ningún enlace (audit-funcional #15).
  const sobrantes = items.filter((it) => !placed.has(it.url))
  if (sobrantes.length > 0) grouped.push({ header: 'Más', items: sobrantes })

  return <ListaNav secciones={grouped} activa={activa} pendingReturns={pendingReturns} />
}

// ── HQ NAV — lista agrupada + etiquetada (admin/dueño), más legible ──
function HQNav({ items, pendingReturns }: { items: NavItem[]; pendingReturns: number }) {
  const { pathname } = useLocation()
  const activa = urlActiva(pathname, items.map((it) => it.url))
  const grouped: Seccion[] = []
  const placed = new Set<string>()

  for (const g of HQ_NAV_GROUPS) {
    const gItems = g.urls
      .map((u) => items.find((it) => it.url === u))
      .filter((it): it is NavItem => !!it)
    if (gItems.length > 0) {
      grouped.push({ header: g.header, items: gItems })
      gItems.forEach((it) => placed.add(it.url))
    }
  }
  const leftover = items.filter((it) => !placed.has(it.url))
  if (leftover.length > 0) grouped.push({ header: 'Más', items: leftover })

  return <ListaNav secciones={grouped} activa={activa} pendingReturns={pendingReturns} />
}

// Contraer / expandir el menú (solo escritorio; en teléfono el menú es un cajón).
function BotonContraer({ contraido, onClick }: { contraido: boolean; onClick: () => void }) {
  const rotulo = contraido ? 'Expandir menú' : 'Contraer menú'
  return (
    <button
      onClick={onClick}
      title={rotulo}
      aria-label={rotulo}
      className="sb-boton"
      style={{ marginLeft: contraido ? undefined : 'auto', width: '30px', height: '30px' }}
    >
      <i className={`fa-solid ${contraido ? 'fa-indent' : 'fa-outdent'}`} style={{ fontSize: '11px' }} aria-hidden="true" />
    </button>
  )
}

// Inicial de la persona. Neutro: el rol ya se lee en el texto de al lado.
function Avatar({ inicial, titulo }: { inicial: string; titulo?: string }) {
  return (
    <div
      title={titulo}
      style={{
        width: '34px', height: '34px', borderRadius: '50%', flexShrink: 0,
        background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '13px', fontWeight: 500, color: 'white',
      }}
    >
      {inicial}
    </div>
  )
}

// ── MATRIX SIDEBAR (expandido) ──────────────────────────────────
function MatrixSidebar({ items, logout, isBranchRole, onToggle }: { items: NavItem[]; logout: () => void; isBranchRole: boolean; onToggle?: () => void }) {
  const { pathname } = useLocation()
  const { user, org, branch } = useAuthStore()
  const { theme, toggleTheme } = useTheme()
  const unaSolaSucursal = esTiendaUnica(useBranchCountStore((s) => s.count))
  const role = (user?.role ?? 'CAJERO') as Role
  const initial = (user?.full_name || user?.username || 'U').charAt(0).toUpperCase()
  const pendingReturns = usePendingReturnsCount(role)

  return (
    <aside style={{
      // `dvh`: con `100vh` en iOS el pie del sidebar (chip de usuario y
      // «Cerrar sesión») cae bajo la barra de URL y no hay forma de tocarlo.
      width: '244px', minWidth: '244px', height: '100dvh',
      display: 'flex', flexDirection: 'column',
      background: 'var(--sb-bg)', borderRight: '1px solid rgba(255,255,255,0.06)',
      flexShrink: 0,
    }}>

      {/* ── Header: logo + org/sucursal ── */}
      <div style={{
        padding: '18px 14px 14px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', paddingLeft: '4px' }}>
          <span style={{ color: 'var(--p-accent)', display: 'flex' }}>
            <AtlasMark size={28} />
          </span>
          <p style={{ color: 'white', fontWeight: 500, fontSize: '17px', letterSpacing: '-0.01em', lineHeight: 1 }}>
            Atlas <span style={{ fontWeight: 300, color: 'rgba(255,255,255,0.62)' }}>ONE</span>
          </p>
          {onToggle && <BotonContraer contraido={false} onClick={onToggle} />}
        </div>

        {/* Organización y dónde está parada la persona: su sucursal o toda la tienda */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '10px 12px', borderRadius: '16px',
          border: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(255,255,255,0.04)',
        }}>
          <div style={{
            width: '30px', height: '30px', borderRadius: '50%', flexShrink: 0,
            background: 'rgba(255,255,255,0.06)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i
              className={`fa-solid ${branch ? 'fa-store' : 'fa-building'}`}
              style={{ fontSize: '11px', color: 'rgba(255,255,255,0.7)' }}
              aria-hidden="true"
            />
          </div>
          <div style={{ overflow: 'hidden', minWidth: 0 }}>
            <p style={{ fontSize: '13px', fontWeight: 500, color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.25 }}>
              {org?.name ?? '—'}
            </p>
            <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.55)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.3, marginTop: '1px' }}>
              {branch ? branch.name : rotuloAccesoGlobal(unaSolaSucursal)}
            </p>
          </div>
        </div>
      </div>


      {/* ── Nav: rectángulos full-width para roles branch, grid SHORT para HQ ── */}
      {isBranchRole ? (
        <BranchNav items={items} pendingReturns={pendingReturns} />
      ) : (
        <HQNav items={items} pendingReturns={pendingReturns} />
      )}

      {/* ── Footer: user card + logout ── */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', padding: '12px', flexShrink: 0 }}>
        {/* User card */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '2px 4px 10px' }}>
          <Avatar inicial={initial} />
          <div style={{ overflow: 'hidden', minWidth: 0 }}>
            <p style={{ fontSize: '12px', fontWeight: 500, color: 'white', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.25 }}>
              {user?.full_name || user?.username}
            </p>
            <p style={{ fontSize: '10px', fontWeight: 400, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'rgba(168, 162, 154, 0.8)', marginTop: '2px' }}>
              {user?.role}
            </p>
          </div>
        </div>

        {/* Mi expediente — solo roles de sucursal, y solo si el menú (módulo + perfil del plan) lo muestra */}
        {isBranchRole && items.some((n) => n.url === '/hr/me') && (
          <Link
            to="/hr/me"
            aria-current={pathname === '/hr/me' ? 'page' : undefined}
            className="sb-item"
            style={{ marginBottom: '8px' }}
          >
            <i className="fa-solid fa-id-card sb-item-icono" aria-hidden="true" />
            <span className="sb-item-rotulo">Mi expediente</span>
          </Link>
        )}


        {/* Theme toggle — mini cielo animado */}
        <button
          onClick={toggleTheme}
          className={`theme-toggle ${theme === 'dark' ? 'is-dark' : 'is-light'}`}
          aria-label={theme === 'dark' ? 'Modo oscuro — cambiar a modo claro' : 'Modo claro — cambiar a modo oscuro'}
          title={theme === 'dark' ? 'Modo oscuro — cambiar a modo claro' : 'Modo claro — cambiar a modo oscuro'}
        >
          <span className="tt-sky" aria-hidden="true">
            {theme === 'dark' ? (
              <>
                <span className="tt-moon" />
                {[[12, 30], [30, 60], [48, 22], [64, 70], [80, 40], [92, 18]].map(([l, t], i) => (
                  <span key={i} className="tt-star" style={{ left: `${l}%`, top: `${t}%`, animationDelay: `${(i * 0.4) % 2}s` }} />
                ))}
              </>
            ) : (
              <>
                <span className="tt-sun" />
                <span className="tt-cloud" style={{ left: '12%', top: '22%', width: 22 }} />
                <span className="tt-cloud" style={{ left: '58%', top: '55%', width: 16, animationDelay: '-6s', opacity: .8 }} />
              </>
            )}
          </span>
          <span className="tt-label">{theme === 'dark' ? 'Modo oscuro' : 'Modo claro'}</span>
          <i className={`fa-solid ${theme === 'dark' ? 'fa-sun' : 'fa-moon'} tt-icon`} aria-hidden="true" />
        </button>

        {/* Logout */}
        <button
          onClick={logout}
          className="sb-boton"
          style={{ width: '100%', gap: '8px', padding: '9px', fontSize: '12px', fontWeight: 400 }}
        >
          <i className="fa-solid fa-right-from-bracket" style={{ fontSize: '11px' }} aria-hidden="true" />
          <span>Cerrar sesión</span>
        </button>
      </div>
    </aside>
  )
}

// ── ICON RAIL (contraído) ───────────────────────────────────────
function IconRail({ items, logout, onToggle }: { items: NavItem[]; logout: () => void; onToggle?: () => void }) {
  const { pathname } = useLocation()
  const activa = urlActiva(pathname, items.map((it) => it.url))
  const { user, org, branch } = useAuthStore()
  const unaSolaSucursal = esTiendaUnica(useBranchCountStore((s) => s.count))
  const role = (user?.role ?? 'CAJERO') as Role
  const pendingReturns = usePendingReturnsCount(role)
  const initial = (user?.full_name || user?.username || 'U').charAt(0).toUpperCase()
  const orgInitial = (org?.name ?? 'A').charAt(0).toUpperCase()

  return (
    <aside style={{
      width: '72px', minWidth: '72px', height: '100dvh',
      display: 'flex', flexDirection: 'column',
      background: 'var(--sb-bg)', borderRight: '1px solid rgba(255,255,255,0.06)',
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{
        height: '60px', display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0,
      }}>
        <span style={{ color: 'var(--p-accent)', display: 'flex', filter: 'drop-shadow(0 0 10px var(--sb-glow))' }}>
          <AtlasMark size={28} />
        </span>
      </div>

      {onToggle && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
          <BotonContraer contraido onClick={onToggle} />
        </div>
      )}

      {/* Organización y sucursal, en un solo punto */}
      <div style={{
        display: 'flex', justifyContent: 'center',
        padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0,
      }}>
        <div
          title={`${org?.name ?? 'Organización'} · ${branch ? branch.name : rotuloAccesoGlobal(unaSolaSucursal)}`}
          style={{
            width: '34px', height: '34px', borderRadius: '50%',
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '12px', fontWeight: 500, color: 'rgba(255,255,255,0.85)',
          }}
        >
          {orgInitial}
        </div>
      </div>


      {/* Icon column */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '10px 6px' }}>
        {items.map((item) => {
          const active = item.url === activa
          const showReturnsBadge = RETURNS_URLS.has(item.url) && pendingReturns > 0
          return (
            <Link
              key={item.url}
              to={item.url}
              title={`${item.label}${showReturnsBadge ? ` (${pendingReturns} pendientes)` : ''}`}
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
              className="sb-item sb-item-riel"
            >
              <i className={`fa-solid ${item.icon} sb-item-icono`} aria-hidden="true" />
              {showReturnsBadge && (
                <span className="sb-item-aviso">{pendingReturns > 9 ? '9+' : pendingReturns}</span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* Avatar + logout */}
      <div style={{
        borderTop: '1px solid rgba(255,255,255,0.06)', padding: '10px 6px', flexShrink: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
      }}>
        <Avatar inicial={initial} titulo={`${user?.full_name || user?.username} · ${user?.role}`} />
        <button
          onClick={logout}
          title="Cerrar sesión"
          aria-label="Cerrar sesión"
          className="sb-boton"
          style={{ width: '34px', height: '34px' }}
        >
          <i className="fa-solid fa-right-from-bracket" style={{ fontSize: '11px' }} aria-hidden="true" />
        </button>
      </div>
    </aside>
  )
}

// ── ROOT ────────────────────────────────────────────────────────
export function Sidebar({ collapsed = false, onToggle }: { collapsed?: boolean; onToggle?: () => void }) {
  const { user, logout, isAuthenticated } = useAuthStore()
  const role = (user?.role ?? 'CAJERO') as Role
  const allowed = ROLE_ROUTES[role] ?? []

  // Module gating: items with `module` declared only appear when the org has
  // that module enabled. Items without `module` are always shown.
  const { enabledModules, preset, loaded, load, plan, perfilUi, noDisponibles } = useEnabledModulesStore()
  useEffect(() => {
    if (isAuthenticated && !loaded) load()
  }, [isAuthenticated, loaded, load])

  // Cuántas sucursales hay: decide si los rótulos dicen "tienda" o "sucursales".
  const cargarConteoSucursales = useBranchCountStore((s) => s.load)
  useEffect(() => {
    if (isAuthenticated) void cargarConteoSucursales()
  }, [isAuthenticated, cargarConteoSucursales])

  const enMovil = useIsMobile()
  // El gating por módulo (y el fail-open mientras carga) vive en
  // `visibleNavItems`, que es pura y tiene pruebas.
  const isGastro = !!preset && GASTRO_PRESETS.has(preset)
  // Consultar (cámara y precio) solo sale en teléfono y tablet; en escritorio se consulta en Productos.
  const items = visibleNavItems(ALL_NAV, { role, allowed, enabledModules, isGastro, plan, perfilUi, noDisponibles, escritorio: !enMovil })

  const handleLogout = async () => {
    const ok = await confirm({
      title: 'Cerrar sesión',
      message: '¿Estás segura/seguro que quieres cerrar tu sesión?',
      confirmText: 'Cerrar sesión',
      cancelText: 'Cancelar',
      variant: 'danger',
    })
    if (ok) logout()
  }

  const isBranchRole = BRANCH_ROLES.includes(role)

  if (collapsed) return <IconRail items={items} logout={handleLogout} onToggle={onToggle} />
  return <MatrixSidebar items={items} logout={handleLogout} isBranchRole={isBranchRole} onToggle={onToggle} />
}
