import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ALL_NAV, HQ_NAV_GROUPS, BRANCH_NAV_GROUPS, ROLE_ROUTES } from '../components/layout/navConfig'
import { visibleNavItems } from '../components/layout/navVisibility'
import { NO_DISPONIBLES, estadoModulo, leerNoDisponibles, moduloDisponible, rotuloNoDisponible } from '../utils/estadoModulos'
import type { Role } from '../types/auth'

/**
 * Módulos sin construir (decisión 2026-11-24): se esconden hasta que existan.
 * La fuente es `app/services/estado_modulos.py`; esta guardia amarra a ella el
 * espejo del frontend, el menú y las rutas de App.tsx.
 */
const raiz = resolve(__dirname, '..')
const src = (p: string) => readFileSync(resolve(raiz, p), 'utf8')
const PYTHON = resolve(raiz, '../../app/services/estado_modulos.py')

/** `{clave: estado}` leído del archivo de Python (una línea `"clave": ESTADO,` por módulo). */
function estadosDelServidor(): Record<string, string> {
  const texto = readFileSync(PYTHON, 'utf8')
  const mapa: Record<string, string> = {}
  for (const m of texto.matchAll(/^\s*"([a-z_]+)":\s*(DISPONIBLE|EN_CONSTRUCCION|OCULTO),/gm)) {
    mapa[m[1]] = m[2].toLowerCase()
  }
  return mapa
}

const ESTADOS = estadosDelServidor()
const TODOS = Object.keys(ESTADOS)

/** Ruta `<Route path="x" element={…} />` de App.tsx → texto de su elemento. */
function rutasDeApp(): { path: string; elemento: string }[] {
  const app = src('App.tsx')
  return [...app.matchAll(/<Route\s+path="([^"]+)"\s+element=\{([\s\S]*?)\}\s*\/>/g)]
    .map((m) => ({ path: m[1], elemento: m[2] }))
}

describe('el espejo del frontend es igual a la fuente del servidor', () => {
  it('el archivo de Python se puede leer y declara módulos', () => {
    expect(TODOS.length).toBeGreaterThan(30)
    expect(ESTADOS.pos).toBe('disponible')
  })

  it('NO_DISPONIBLES tiene exactamente lo que el servidor declara no disponible', () => {
    const delServidor = Object.fromEntries(Object.entries(ESTADOS).filter(([, e]) => e !== 'disponible'))
    expect({ ...NO_DISPONIBLES }).toEqual(delServidor)
  })
})

describe('el menú no enseña módulos sin construir', () => {
  it('todo módulo que el menú exige tiene estado declarado', () => {
    for (const n of ALL_NAV) {
      for (const clave of [n.module, n.branchModule]) {
        if (clave) expect(TODOS, `${n.url} exige ${clave}`).toContain(clave)
      }
    }
  })

  it('con TODOS los módulos encendidos, ningún rol ve un ítem de un módulo no disponible', () => {
    for (const role of Object.keys(ROLE_ROUTES) as Role[]) {
      const items = visibleNavItems(ALL_NAV, { role, allowed: ROLE_ROUTES[role], enabledModules: TODOS, isGastro: false })
      for (const n of items) {
        if (n.module) expect(estadoModulo(n.module), `${role} ve ${n.url} (${n.module})`).toBe('disponible')
      }
    }
  })

  it('tampoco mientras el contexto no ha cargado (enabledModules vacío no abre esta puerta)', () => {
    const urls = visibleNavItems(ALL_NAV, {
      role: 'ADMINISTRADOR', allowed: ROLE_ROUTES.ADMINISTRADOR, enabledModules: [], isGastro: false,
    }).map((n) => n.url)
    for (const u of ['/appointments', '/commissions', '/memberships', '/ai']) expect(urls).not.toContain(u)
    expect(urls).toContain('/quotes') // lo construido sí falla abierto
  })

  it('el mapa que manda el servidor manda sobre el espejo: al destapar un módulo, reaparece', () => {
    const { appointments: _fuera, ...resto } = NO_DISPONIBLES
    const urls = visibleNavItems(ALL_NAV, {
      role: 'ADMINISTRADOR', allowed: ROLE_ROUTES.ADMINISTRADOR, enabledModules: TODOS, isGastro: false,
      noDisponibles: resto,
    }).map((n) => n.url)
    expect(urls).toContain('/appointments')
    expect(urls).not.toContain('/commissions')
  })

  it('una organización que ya tenía encendido un módulo sin construir solo deja de verlo', () => {
    const urls = visibleNavItems(ALL_NAV, {
      role: 'DUEÑO', allowed: ROLE_ROUTES.DUEÑO, isGastro: false,
      enabledModules: ['core', 'pos', 'crm', 'commissions', 'memberships', 'appointments', 'ai'],
    }).map((n) => n.url)
    expect(urls).toContain('/customers')
    for (const u of ['/appointments', '/commissions', '/memberships', '/ai']) expect(urls).not.toContain(u)
  })
})

