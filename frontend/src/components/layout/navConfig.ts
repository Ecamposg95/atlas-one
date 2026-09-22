import type { Role } from '../../types/auth'
import type { NavItem } from './navVisibility'

// Catálogo de navegación: una sola fuente para el menú lateral, el título de
// la barra superior y las guardas de rol de `App.tsx`. Vive en un `.ts` puro
// (sin JSX) para que vitest pueda probarlo — `Sidebar.tsx` solo lo pinta.

// Presets gastronómicos (valor de `preset` = industry_type de la org). En estos
// verticales ocultamos los ítems marcados `hideForGastro` (lenguaje retail que
// no aplica a una cocina). Incluye taxonomía v2 (ATLAS_ONE_*) y v1 legacy.
export const GASTRO_PRESETS = new Set([
  'ATLAS_ONE_RESTAURANT', 'ATLAS_ONE_CAFE', 'ATLAS_ONE_BAR', 'ATLAS_ONE_GASTRO',
  'RESTAURANT_FULL', 'RESTAURANT_QSR', 'CAFE_BAKERY',
])

// Grupos del menú de sucursal (cajera/gerente). Lo que no cae en ningún grupo
// termina en "Más" — antes se descartaba en silencio y dejaba sin enlace a
// Devoluciones y Recetas (audit-funcional #15).
export const BRANCH_NAV_GROUPS: { header: string; urls: string[] }[] = [
  { header: 'Mi día',        urls: ['/atlas-pos', '/pos'] },
  { header: 'Restaurante',   urls: ['/menu', '/tables', '/mobile/comanda', '/kitchen', '/bar/bottles'] },
  { header: 'Mi turno',      urls: ['/cash-history', '/sales'] },
  { header: 'Inventario',    urls: ['/products', '/scanner', '/labels'] },
  { header: 'Reportes',      urls: ['/reports', '/meseros'] },
  { header: 'Configuración', urls: ['/printer-settings'] },
]

// Grupos del menú HQ/admin. Los items no listados caen en "Más" (no se ocultan).
// "Mi tienda" va primero: en una tienda de una sola sucursal, cobrar, ver los
// tickets del día, el catálogo, las etiquetas y la impresora son el trabajo
// diario de la dueña, y antes no tenían ninguna entrada en su menú.
export const HQ_NAV_GROUPS: { header: string; urls: string[] }[] = [
  { header: 'Mi tienda',    urls: ['/pos', '/sales', '/products', '/labels', '/printer-settings'] },
  { header: 'Caja',         urls: ['/cash-history'] },
  { header: 'Restaurante',  urls: ['/menu', '/tables', '/mobile/comanda', '/kitchen', '/recipes', '/meseros', '/bar/bottles'] },
  { header: 'Operación',    urls: ['/hq/operations', '/hq/reports-hub', '/hq/control'] },
  { header: 'Catálogo',     urls: ['/admin/catalog', '/departments', '/brands'] },
  { header: 'Inventario',   urls: ['/inventory', '/hq/inventory', '/boxes', '/logistics', '/scanner'] },
  { header: 'Ventas',       urls: ['/hq/sales', '/hq/returns', '/quotes', '/quotes/new', '/seguimiento'] },
  { header: 'Compras',      urls: ['/purchases', '/expenses', '/purchasing'] },
  { header: 'Clientes',     urls: ['/customers', '/appointments', '/commissions', '/memberships'] },
  { header: 'Organización', urls: ['/organization', '/hq/branches', '/users', '/hr'] },
  { header: 'Inteligencia', urls: ['/ai'] },
  { header: 'Móvil',        urls: ['/mobile/owner'] },
]

