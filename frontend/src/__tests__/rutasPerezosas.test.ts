// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'

// Cada módulo que App.tsx carga con lazy() tiene que seguir resolviendo: un
// import roto no lo ve tsc (la ruta es un string) y en producción se
// manifiesta como un "Cargando..." eterno. Aquí se importa igual que lo hace
// App.tsx y se comprueba que exporta el componente con ese nombre.
const PEREZOSOS: Record<string, () => Promise<Record<string, unknown>>> = {
  MobileLayout: () => import('../components/layout/MobileLayout'),
  NotFoundPage: () => import('../pages/NotFound'),
  // Fase 2 del admin: las gráficas del Inicio solo bajan en perfil completo.
  InicioGraficas: () => import('../pages/hq/InicioGraficas'),
  Reportes: () => import('../pages/reports/Reportes'),
  // Añadir aquí cada módulo que salga del chunk de entrada en esta tarea.
}

describe('módulos movidos a lazy() en SP2', () => {
  for (const [nombre, cargar] of Object.entries(PEREZOSOS)) {
    it(`${nombre} resuelve y exporta un componente`, async () => {
      const m = await cargar()
      expect(typeof m[nombre]).toBe('function')
    })
  }
})
