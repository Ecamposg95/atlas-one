/**
 * A dónde va cada rol al entrar. Vive fuera de App.tsx para poder probarse:
 * vitest incluye los `.test.ts` y `.test.tsx` de `src/`.
 */
export function rutaInicioPorRol(
  rol?: string | null,
  esMovil = false,
  preset?: string | null,
): string {
  const esOficina = rol === 'ADMINISTRADOR' || rol === 'DUEÑO'
  // esMovil ya no desvía al dueño: desde la ola 1 del responsivo el escritorio cabe en teléfono.
  if (esOficina) {
    if (preset && preset.startsWith('ATLAS_ONE_')) return '/home'
    return '/hq/operations'
  }
  if (rol === 'VENDEDOR' || rol === 'SOPORTE_OPERATIVO') return '/mobile/dashboard'
  if (rol === 'CLIENTE') return '/portal'
  return '/atlas-pos'
}
