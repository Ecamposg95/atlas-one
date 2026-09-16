import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { returnsApi } from '../../api/returns'
import { confirm } from '../ui/ConfirmDialog'
import { useTheme } from '../../context/ThemeContext'
import type { Role } from '../../types/auth'
import { BRANCH_ROLES, visibleNavItems, type NavItem } from './navVisibility'

const APPROVER_ROLES: Role[] = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE']
const RETURNS_URLS = new Set(['/returns', '/hq/returns'])

// Presets gastronómicos (valor de `preset` = industry_type de la org). En estos
// verticales ocultamos los ítems marcados `hideForGastro` (lenguaje retail que
// no aplica a una cocina). Incluye taxonomía v2 (ATLAS_ONE_*) y v1 legacy.
const GASTRO_PRESETS = new Set([
  'ATLAS_ONE_RESTAURANT', 'ATLAS_ONE_CAFE', 'ATLAS_ONE_BAR', 'ATLAS_ONE_GASTRO',
  'RESTAURANT_FULL', 'RESTAURANT_QSR', 'CAFE_BAKERY',
])

// Branch nav group labels — keyed by URL, defines section header shown above each group
const BRANCH_NAV_GROUPS: { header: string; urls: string[] }[] = [
  { header: 'Mi día',        urls: ['/atlas-pos', '/pos'] },
  { header: 'Restaurante',   urls: ['/menu', '/tables', '/mobile/comanda', '/kitchen', '/bar/bottles'] },
  { header: 'Mi turno',      urls: ['/cash-history', '/sales'] },
  { header: 'Inventario',    urls: ['/products', '/scanner'] },
  { header: 'Reportes',      urls: ['/reports', '/meseros'] },
  { header: 'Configuración', urls: ['/printer-settings'] },
]

// HQ/admin nav groups — lista agrupada y etiquetada (más legible que el grid de
// códigos crípticos). Los items no listados caen en "Más" (no se ocultan).
const HQ_NAV_GROUPS: { header: string; urls: string[] }[] = [
  { header: 'Restaurante',  urls: ['/menu', '/tables', '/mobile/comanda', '/kitchen', '/recipes', '/meseros', '/bar/bottles'] },
  { header: 'Operación',    urls: ['/hq/operations', '/hq/reports-hub', '/hq/control'] },
  { header: 'Catálogo',     urls: ['/admin/catalog', '/departments', '/brands'] },
  { header: 'Inventario',   urls: ['/inventory', '/hq/inventory', '/boxes', '/logistics', '/scanner'] },
  { header: 'Ventas',       urls: ['/hq/sales', '/hq/returns', '/quotes', '/quotes/new', '/seguimiento'] },
  { header: 'Compras',      urls: ['/purchases', '/expenses', '/purchasing'] },
  { header: 'Clientes',     urls: ['/customers', '/appointments', '/commissions', '/memberships'] },
  { header: 'Organización', urls: ['/organization', '/hq/branches', '/users', '/hr'] },
  { header: 'Inteligencia', urls: ['/ai'] },
]

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

