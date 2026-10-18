import { useMediaQuery } from './useMediaQuery'

/**
 * Ancho por debajo del cual el armazón de escritorio ya no cabe: el sidebar
 * pasa a ser cajón off-canvas. Corte en `lg` (1024), no en `md` (768).
 *
 * Por qué 1024 y no 768 (admin-findings I-11): a exactamente 768 px —iPad en
 * vertical, el tamaño de tablet del encargo— `esMovil` era `false`, así que la
 * barra lateral volvía al flujo con sus 244 px fijos y al contenido le
 * quedaban **524 px**: menos que a un teléfono en apaisado, y encima con todas
 * las rejillas `md:` ya activadas. Era el peor de los dos mundos.
 *
 * Se eligió subir el umbral en vez de añadir un tercer modo «sidebar
 * contraído entre 768 y 1024» porque es el cambio más pequeño y seguro: una
 * constante, ningún estado nuevo ni camino de render nuevo, y reutiliza el
 * cajón que ya existe y ya está probado (`utils/cajonLateral.ts`). El rail de
 * iconos contraído seguiría comiendo 72 px y habría que decidir qué pasa
 * cuando el usuario lo alterna a mano. En ≥ 1024 px nada cambia.
 */
const SHELL_BREAKPOINT = 1024 // Tailwind lg

/**
 * Ancho de teléfono. Se mantiene en `md` (768) porque decide el render
 * condicional tabla/tarjetas (`useEsTelefono`) y los cortes de maquetación del
 * kit, no el armazón. Desde la ola 1 del responsivo el dueño y el admin ya no
 * se desvían a `/mobile/owner` en teléfono: entran al escritorio adaptado y al
 * panel móvil llegan por el ítem «Resumen móvil» del menú.
 */
const PHONE_BREAKPOINT = 768 // Tailwind md

/** `true` cuando el armazón debe colapsar el sidebar en cajón (< 1024 px). */
export function useIsMobile(): boolean {
  return useMediaQuery(`(max-width: ${SHELL_BREAKPOINT - 1}px)`)
}

/** `true` en anchos de teléfono (< 768 px). Para el render tabla/tarjetas y los cortes del kit (< 768). */
export function useEsTelefono(): boolean {
  return useMediaQuery(`(max-width: ${PHONE_BREAKPOINT - 1}px)`)
}
