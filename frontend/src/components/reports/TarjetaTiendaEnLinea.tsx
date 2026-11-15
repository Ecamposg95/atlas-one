import { useEffect, useState } from 'react'
import { reportsApi, type TiendaEnLinea } from '../../api/reports'
import { DaxCard } from '../ui/DaxCard'

/**
 * Tarjeta «Tienda en línea» de Reportes: las piezas más consultadas del periodo
 * (clics de WhatsApp y selecciones de la web) y cuántos prospectos dejaron su
 * teléfono. Solo se monta cuando la org tiene el módulo `tienda_en_linea`.
 * Solo tokens `dax-*`.
 */
export function TarjetaTiendaEnLinea({ desde, hasta }: { desde: string; hasta: string }) {
  const [datos, setDatos] = useState<TiendaEnLinea | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let vigente = true
    setError(false)
    reportsApi.tiendaEnLinea({ desde, hasta })
      .then((d) => { if (vigente) setDatos(d) })
      .catch(() => { if (vigente) setError(true) })
    return () => { vigente = false }
  }, [desde, hasta])

  return (
    <DaxCard>
      <div data-testid="tienda-en-linea">
        <div className="flex items-baseline justify-between gap-2 mb-3">
          <p className="dax-section-title">Tienda en línea</p>
          {datos && (
            <p className="text-xs text-dax-faint" data-testid="prospectos">
              {datos.prospectos} {datos.prospectos === 1 ? 'prospecto' : 'prospectos'}
            </p>
          )}
        </div>
        {error ? (
          <p className="text-sm text-dax-danger">No se pudo cargar la tienda en línea.</p>
        ) : !datos ? (
          <p className="text-sm text-dax-faint">Cargando…</p>
        ) : datos.piezas.length === 0 ? (
          <p className="text-sm text-dax-muted">Sin consultas en el periodo.</p>
        ) : (
          <>
            <p className="dax-kpi-label mb-1">Piezas más consultadas</p>
            <ol className="space-y-1 text-sm">
              {datos.piezas.map((p, i) => (
                <li key={p.product_id} className="flex justify-between gap-2">
                  <span className="text-dax-muted">{i + 1}. {p.name}</span>
                  <span className="font-bold tabular-nums text-dax-text">{p.consultas}</span>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </DaxCard>
  )
}