const ALL_NAV: NavItem[] = [
  { label: 'Operaciones',       short: 'OPS', icon: 'fa-gauge-high',          url: '/hq/operations',    group: 'hq',   sort: 0  },
  { label: 'Reportes',          short: 'REP', icon: 'fa-chart-line',          url: '/hq/reports-hub',   group: 'hq',   sort: 1  },
  { label: 'Control HQ',        short: 'HQ',  icon: 'fa-sliders',             url: '/hq/control',       group: 'hq',   sort: 2  },
  { label: 'Catálogo',          short: 'CAT', icon: 'fa-book',                url: '/admin/catalog',    group: 'hq',   sort: 3,  module: 'catalog' },
  { label: 'Deptos.',           short: 'DEP', icon: 'fa-layer-group',         url: '/departments',      group: 'hq',   sort: 4,  module: 'catalog', hideForGastro: true },
  { label: 'Marcas',            short: 'MRC', icon: 'fa-tags',                url: '/brands',           group: 'hq',   sort: 5,  module: 'catalog', hideForGastro: true },
  { label: 'Ventas HQ',         short: 'VTA', icon: 'fa-receipt',             url: '/hq/sales',         group: 'hq',   sort: 6,  module: 'pos' },
  { label: 'Devoluc. HQ',       short: 'DEV', icon: 'fa-undo',                url: '/hq/returns',       group: 'hq',   sort: 7,  module: 'returns' },
  { label: 'Cotizaciones',      short: 'COT', icon: 'fa-file-invoice',        url: '/quotes',           group: 'hq',   sort: 8,  module: 'quotes' },
  { label: 'Nueva Cot.',        short: 'NEW', icon: 'fa-file-invoice-dollar', url: '/quotes/new',       group: 'hq',   sort: 9,  module: 'quotes' },
  { label: 'Pedidos',           short: 'PED', icon: 'fa-clipboard-check',     url: '/seguimiento',      group: 'hq',   sort: 10, module: 'quotes' },
  { label: 'Compras',           short: 'CMP', icon: 'fa-shopping-cart',       url: '/purchases',        group: 'hq',   sort: 11 },
  { label: 'Gastos',            short: 'GST', icon: 'fa-money-bill-wave',     url: '/expenses',         group: 'hq',   sort: 12 },
  { label: 'Inventario',        short: 'INV', icon: 'fa-boxes',               url: '/inventory',        group: 'hq',   sort: 13, module: 'inventory' },
  { label: 'Scanner',           short: 'SCN', icon: 'fa-barcode',             url: '/scanner',          group: 'hq',   sort: 13.5, module: 'inventory', branchModule: 'scanner' },
  { label: 'Inv. Global',       short: 'GLB', icon: 'fa-globe',               url: '/hq/inventory',     group: 'hq',   sort: 14, module: 'inventory', hideForGastro: true },
  { label: 'Logística',         short: 'LOG', icon: 'fa-truck-loading',       url: '/logistics',        group: 'hq',   sort: 15, module: 'logistics' },
  { label: 'Cajas',             short: 'CJA', icon: 'fa-box-open',            url: '/boxes',            group: 'hq',   sort: 16, module: 'logistics' },
  { label: 'Clientes',          short: 'CRM', icon: 'fa-address-book',        url: '/customers',        group: 'hq',   sort: 17, module: 'crm' },
  { label: 'Empresa',           short: 'EMP', icon: 'fa-building',            url: '/organization',     group: 'hq',   sort: 18 },
  { label: 'Sucursales',        short: 'SCR', icon: 'fa-store',               url: '/hq/branches',      group: 'hq',   sort: 19 },
  { label: 'Usuarios',          short: 'USR', icon: 'fa-users-cog',           url: '/users',            group: 'hq',   sort: 20 },
  { label: 'RRHH',              short: 'HR',  icon: 'fa-user-tie',            url: '/hr',               group: 'hq',   sort: 21 },
  // Atlas One stub modules (Beta — visible when the module is enabled for the org)
  { label: 'Agenda',            short: 'AGE', icon: 'fa-calendar',            url: '/appointments',     group: 'hq',   sort: 22, module: 'appointments' },
  { label: 'Comisiones',        short: 'CMS', icon: 'fa-percent',             url: '/commissions',      group: 'hq',   sort: 23, module: 'commissions' },
  { label: 'Membresías',        short: 'MEM', icon: 'fa-id-card',             url: '/memberships',      group: 'hq',   sort: 24, module: 'memberships' },
  { label: 'Recetas',           short: 'REC', icon: 'fa-book',                url: '/recipes',          group: 'hq',   sort: 25, module: 'recipes' },
  { label: 'IA',                short: 'IA',  icon: 'fa-microchip',           url: '/ai',               group: 'hq',   sort: 26, module: 'ai' },
  { label: 'Pedidos compras',   short: 'OC',  icon: 'fa-truck',               url: '/purchasing',       group: 'hq',   sort: 27, module: 'purchasing' },
  { label: 'Mesas',             short: 'MSA', icon: 'fa-chair',               url: '/tables',           group: 'hq',   sort: 28, module: 'tables' },
  { label: 'Cocina (KDS)',      short: 'KDS', icon: 'fa-fire-burner',         url: '/kitchen',          group: 'hq',   sort: 29, module: 'kitchen' },
  { label: 'Meseros',           short: 'MSR', icon: 'fa-user-tie',            url: '/meseros',          group: 'hq',   sort: 30, module: 'tables' },
  { label: 'Botellas',          short: 'BTL', icon: 'fa-wine-bottle',         url: '/bar/bottles',      group: 'hq',   sort: 31, module: 'bar' },
  { label: 'Menú',              short: 'MNU', icon: 'fa-book-open',           url: '/menu',             group: 'hq',   sort: 32, module: 'menu' },
  { label: 'Comanda',           short: 'CMD', icon: 'fa-clipboard-list',      url: '/mobile/comanda',   group: 'hq',   sort: 33, module: 'tables' },
  { label: 'Mi día',            short: 'INI', icon: 'fa-house',               url: '/atlas-pos',         group: 'pos',  sort: 0  },
  { label: 'Cobrar',            short: 'POS', icon: 'fa-cash-register',       url: '/pos',              group: 'pos',  sort: 1  },
  { label: 'Mis ventas',        short: 'HST', icon: 'fa-history',             url: '/sales',            group: 'pos',  sort: 2  },
  { label: 'Mi caja',           short: 'CRT', icon: 'fa-vault',               url: '/cash-history',     group: 'pos',  sort: 3  },
  { label: 'Devoluciones',      short: 'DEV', icon: 'fa-undo',                url: '/returns',          group: 'pos',  sort: 4  },
  { label: 'Inventario',        short: 'PRD', icon: 'fa-barcode',             url: '/products',         group: 'pos',  sort: 5  },
  { label: 'Reportes',          short: 'REP', icon: 'fa-chart-pie',           url: '/reports',          group: 'pos',  sort: 6  },
  { label: 'Impresora',         short: 'IMP', icon: 'fa-print',               url: '/printer-settings', group: 'pos',  sort: 7  },
  { label: 'Mi Expediente',     short: 'YO',  icon: 'fa-id-card',             url: '/hr/me',            group: 'pos',  sort: 8  },
  { label: 'Dashboard Móvil',   short: 'DSH', icon: 'fa-mobile-screen',       url: '/mobile/dashboard', group: 'mob',  sort: 0  },
  { label: 'Consulta Móvil',    short: 'QRY', icon: 'fa-mobile-alt',          url: '/mobile/query',     group: 'mob',  sort: 1  },
  { label: 'Cotización móvil',  short: 'COT', icon: 'fa-file-invoice',        url: '/mobile/sales',     group: 'mob',  sort: 2  },
  { label: 'Perfil Móvil',      short: 'PRF', icon: 'fa-user-circle',         url: '/mobile/profile',   group: 'mob',  sort: 3  },
]

