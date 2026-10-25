// frontend/src/components/graficas/index.ts
// Kit de gráficas (spec 2026-10-23 §3.3): envoltorios planos de react-chartjs-2
// pintados con los tokens del tema. Quien lo importa cae en el chunk `charts`:
// el Inicio solo lo alcanza con lazy() y en perfil completo.
export { GraficaLinea, type SerieLinea } from './GraficaLinea'
export { GraficaBarras, type GraficaBarrasProps } from './GraficaBarras'
export { GraficaDona, type ParteDona } from './GraficaDona'
export { useTemaGrafica, leerTemaGrafica, colorMetodo, type TemaGrafica } from './tema'
export { dineroCorto, recortarHoras, etiquetaHora } from './formato'
