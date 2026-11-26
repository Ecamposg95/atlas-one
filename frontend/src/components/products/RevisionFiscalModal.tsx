import { useEffect, useState } from 'react'
import { productsApi, type RevisionFiscal } from '../../api/products'
import { Modal } from '../ui/Modal'

interface Props {
  open: boolean
  onClose: () => void
}

/**
 * Revisión fiscal del catálogo (solo lectura): cuántos productos de cada
 * sucursal no tienen tasa de IVA del SAT o la tienen en contradicción con
 * «Aplica IVA», y cuáles son las discrepancias. La lista completa sale en CSV
 * para repartirla a las tiendas. La regla vive en el backend
 * (`app/modules/products/services/revision_fiscal.py`).
 */
export function RevisionFiscalModal({ open, onClose }: Props) {
  const [datos, setDatos] = useState<RevisionFiscal | null>(null)
  const [error, setError] = useState(false)
  const [descargando, setDescargando] = useState(false)

  useEffect(() => {
    if (!open) return
    setDatos(null)
    setError(false)
    productsApi.revisionFiscal({ problema: 'DISCREPANCIA', limit: 100 })
      .then(setDatos)
      .catch(() => setError(true))
  }, [open])

  const descargar = async () => {
    setDescargando(true)
    try {
      await productsApi.downloadRevisionFiscalCsv()
    } catch {
      setError(true)
    } finally {
      setDescargando(false)
    }
  }

  const sinPendientes = datos !== null && datos.resumen.length === 0

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Revisión fiscal del catálogo"
      size="lg"
      footer={
        <>
          <button type="button" className="dax-btn-secondary" onClick={onClose}>Cerrar</button>
          {!sinPendientes && (
            <button type="button" className="dax-btn-primary" onClick={descargar} disabled={descargando || datos === null}>
              <i className={`fa-solid ${descargando ? 'fa-spinner fa-spin' : 'fa-file-csv'}`} aria-hidden="true" /> Descargar lista
            </button>
          )}
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <p className="text-dax-muted">
          La tasa de IVA de los datos fiscales decide el IVA de cada venta. Sin ella se supone 16 % incluido en el precio,
          y si contradice «Aplica IVA» el producto no se puede guardar hasta corregirlo.
        </p>
        {error && <p className="text-dax-danger">No se pudo cargar la revisión. Cierra y vuelve a intentar.</p>}
        {datos === null && !error && <p className="text-dax-muted">Cargando…</p>}
        {sinPendientes && (
          <p className="text-dax-text">Todos los productos tienen su tasa de IVA y coincide con «Aplica IVA».</p>
        )}
        {datos !== null && datos.resumen.length > 0 && (
          <div className="overflow-x-auto">
            <table className="dax-table">
              <thead>
                <tr><th>Sucursal</th><th className="text-right">Sin tasa de IVA</th><th className="text-right">Con discrepancia</th></tr>
              </thead>
              <tbody>
                {datos.resumen.map((r) => (
                  <tr key={r.branch_id ?? 'sin'}>
                    <td>{r.branch_name}</td>
                    <td className="text-right tabular-nums">{r.sin_clasificacion}</td>
                    <td className={`text-right tabular-nums ${r.con_discrepancia > 0 ? 'text-dax-danger' : ''}`}>{r.con_discrepancia}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {datos !== null && datos.items.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs uppercase tracking-wide text-dax-muted">Discrepancias por corregir</h3>
            <ul className="space-y-2">
              {datos.items.map((h) => (
                <li key={`${h.product_id}-${h.branch_id ?? 'sin'}`} className="border border-dax-border rounded-dax p-2">
                  <div className="text-dax-text">{h.producto} <span className="text-dax-muted font-mono text-xs">{h.sku}</span></div>
                  <div className="text-dax-muted text-xs">{h.branch_name} · {h.detalle}</div>
                </li>
              ))}
            </ul>
            {datos.total > datos.items.length && (
              <p className="text-dax-muted text-xs">Hay {datos.total} en total; la lista completa viene en el archivo.</p>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}