const ROLE_ROUTES: Record<Role, string[]> = {
  ADMINISTRADOR:    ['/cash-history','/hq/operations','/hq/reports-hub','/hq/control','/admin/catalog','/scanner','/departments','/organization','/users','/customers','/hq/branches','/hq/inventory','/hq/sales','/hq/returns','/brands','/hr','/hr/me','/logistics','/boxes','/quotes','/quotes/new','/seguimiento','/purchases','/expenses','/appointments','/commissions','/memberships','/recipes','/ai','/purchasing','/tables','/kitchen','/meseros','/bar/bottles','/menu','/mobile/comanda'],
  DUEÑO:            ['/cash-history','/hq/operations','/hq/reports-hub','/hq/control','/admin/catalog','/scanner','/customers','/hq/sales','/hq/returns','/hr/me','/logistics','/boxes','/quotes','/quotes/new','/seguimiento','/purchases','/expenses','/appointments','/commissions','/memberships','/recipes','/ai','/purchasing','/tables','/kitchen','/meseros','/bar/bottles','/menu','/mobile/comanda'],
  GERENTE:          ['/cash-history','/reports','/hr/me','/products','/scanner','/pos','/sales','/returns','/atlas-pos','/tables','/kitchen','/recipes','/meseros','/bar/bottles','/menu','/mobile/comanda'],
  CAJERO:           ['/pos','/cash-history','/hr/me','/products','/scanner','/printer-settings','/sales','/returns','/atlas-pos','/tables','/kitchen','/bar/bottles','/menu','/mobile/comanda'],
  VENDEDOR:         ['/mobile/dashboard','/mobile/query','/mobile/sales','/mobile/profile','/hr/me','/atlas-pos'],
  SOPORTE_OPERATIVO:['/mobile/dashboard','/mobile/query','/mobile/profile','/hr/me','/atlas-pos'],
  CLIENTE:          ['/portal'],
}