// Color de acento por grupo — identidad de módulo en el sidebar. El ícono se
// tiñe con el color del grupo; el ítem activo lo usa para el riel lateral, el
// resplandor y el relleno suave. Los encabezados de sección y las etiquetas
// inactivas se quedan neutros. Los matices viven en index.css (--sb-mod-*),
// no como hex sueltos aquí.
export const GROUP_COLOR: Record<string, string> = {
  // Grupos HQ (admin)
  'Mi tienda': 'var(--sb-mod-violet)', 'Caja': 'var(--sb-mod-green)',
  'Operación': 'var(--sb-mod-violet)', 'Catálogo': 'var(--sb-mod-green)',
  'Ventas': 'var(--sb-mod-blue)', 'Inventario': 'var(--sb-mod-amber)',
  'Compras': 'var(--sb-mod-teal)', 'Clientes': 'var(--sb-mod-rose)',
  'Organización': 'var(--sb-mod-cyan)', 'Inteligencia': 'var(--sb-mod-indigo)',
  'Restaurante': 'var(--sb-mod-orange)', 'Más': 'var(--sb-mod-slate)',
  'Móvil': 'var(--sb-mod-blue)',
  // Grupos de sucursal
  'Mi día': 'var(--sb-mod-violet)', 'Mi turno': 'var(--sb-mod-green)',
  'Reportes': 'var(--sb-mod-indigo)', 'Configuración': 'var(--sb-mod-slate)',
}
export const DEFAULT_GROUP_COLOR = 'var(--sb-mod-violet)'

/** url → color del grupo, para el IconRail contraído (que no tiene secciones). */
export const URL_COLOR: Record<string, string> = {}
for (const _g of [...HQ_NAV_GROUPS, ...BRANCH_NAV_GROUPS]) {
  const _c = GROUP_COLOR[_g.header] ?? DEFAULT_GROUP_COLOR
  for (const _u of _g.urls) if (!(_u in URL_COLOR)) URL_COLOR[_u] = _c
}