describe('App.tsx no pinta "Próximamente"', () => {
  const rutas = rutasDeApp()
  const moduloDeUrl = new Map(ALL_NAV.filter((n) => n.module).map((n) => [n.url, n.module as string]))

  it('se leyeron las rutas', () => {
    expect(rutas.length).toBeGreaterThan(40)
    expect(rutas.map((r) => r.path)).toEqual(expect.arrayContaining(['appointments', 'ai', 'quotes']))
  })

  it('ninguna ruta sirve un componente ComingSoon para un módulo disponible', () => {
    for (const r of rutas) {
      if (!/ComingSoon|Proximamente|Próximamente/.test(r.elemento)) continue
      const modulo = moduloDeUrl.get('/' + r.path)
      // Una pantalla de relleno tiene que colgar de un módulo declarado no disponible.
      expect(modulo, `la ruta /${r.path} pinta un relleno sin módulo en ALL_NAV`).toBeTruthy()
      expect(estadoModulo(modulo!), `/${r.path} pinta un relleno pero ${modulo} está disponible`).not.toBe('disponible')
    }
  })

  it('las rutas de módulos sin construir mandan al inicio del rol', () => {
    for (const [url, modulo] of moduloDeUrl) {
      if (moduloDisponible(modulo)) continue
      const r = rutas.find((x) => '/' + x.path === url)
      expect(r, url).toBeTruthy()
      expect(r!.elemento.trim(), url).toBe('<Navigate to="/" replace />')
    }
  })

  it('las páginas de relleno se borraron y /purchasing cae en la pantalla real de Compras', () => {
    expect(existsSync(resolve(raiz, 'pages/coming-soon/index.tsx'))).toBe(false)
    expect(existsSync(resolve(raiz, 'components/ComingSoon.tsx'))).toBe(false)
    expect(src('App.tsx')).not.toMatch(/ComingSoon|coming-soon/)
    expect(src('App.tsx')).toMatch(/path="purchasing"\s+element=\{<RedirigirConQuery a="\/purchases" \/>\}/)
    const grupos = [...HQ_NAV_GROUPS, ...BRANCH_NAV_GROUPS].flatMap((g) => g.urls)
    expect(ALL_NAV.map((n) => n.url)).not.toContain('/purchasing')
    expect(grupos).not.toContain('/purchasing')
    expect(Object.values(ROLE_ROUTES).flat()).not.toContain('/purchasing')
  })
})

describe('lectura tolerante', () => {
  it('servidor viejo (sin el campo) o respuesta rara: se usa el espejo', () => {
    expect(leerNoDisponibles(undefined)).toBe(NO_DISPONIBLES)
    expect(leerNoDisponibles(null)).toBe(NO_DISPONIBLES)
    expect(leerNoDisponibles(['ai'])).toBe(NO_DISPONIBLES)
  })

  it('un mapa del servidor se respeta, descartando estados que no esconden', () => {
    expect(leerNoDisponibles({ ai: 'en_construccion', pos: 'disponible', x: 7 })).toEqual({ ai: 'en_construccion' })
    expect(leerNoDisponibles({})).toEqual({})
  })

  it('la plataforma rotula lo no disponible y calla lo disponible', () => {
    expect(rotuloNoDisponible('pos')).toBeNull()
    expect(rotuloNoDisponible('commissions')).toBe('No construido')
    expect(rotuloNoDisponible('appointments')).toBe('En construcción')
    expect(rotuloNoDisponible('commissions', 'disponible')).toBeNull() // el servidor manda
    expect(moduloDisponible(undefined)).toBe(true)
  })
})
