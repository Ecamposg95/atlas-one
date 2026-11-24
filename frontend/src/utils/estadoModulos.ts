/**
 * Estado de construcción de los módulos: qué NO se muestra todavía.
 *
 * La fuente es `app/services/estado_modulos.py`; el servidor lo manda en
 * `/users/me/context` (`modulos_no_disponibles`). Este espejo cubre el rato en
 * que el contexto aún no carga (o falló) para que el menú no enseñe, ni un
 * instante, una pantalla que no existe. `__tests__/estadoModulos.test.ts`
 * compara el espejo con el archivo de Python: si cambias uno, cambia el otro.
 *
 * Solo esconde. Nada se apaga: un módulo encendido sigue encendido en la base.
 * Para destapar uno terminado: CLAUDE.md §5 «Destapar un módulo».
 */
export type EstadoModulo = 'disponible' | 'en_construccion' | 'oculto'

export type ModulosNoDisponibles = Readonly<Record<string, EstadoModulo>>

export const NO_DISPONIBLES: ModulosNoDisponibles = {
  promotions: 'oculto',
  warehouse: 'en_construccion',
  invoicing: 'en_construccion',
  commissions: 'oculto',
  memberships: 'oculto',
  ai: 'en_construccion',
  appointments: 'en_construccion',
  workshops: 'oculto',
  manufacturing: 'oculto',
  kds: 'oculto',
  work_orders: 'oculto',
}

/** Lo que mandó el servidor si tiene forma de mapa; si no (servidor viejo, error), el espejo. */
export function leerNoDisponibles(crudo: unknown): ModulosNoDisponibles {
  if (!crudo || typeof crudo !== 'object' || Array.isArray(crudo)) return NO_DISPONIBLES
  const mapa: Record<string, EstadoModulo> = {}
  for (const [clave, estado] of Object.entries(crudo as Record<string, unknown>)) {
    if (estado === 'en_construccion' || estado === 'oculto') mapa[clave] = estado
  }
  return mapa
}

export function estadoModulo(
  clave: string,
  noDisponibles: ModulosNoDisponibles = NO_DISPONIBLES,
): EstadoModulo {
  return noDisponibles[clave] ?? 'disponible'
}

/** Sin clave (pantalla que no depende de un módulo) siempre se muestra. */
export function moduloDisponible(
  clave: string | undefined,
  noDisponibles: ModulosNoDisponibles = NO_DISPONIBLES,
): boolean {
  return !clave || estadoModulo(clave, noDisponibles) === 'disponible'
}

/** Cómo lo rotula la plataforma (el superadministrador sí lo ve). */
export const ROTULO_ESTADO: Record<Exclude<EstadoModulo, 'disponible'>, string> = {
  en_construccion: 'En construcción',
  oculto: 'No construido',
}

/**
 * Marca para las pantallas de plataforma: `null` si el módulo está disponible.
 * Prefiere el `estado` que mandó el servidor; sin él, el espejo.
 */
export function rotuloNoDisponible(clave: string, estado?: string | null): string | null {
  const e = estado === 'disponible' || estado === 'en_construccion' || estado === 'oculto' ? estado : estadoModulo(clave)
  return e === 'disponible' ? null : ROTULO_ESTADO[e]
}