// Glosario: una pantalla, un nombre. La etiqueta de esta tabla es la que se ve
// en el menú, en la barra superior (`routeTitle`) y en el `<h1>` de la página.
// Sin "HQ" ni "Global": para una tienda de una sucursal, HQ y sucursal son el
// mismo lugar, y para una cadena el selector de sucursal ya dice dónde estás.
export const ALL_NAV: NavItem[] = [
  { label: 'Inicio',            short: 'OPS', icon: 'fa-gauge-high',          url: '/hq/operations',    group: 'hq',   sort: 0  },
  { label: 'Reportes',          short: 'REP', icon: 'fa-chart-line',          url: '/hq/reports-hub',   group: 'hq',   sort: 1  },
  { label: 'Control',           short: 'CTL', icon: 'fa-sliders',             url: '/hq/control',       group: 'hq',   sort: 2  },
  { label: 'Catálogo',          short: 'CAT', icon: 'fa-book',                url: '/admin/catalog',    group: 'hq',   sort: 3,  module: 'catalog' },
  { label: 'Departamentos',     short: 'DEP', icon: 'fa-layer-group',         url: '/departments',      group: 'hq',   sort: 4,  module: 'catalog', hideForGastro: true },
  { label: 'Marcas',            short: 'MRC', icon: 'fa-tags',                url: '/brands',           group: 'hq',   sort: 5,  module: 'catalog', hideForGastro: true },
  { label: 'Ventas',            short: 'VTA', icon: 'fa-receipt',             url: '/hq/sales',         group: 'hq',   sort: 6,  module: 'pos' },
  { label: 'Devoluciones',      short: 'DEV', icon: 'fa-undo',                url: '/hq/returns',       group: 'hq',   sort: 7,  module: 'returns' },
  { label: 'Cotizaciones',      short: 'COT', icon: 'fa-file-invoice',        url: '/quotes',           group: 'hq',   sort: 8,  module: 'quotes' },
  { label: 'Nueva cotización',  short: 'NEW', icon: 'fa-file-invoice-dollar', url: '/quotes/new',       group: 'hq',   sort: 9,  module: 'quotes' },
  { label: 'Pedidos',           short: 'PED', icon: 'fa-clipboard-check',     url: '/seguimiento',      group: 'hq',   sort: 10, module: 'quotes' },
  // Compras, Gastos y RRHH son de otros giros: sin `module` se colaban en el
  // menú de una boutique, que no tiene ninguno de los tres en su preset.
  { label: 'Compras',           short: 'CMP', icon: 'fa-shopping-cart',       url: '/purchases',        group: 'hq',   sort: 11, module: 'purchasing' },
  { label: 'Gastos',            short: 'GST', icon: 'fa-money-bill-wave',     url: '/expenses',         group: 'hq',   sort: 12, module: 'finance' },
  { label: 'Inventario',        short: 'INV', icon: 'fa-boxes',               url: '/inventory',        group: 'hq',   sort: 13, module: 'inventory' },
  { label: 'Escáner',           short: 'SCN', icon: 'fa-barcode',             url: '/scanner',          group: 'hq',   sort: 13.5, module: 'inventory', branchModule: 'scanner' },
  { label: 'Etiquetas',         short: 'ETQ', icon: 'fa-tag',                 url: '/labels',           group: 'hq',   sort: 13.6, module: 'labels' },
  { label: 'Existencias',       short: 'EXI', icon: 'fa-globe',               url: '/hq/inventory',     group: 'hq',   sort: 14, module: 'inventory', hideForGastro: true },
  { label: 'Logística',         short: 'LOG', icon: 'fa-truck-loading',       url: '/logistics',        group: 'hq',   sort: 15, module: 'logistics' },
  { label: 'Cajas y contenedores', short: 'CJA', icon: 'fa-box-open',         url: '/boxes',            group: 'hq',   sort: 16, module: 'logistics' },
  { label: 'Clientes',          short: 'CRM', icon: 'fa-address-book',        url: '/customers',        group: 'hq',   sort: 17, module: 'crm' },
  { label: 'Empresa',           short: 'EMP', icon: 'fa-building',            url: '/organization',     group: 'hq',   sort: 18 },
  { label: 'Sucursales',        short: 'SCR', icon: 'fa-store',               url: '/hq/branches',      group: 'hq',   sort: 19 },
  { label: 'Usuarios',          short: 'USR', icon: 'fa-users-cog',           url: '/users',            group: 'hq',   sort: 20 },
  { label: 'Recursos Humanos',  short: 'HR',  icon: 'fa-user-tie',            url: '/hr',               group: 'hq',   sort: 21, module: 'hr' },
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
  { label: 'Mi día',            short: 'INI', icon: 'fa-house',               url: '/atlas-pos',        group: 'pos',  sort: 0  },
  { label: 'Cobrar',            short: 'POS', icon: 'fa-cash-register',       url: '/pos',              group: 'pos',  sort: 1  },
  { label: 'Mis ventas',        short: 'HST', icon: 'fa-history',             url: '/sales',            group: 'pos',  sort: 2  },
  { label: 'Corte de caja',     short: 'CRT', icon: 'fa-vault',               url: '/cash-history',     group: 'pos',  sort: 3  },
  { label: 'Devoluciones',      short: 'DEV', icon: 'fa-undo',                url: '/returns',          group: 'pos',  sort: 4  },
  { label: 'Productos',         short: 'PRD', icon: 'fa-barcode',             url: '/products',         group: 'pos',  sort: 5  },
  { label: 'Reportes',          short: 'REP', icon: 'fa-chart-pie',           url: '/reports',          group: 'pos',  sort: 6  },
  { label: 'Impresora',         short: 'IMP', icon: 'fa-print',               url: '/printer-settings', group: 'pos',  sort: 7  },
  { label: 'Mi expediente',     short: 'YO',  icon: 'fa-id-card',             url: '/hr/me',            group: 'pos',  sort: 8  },
  // Vuelta al armazón móvil para dueño/admin. Sin este enlace, quien entra
  // al escritorio desde la pestaña «Más» del móvil se queda sin camino de
  // regreso salvo escribiendo la URL (admin-findings I-10).
  { label: 'Resumen móvil',     short: 'RSM', icon: 'fa-mobile-screen-button', url: '/mobile/owner',    group: 'mob',  sort: -1 },
  { label: 'Dashboard móvil',   short: 'DSH', icon: 'fa-mobile-screen',       url: '/mobile/dashboard', group: 'mob',  sort: 0  },
  { label: 'Consulta móvil',    short: 'QRY', icon: 'fa-mobile-alt',          url: '/mobile/query',     group: 'mob',  sort: 1  },
  { label: 'Cotización móvil',  short: 'COT', icon: 'fa-file-invoice',        url: '/mobile/sales',     group: 'mob',  sort: 2  },
  { label: 'Perfil móvil',      short: 'PRF', icon: 'fa-user-circle',         url: '/mobile/profile',   group: 'mob',  sort: 3  },
]

