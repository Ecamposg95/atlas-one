// frontend/src/components/graficas/registro.ts
import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, LineElement, LinearScale, PointElement, Tooltip,
} from 'chart.js'

/**
 * Registración única de chart.js para el kit. Sin `Legend` (la leyenda la
 * pinta cada pantalla con tokens) y sin `Filler` (spec §3.3: sin relleno ni
 * degradados). Importar este módulo basta; `register` es idempotente.
 */
ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, Tooltip)