const ROLE_COLOR: Record<Role, string> = {
  ADMINISTRADOR: '#818cf8', DUEÑO: '#a78bfa', GERENTE: '#60a5fa',
  CAJERO: '#34d399', VENDEDOR: '#fbbf24', SOPORTE_OPERATIVO: '#94a3b8', CLIENTE: '#94a3b8',
}

// ── BRANCH NAV — full-width rectangle buttons ───────────────────
function BranchNav({ items, pendingReturns }: { items: NavItem[]; pendingReturns: number }) {
  const { pathname } = useLocation()
  const grouped: { header: string; items: NavItem[] }[] = []
  const placed = new Set<string>()

  for (const g of BRANCH_NAV_GROUPS) {
    const gItems = items.filter((it) => g.urls.includes(it.url))
    if (gItems.length > 0) {
      grouped.push({ header: g.header, items: gItems })
      gItems.forEach((it) => placed.add(it.url))
    }
  }
  // Items not matched by BRANCH_NAV_GROUPS are silently excluded from the sidebar

  return (
    <nav style={{ flex: 1, overflowY: 'auto', padding: '10px 12px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {grouped.map((section) => (
          <div key={section.header}>
            <p style={{
              fontSize: '9px', fontWeight: 800, textTransform: 'uppercase',
              letterSpacing: '0.12em', color: 'rgba(148,163,184,0.55)',
              marginBottom: '6px', paddingLeft: '4px',
            }}>
              {section.header}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {section.items.map((item) => {
                const active = pathname === item.url || pathname.startsWith(item.url + '/')
                const showReturnsBadge = RETURNS_URLS.has(item.url) && pendingReturns > 0
                return (
                  <Link
                    key={item.url}
                    to={item.url}
                    style={{
                      position: 'relative',
                      display: 'flex', flexDirection: 'row',
                      alignItems: 'center', gap: '12px',
                      padding: '14px 14px',
                      borderRadius: '14px',
                      textDecoration: 'none', transition: 'all 0.15s ease',
                      background: active
                        ? 'var(--sb-active-bg)'
                        : 'rgba(255,255,255,0.055)',
                      border: `1px solid ${active ? 'var(--sb-active-line)' : 'rgba(255,255,255,0.07)'}`,
                      borderLeft: active
                        ? '4px solid var(--p-accent)'
                        : '4px solid transparent',
                      boxShadow: active ? '0 0 12px var(--sb-glow)' : 'none',
                    }}
                  >
                    <i
                      className={`fa-solid ${item.icon}`}
                      style={{
                        fontSize: '18px', flexShrink: 0,
                        color: active ? 'var(--sb-active-icon)' : 'rgba(255,255,255,0.78)',
                      }}
                    />
                    <span style={{
                      fontSize: '13px',
                      fontWeight: active ? 700 : 500,
                      color: active ? 'var(--sb-active-text)' : 'rgba(255,255,255,0.82)',
                      letterSpacing: '-0.01em',
                      flex: 1,
                    }}>
                      {item.label}
                    </span>
                    {showReturnsBadge && (
                      <span style={{
                        minWidth: '20px', height: '20px', padding: '0 5px',
                        borderRadius: '10px', flexShrink: 0,
                        background: '#f59e0b', color: '#1c1917',
                        fontSize: '10px', fontWeight: 900,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 0 8px rgba(245,158,11,0.5)',
                      }}>
                        {pendingReturns > 99 ? '99+' : pendingReturns}
                      </span>
                    )}
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </nav>
  )
}

// ── HQ NAV — lista agrupada + etiquetada (admin/dueño), más legible ──
function HQNav({ items, pendingReturns }: { items: NavItem[]; pendingReturns: number }) {
  const { pathname } = useLocation()
  const grouped: { header: string; items: NavItem[] }[] = []
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

  return (
    <nav style={{ flex: 1, overflowY: 'auto', padding: '10px 12px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {grouped.map((section) => (
          <div key={section.header}>
            <p style={{
              fontSize: '9px', fontWeight: 800, textTransform: 'uppercase',
              letterSpacing: '0.12em', color: 'rgba(255,255,255,0.42)',
              marginBottom: '6px', paddingLeft: '6px',
            }}>
              {section.header}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              {section.items.map((item) => {
                const active = pathname === item.url || pathname.startsWith(item.url + '/')
                const showReturnsBadge = RETURNS_URLS.has(item.url) && pendingReturns > 0
                return (
                  <Link
                    key={item.url}
                    to={item.url}
                    style={{
                      position: 'relative',
                      display: 'flex', alignItems: 'center', gap: '11px',
                      padding: '9px 11px', borderRadius: '10px',
                      textDecoration: 'none', transition: 'all 0.15s ease',
                      background: active ? 'var(--sb-active-bg)' : 'transparent',
                      borderLeft: `3px solid ${active ? 'var(--p-accent)' : 'transparent'}`,
                    }}
                    onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
                    onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent' }}
                  >
                    <i
                      className={`fa-solid ${item.icon}`}
                      style={{
                        fontSize: '15px', width: '18px', textAlign: 'center', flexShrink: 0,
                        color: active ? 'var(--sb-active-icon)' : 'rgba(255,255,255,0.75)',
                      }}
                    />
                    <span style={{
                      fontSize: '12.5px',
                      fontWeight: active ? 700 : 500,
                      color: active ? 'var(--sb-active-text)' : 'rgba(255,255,255,0.9)',
                      letterSpacing: '-0.01em', flex: 1,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {item.label}
                    </span>
                    {showReturnsBadge && (
                      <span style={{
                        minWidth: '18px', height: '18px', padding: '0 5px', borderRadius: '9px', flexShrink: 0,
                        background: '#f59e0b', color: '#1c1917', fontSize: '10px', fontWeight: 900,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        {pendingReturns > 99 ? '99+' : pendingReturns}
                      </span>
                    )}
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </nav>
  )
}

// ── MATRIX SIDEBAR (expandido) ──────────────────────────────────
function MatrixSidebar({ items, logout, isBranchRole }: { items: NavItem[]; logout: () => void; isBranchRole: boolean }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { user, org, branch } = useAuthStore()
  const { theme, toggleTheme } = useTheme()
  const role = (user?.role ?? 'CAJERO') as Role
  const initial = (user?.full_name || user?.username || 'U').charAt(0).toUpperCase()
  const pendingReturns = usePendingReturnsCount(role)

  return (
    <aside style={{
      width: '244px', minWidth: '244px', height: '100vh',
      display: 'flex', flexDirection: 'column',
      background: 'var(--sb-bg)', borderRight: '1px solid rgba(255,255,255,0.06)',
      flexShrink: 0,
    }}>

      {/* ── Header: logo + org/sucursal ── */}
      <div style={{
        padding: '18px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
          <div style={{
            width: '34px', height: '34px', borderRadius: '10px', flexShrink: 0,
            background: 'var(--sb-logo-grad)',
            boxShadow: '0 0 16px var(--sb-glow)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i className="fa fa-bolt" style={{ color: 'white', fontSize: '13px' }} />
          </div>
          <div>
            <p style={{ color: 'white', fontWeight: 900, fontSize: '14px', letterSpacing: '-0.02em', lineHeight: 1 }}>
              Atlas <span style={{ color: 'var(--p-accent)' }}>One</span>
            </p>
            <p style={{ fontSize: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(148,163,184,0.35)', marginTop: '2px' }}>
              v2.0 · Suite Comercial
            </p>
          </div>
        </div>

        {/* Org + Branch info card */}
        <div style={{
          borderRadius: '10px', overflow: 'hidden',
          border: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(255,255,255,0.04)',
        }}>
          {/* Organización */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '8px 10px',
            borderBottom: branch ? '1px solid rgba(255,255,255,0.06)' : 'none',
          }}>
            <div style={{
              width: '22px', height: '22px', borderRadius: '6px', flexShrink: 0,
              background: 'rgba(99,102,241,0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <i className="fa-solid fa-building" style={{ fontSize: '9px', color: '#818cf8' }} />
            </div>
            <div style={{ overflow: 'hidden', minWidth: 0 }}>
              <p style={{ fontSize: '7px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.35)', lineHeight: 1, marginBottom: '2px' }}>
                Organización
              </p>
              <p style={{ fontSize: '10px', fontWeight: 700, color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1 }}>
                {org?.name ?? '—'}
              </p>
            </div>
          </div>

          {/* Sucursal */}
          {branch && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 10px' }}>
              <div style={{
                width: '22px', height: '22px', borderRadius: '6px', flexShrink: 0,
                background: 'rgba(52,211,153,0.12)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <i className="fa-solid fa-store" style={{ fontSize: '9px', color: '#34d399' }} />
              </div>
              <div style={{ overflow: 'hidden', minWidth: 0 }}>
                <p style={{ fontSize: '7px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.35)', lineHeight: 1, marginBottom: '2px' }}>
                  Sucursal
                </p>
                <p style={{ fontSize: '10px', fontWeight: 700, color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1 }}>
                  {branch.name}
                </p>
              </div>
            </div>
          )}

          {/* Sin sucursal asignada → modo HQ */}
          {!branch && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 10px' }}>
              <div style={{
                width: '22px', height: '22px', borderRadius: '6px', flexShrink: 0,
                background: 'rgba(251,191,36,0.1)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <i className="fa-solid fa-globe" style={{ fontSize: '9px', color: '#fbbf24' }} />
              </div>
              <div style={{ overflow: 'hidden', minWidth: 0 }}>
                <p style={{ fontSize: '7px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.35)', lineHeight: 1, marginBottom: '2px' }}>
                  Acceso
                </p>
                <p style={{ fontSize: '10px', fontWeight: 700, color: '#fbbf24', lineHeight: 1 }}>
                  HQ Global
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Nav: rectángulos full-width para roles branch, grid SHORT para HQ ── */}
      {isBranchRole ? (
        <BranchNav items={items} pendingReturns={pendingReturns} />
      ) : (
        <HQNav items={items} pendingReturns={pendingReturns} />
      )}

      {/* ── Footer: user card + logout ── */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', padding: '10px 12px', flexShrink: 0 }}>
        {/* User card */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '9px',
          padding: '9px 10px', borderRadius: '10px', marginBottom: '8px',
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.08)',
        }}>
          <div style={{
            width: '30px', height: '30px', borderRadius: '9px', flexShrink: 0,
            background: 'var(--sb-logo-grad)',
            boxShadow: `0 0 10px ${ROLE_COLOR[role]}55`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '12px', fontWeight: 900, color: 'white',
          }}>
            {initial}
          </div>
          <div style={{ overflow: 'hidden', minWidth: 0 }}>
            <p style={{ fontSize: '11px', fontWeight: 700, color: 'white', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.2 }}>
              {user?.full_name || user?.username}
            </p>
            <p style={{ fontSize: '8px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: ROLE_COLOR[role], marginTop: '2px' }}>
              {user?.role}
            </p>
          </div>
        </div>

        {/* Mi expediente — solo roles de sucursal */}
        {isBranchRole && (
          <button
            onClick={() => navigate('/hr/me')}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
              padding: '8px 10px', borderRadius: '9px', cursor: 'pointer', transition: 'all 0.15s',
              fontSize: '11px', fontWeight: 600,
              color: pathname === '/hr/me' ? 'var(--sb-active-text)' : 'rgba(255,255,255,0.65)',
              background: pathname === '/hr/me' ? 'var(--sb-active-bg)' : 'transparent',
              border: `1px solid ${pathname === '/hr/me' ? 'var(--sb-active-line)' : 'rgba(255,255,255,0.08)'}`,
              marginBottom: '6px',
            }}
            onMouseEnter={e => { if (pathname !== '/hr/me') { const el = e.currentTarget as HTMLElement; el.style.color = 'var(--sb-active-text)'; el.style.background = 'var(--sb-active-bg)'; } }}
            onMouseLeave={e => { if (pathname !== '/hr/me') { const el = e.currentTarget as HTMLElement; el.style.color = 'rgba(255,255,255,0.65)'; el.style.background = 'transparent'; } }}
          >
            <i className="fa-solid fa-id-card" style={{ fontSize: '11px', flexShrink: 0 }} />
            <span>Mi expediente</span>
          </button>
        )}

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
            padding: '8px 10px', borderRadius: '9px', cursor: 'pointer', transition: 'all 0.15s',
            fontSize: '11px', fontWeight: 600,
            color: theme === 'dark' ? '#fbbf24' : '#818cf8',
            background: theme === 'dark' ? 'rgba(251,191,36,0.08)' : 'rgba(99,102,241,0.08)',
            border: `1px solid ${theme === 'dark' ? 'rgba(251,191,36,0.25)' : 'rgba(99,102,241,0.25)'}`,
            marginBottom: '6px',
          }}
          onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.opacity = '0.8' }}
          onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.opacity = '1' }}
        >
          <i
            className={`fa-solid ${theme === 'dark' ? 'fa-sun' : 'fa-moon'}`}
            style={{ fontSize: '11px', flexShrink: 0 }}
          />
          <span>{theme === 'dark' ? 'Claro' : 'Oscuro'}</span>
        </button>

        {/* Logout */}
        <button
          onClick={logout}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
            padding: '8px', borderRadius: '9px', cursor: 'pointer', transition: 'all 0.15s',
            fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
            color: 'rgba(255,255,255,0.65)', background: 'transparent',
            border: '1px solid rgba(255,255,255,0.08)',
          }}
          onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.color = '#fb7185'; el.style.background = 'rgba(225,29,72,0.1)'; el.style.borderColor = 'rgba(244,63,94,0.3)'; }}
          onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.color = 'rgba(255,255,255,0.65)'; el.style.background = 'transparent'; el.style.borderColor = 'rgba(255,255,255,0.08)'; }}
        >
          <i className="fa-solid fa-right-from-bracket" style={{ fontSize: '10px' }} />
          <span>Cerrar sesión</span>
        </button>
      </div>
    </aside>
  )
}

// ── ICON RAIL (contraído) ───────────────────────────────────────
function IconRail({ items, logout }: { items: NavItem[]; logout: () => void }) {
  const { pathname } = useLocation()
  const { user, org, branch } = useAuthStore()
  const role = (user?.role ?? 'CAJERO') as Role
  const pendingReturns = usePendingReturnsCount(role)
  const initial = (user?.full_name || user?.username || 'U').charAt(0).toUpperCase()
  const orgInitial = (org?.name ?? 'A').charAt(0).toUpperCase()

  return (
    <aside style={{
      width: '72px', minWidth: '72px', height: '100vh',
      display: 'flex', flexDirection: 'column',
      background: 'var(--sb-bg)', borderRight: '1px solid rgba(255,255,255,0.06)',
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{
        height: '60px', display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0,
      }}>
        <div style={{
          width: '34px', height: '34px', borderRadius: '10px',
          background: 'var(--sb-logo-grad)',
          boxShadow: '0 0 12px var(--sb-glow)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <i className="fa fa-bolt" style={{ color: 'white', fontSize: '12px' }} />
        </div>
      </div>

      {/* Org/branch dots */}
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
        padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0,
      }}>
        <div title={org?.name ?? 'Organización'} style={{
          width: '28px', height: '28px', borderRadius: '7px',
          background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '10px', fontWeight: 800, color: '#818cf8',
        }}>
          {orgInitial}
        </div>
        {branch ? (
          <div title={branch.name} style={{
            width: '28px', height: '16px', borderRadius: '5px',
            background: 'rgba(52,211,153,0.1)', border: '1px solid rgba(52,211,153,0.2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i className="fa-solid fa-store" style={{ fontSize: '7px', color: '#34d399' }} />
          </div>
        ) : (
          <div title="HQ Global" style={{
            width: '28px', height: '16px', borderRadius: '5px',
            background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i className="fa-solid fa-globe" style={{ fontSize: '7px', color: '#fbbf24' }} />
          </div>
        )}
      </div>

      {/* Icon column */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '6px' }}>
        {items.map((item) => {
          const active = pathname === item.url || pathname.startsWith(item.url + '/')
          const showReturnsBadge = RETURNS_URLS.has(item.url) && pendingReturns > 0
          return (
            <Link
              key={item.url}
              to={item.url}
              title={`${item.label}${showReturnsBadge ? ` (${pendingReturns} pendientes)` : ''}`}
              style={{
                position: 'relative',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                height: '38px', borderRadius: '8px', marginBottom: '2px',
                textDecoration: 'none', transition: 'all 0.15s ease',
                background: active ? 'var(--sb-active-bg)' : 'transparent',
                borderLeft: `2px solid ${active ? 'var(--sb-active-icon)' : 'transparent'}`,
              }}
            >
              <i
                className={`fa-solid ${item.icon}`}
                style={{ fontSize: '14px', color: active ? 'var(--sb-active-icon)' : 'rgba(255,255,255,0.78)' }}
              />
              {showReturnsBadge && (
                <span style={{
                  position: 'absolute', top: '4px', right: '4px',
                  minWidth: '14px', height: '14px', padding: '0 3px',
                  borderRadius: '7px',
                  background: '#f59e0b', color: '#1c1917',
                  fontSize: '8px', fontWeight: 900,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {pendingReturns > 9 ? '9+' : pendingReturns}
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* Avatar + logout */}
      <div style={{
        borderTop: '1px solid rgba(255,255,255,0.06)', padding: '8px 6px', flexShrink: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
      }}>
        <div
          title={`${user?.full_name || user?.username} · ${user?.role}`}
          style={{
            width: '34px', height: '34px', borderRadius: '9px',
            background: 'var(--sb-logo-grad)',
            boxShadow: `0 0 8px ${ROLE_COLOR[role]}55`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '13px', fontWeight: 900, color: 'white',
          }}
        >
          {initial}
        </div>
        <button
          onClick={logout}
          title="Cerrar sesión"
          style={{
            width: '34px', height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: '7px', cursor: 'pointer', transition: 'all 0.15s',
            background: 'transparent', border: '1px solid rgba(255,255,255,0.08)',
            color: 'rgba(255,255,255,0.55)',
          }}
          onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.color = '#fb7185'; el.style.background = 'rgba(225,29,72,0.1)'; el.style.borderColor = 'rgba(244,63,94,0.3)'; }}
          onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.color = 'rgba(255,255,255,0.55)'; el.style.background = 'transparent'; el.style.borderColor = 'rgba(255,255,255,0.08)'; }}
        >
          <i className="fa-solid fa-right-from-bracket" style={{ fontSize: '11px' }} />
        </button>
      </div>
    </aside>
  )
}

// ── ROOT ────────────────────────────────────────────────────────
export function Sidebar({ collapsed = false }: { collapsed?: boolean }) {
  const { user, logout, isAuthenticated } = useAuthStore()
  const role = (user?.role ?? 'CAJERO') as Role
  const allowed = ROLE_ROUTES[role] ?? []

  // Module gating: items with `module` declared only appear when the org has
  // that module enabled. Items without `module` are always shown.
  const { enabledModules, preset, loaded, load } = useEnabledModulesStore()
  useEffect(() => {
    if (isAuthenticated && !loaded) load()
  }, [isAuthenticated, loaded, load])

  // El gating por módulo (y el fail-open mientras carga) vive en
  // `visibleNavItems`, que es pura y tiene pruebas.
  const isGastro = !!preset && GASTRO_PRESETS.has(preset)
  const items = visibleNavItems(ALL_NAV, { role, allowed, enabledModules, isGastro })

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

  if (collapsed) return <IconRail items={items} logout={handleLogout} />
  return <MatrixSidebar items={items} logout={handleLogout} isBranchRole={isBranchRole} />
}