export const ROLE_ROUTES: Record<Role, string[]> = {
  // `/pos`, `/sales`, `/products` y `/printer-settings` entran al menú del
  // admin: sin ellos la dueña no podía cobrar, reimprimir un ticket, ver su
  // catálogo completo ni configurar la impresora desde su propia cuenta.
  ADMINISTRADOR:    ['/pos','/sales','/products','/printer-settings','/labels','/mobile/owner','/cash-history','/hq/operations','/hq/reports-hub','/hq/control','/admin/catalog','/scanner','/departments','/organization','/users','/customers','/hq/branches','/hq/inventory','/hq/sales','/hq/returns','/brands','/hr','/hr/me','/logistics','/boxes','/quotes','/quotes/new','/seguimiento','/purchases','/expenses','/appointments','/commissions','/memberships','/recipes','/ai','/purchasing','/tables','/kitchen','/meseros','/bar/bottles','/menu','/mobile/comanda'],
  DUEÑO:            ['/pos','/sales','/products','/printer-settings','/labels','/mobile/owner','/cash-history','/hq/operations','/hq/reports-hub','/hq/control','/admin/catalog','/scanner','/customers','/hq/sales','/hq/returns','/hr/me','/logistics','/boxes','/quotes','/quotes/new','/seguimiento','/purchases','/expenses','/appointments','/commissions','/memberships','/recipes','/ai','/purchasing','/tables','/kitchen','/meseros','/bar/bottles','/menu','/mobile/comanda'],
  GERENTE:          ['/labels','/cash-history','/reports','/hr/me','/products','/scanner','/pos','/sales','/returns','/atlas-pos','/tables','/kitchen','/recipes','/meseros','/bar/bottles','/menu','/mobile/comanda'],
  CAJERO:           ['/labels','/pos','/cash-history','/hr/me','/products','/scanner','/printer-settings','/sales','/returns','/atlas-pos','/tables','/kitchen','/bar/bottles','/menu','/mobile/comanda'],
  VENDEDOR:         ['/mobile/dashboard','/mobile/query','/mobile/sales','/mobile/profile','/hr/me','/atlas-pos'],
  SOPORTE_OPERATIVO:['/mobile/dashboard','/mobile/query','/mobile/profile','/hr/me','/atlas-pos'],
  CLIENTE:          ['/portal'],
}

const ALL_ROLES = Object.keys(ROLE_ROUTES) as Role[]

/**
 * Roles que pueden ABRIR una ruta. Se deriva de `ROLE_ROUTES` (la misma lista
 * que dibuja el menú) para que no haya dos verdades: si una pantalla no está
 * en tu menú, tampoco la abres escribiendo la URL.
 *
 * Única excepción: DUEÑO hereda el permiso de ADMINISTRADOR. El menú del dueño
 * es deliberadamente corto, pero sigue siendo el dueño del negocio y hoy puede
 * entrar a Usuarios o Empresa por URL; quitárselo sería una regresión.
 */
export function rolesConAcceso(url: string): Role[] {
  const roles = ALL_ROLES.filter((r) => ROLE_ROUTES[r].includes(url))
  if (roles.includes('ADMINISTRADOR') && !roles.includes('DUEÑO')) roles.push('DUEÑO')
  return roles
}

/** Título de la barra superior, derivado del mismo `NavItem` que pinta el menú. */
export const ROUTE_TITLES: Record<string, string> = Object.fromEntries(
  ALL_NAV.map((n) => [n.url, n.label]),
)

/** Rutas sin entrada de menú propia que aun así necesitan un título. */
const EXTRA_TITLES: Record<string, string> = {
  '/home': 'Inicio',
  '/startup': 'Puesta en marcha',
  '/admin/products/new': 'Nuevo producto',
}

/**
 * Nombre de la pantalla para una URL. Coincidencia exacta y, si no, el ítem
 * más específico del que la URL cuelga (`/products/12/edit` → Productos).
 */
export function routeTitle(pathname: string): string {
  const exact = ROUTE_TITLES[pathname] ?? EXTRA_TITLES[pathname]
  if (exact) return exact
  const tabla = { ...ROUTE_TITLES, ...EXTRA_TITLES }
  const prefijo = Object.keys(tabla)
    .filter((k) => k.length > 1 && pathname.startsWith(k + '/'))
    .sort((a, b) => b.length - a.length)[0]
  return prefijo ? tabla[prefijo] : 'Atlas One'
}
