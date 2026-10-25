// frontend/src/pages/hq/InicioGraficas.tsx
import { useMemo } from 'react'
import type { Inicio as DatosInicio } from '../../api/reports'
import {
  GraficaBarras, GraficaDona, GraficaLinea, colorMetodo, etiquetaHora, recortarHoras, useTemaGrafica,
} from '../../components/graficas'
import { formatCurrency } from '../../utils/currency'

/**
 * Las cuatro gráficas del Inicio (spec 2026-10-23 §3.1). Vive aparte de
 * `Inicio.tsx` y se carga con `lazy()` SOLO en perfil completo: el chunk
 * `charts` (chart.js) no debe bajar en modo básico (PC viejas, SP2/SP6).
 * `Inicio.tsx` solo puede importar de aquí el tipo `SeccionGrafica`.
 */
export type SeccionGrafica = 'tendencia' | 'metodos' | 'horas' | 'sucursales'

const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']
/** "vie 17": a mediodía local para que la zona horaria no mueva el día. */
const diaCorto = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric' })

export function InicioGraficas({ seccion, datos, horaActual = new Date().getHours() }: {
  seccion: SeccionGrafica
  datos: DatosInicio
  /** Hora que se resalta en "horas"; por defecto la del reloj del navegador (supone un navegador en México: las horas del backend son de México). */
  horaActual?: number
}) {
  const tema = useTemaGrafica()
  const { tendencia, por_metodo_hoy: porMetodo, por_hora_hoy: porHora, sucursales } = datos

  // Los arreglos se memoizan para que los useMemo del kit no recalculen en cada render.
  const lineas = useMemo(() => tendencia && ({
    etiquetas: tendencia.dias.map((d) => diaCorto(d.fecha)),
    series: [
      { nombre: 'Estos 7 días', valores: tendencia.dias.map((d) => d.neta) },
      { nombre: 'Semana anterior', valores: tendencia.anterior.map((d) => d.neta), comparativo: true },
    ],
  }), [tendencia])

  const dona = useMemo(() => {
    const claves = [
      ...ORDEN_METODOS.filter((m) => m in porMetodo),
      ...Object.keys(porMetodo).filter((m) => !ORDEN_METODOS.includes(m)),
    ]
    const partes = claves.map((m) => ({ nombre: METODOS[m] ?? m, valor: porMetodo[m], color: colorMetodo(m, tema) }))
    return { partes, total: partes.reduce((s, p) => s + p.valor, 0) }
  }, [porMetodo, tema])

  const horas = useMemo(() => {
    if (!porHora) return null
    const { desde, hasta } = recortarHoras(porHora)
    // Por hora (no por índice): no depende de que el backend mande siempre las 24 en orden.
    const ventana = porHora.filter((h) => h.hora >= desde && h.hora <= hasta)
    return {
      etiquetas: ventana.map((h) => etiquetaHora(h.hora)),
      valores: ventana.map((h) => h.neta),
      indice: ventana.findIndex((h) => h.hora === horaActual),
    }
  }, [porHora, horaActual])

  const ranking = useMemo(() => {
    const lista = [...(sucursales ?? [])].sort((a, b) => b.ventas_hoy - a.ventas_hoy)
    return { etiquetas: lista.map((s) => s.nombre), valores: lista.map((s) => s.ventas_hoy) }
  }, [sucursales])

  if (seccion === 'tendencia') {
    if (!lineas) return null
    return <GraficaLinea etiquetas={lineas.etiquetas} series={lineas.series} ariaLabel="Venta de los últimos 7 días contra la semana anterior" />
  }

  if (seccion === 'metodos') {
    return (
      <GraficaDona
        partes={dona.partes}
        alto={200}
        ariaLabel="Cobros de hoy por método de pago"
        centro={(
          <>
            <span className="dax-kpi-label">Hoy</span>
            <span className="text-base font-black tabular-nums text-dax-text">{formatCurrency(dona.total)}</span>
          </>
        )}
      />
    )
  }

  if (seccion === 'horas') {
    if (!horas) return null
    return (
      <GraficaBarras
        etiquetas={horas.etiquetas}
        valores={horas.valores}
        resaltar={horas.indice >= 0 ? horas.indice : null}
        alto={200}
        nombre="Venta de hoy"
        ariaLabel="Venta de hoy por hora"
      />
    )
  }

  return (
    <GraficaBarras
      etiquetas={ranking.etiquetas}
      valores={ranking.valores}
      horizontal
      alto={Math.max(120, 36 * ranking.etiquetas.length + 40)}
      nombre="Venta de hoy"
      ariaLabel="Venta de hoy por sucursal"
    />
  )
}
