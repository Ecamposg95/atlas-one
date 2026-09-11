// Navegación del nivel SUPERADMIN. Vive fuera de PlatformLayout.tsx para
// poder probar la partición móvil (spec 2026-09-09 §3.2) sin renderizar.
export interface PlatformNavItem {
  label: string
  icon: string
  to: string
}

export const NAV_PLATFORM: PlatformNavItem[] = [
  { label: 'Dashboard',      icon: 'fa-gauge-high',              to: '/platform/metrics' },
  { label: 'Health',         icon: 'fa-heart-pulse',             to: '/platform/health' },
  { label: 'Alerts',         icon: 'fa-triangle-exclamation',    to: '/platform/alerts' },
  { label: 'Organizaciones', icon: 'fa-building',                to: '/platform/organizations' },
  { label: 'Usuarios',       icon: 'fa-users',                   to: '/platform/users' },
  { label: 'Sucursales',     icon: 'fa-store',                   to: '/platform/branches' },
  { label: 'Reportes',       icon: 'fa-chart-line',              to: '/platform/reportes' },
  { label: 'Cash Audit',     icon: 'fa-magnifying-glass-dollar', to: '/platform/cash-audit' },
]

export const NAV_ADMIN: PlatformNavItem[] = [
  { label: 'Presets',       icon: 'fa-layer-group',  to: '/platform/presets' },
  { label: 'Módulos',       icon: 'fa-puzzle-piece', to: '/platform/modules' },
  { label: 'Admins',        icon: 'fa-user-shield',  to: '/platform/admins' },
  { label: 'Announcements', icon: 'fa-bullhorn',     to: '/platform/announcements' },
  { label: 'Flags',         icon: 'fa-toggle-on',    to: '/platform/flags' },
  { label: 'Incidents',     icon: 'fa-fire',         to: '/platform/incidents' },
  { label: 'API keys',      icon: 'fa-key',          to: '/platform/api-keys' },
  { label: 'Audit Log',     icon: 'fa-scroll',       to: '/platform/audit' },
]

/** Las 4 entradas de la barra inferior en teléfono; el resto va en la hoja "Más". */
export const MOBILE_PRIMARY_PATHS = [
  '/platform/metrics',
  '/platform/reportes',
  '/platform/alerts',
  '/platform/cash-audit',
]

export function splitMobileNav(
  all: PlatformNavItem[],
  primaryPaths: string[],
): { primary: PlatformNavItem[]; rest: PlatformNavItem[] } {
  const byPath = new Map(all.map((i) => [i.to, i]))
  const primary = primaryPaths.map((p) => byPath.get(p)).filter((i): i is PlatformNavItem => Boolean(i))
  const primarySet = new Set(primary.map((i) => i.to))
  const rest = all.filter((i) => !primarySet.has(i.to))
  return { primary, rest }
}
