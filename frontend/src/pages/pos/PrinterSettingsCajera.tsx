import { useCallback, useEffect, useState } from 'react'
import client from '../../api/client'
import { AGENT_BASE, printerApi } from '../../api/printer'
import { AgentDiagnosticsPanel } from '../../components/pos/AgentDiagnosticsPanel'
import { DaxCard } from '../../components/ui/DaxCard'
import { useAuthStore } from '../../store/authStore'
import { usePOSStore } from '../../store/posStore'
import { toast } from '../../store/toastStore'

/**
 * Impresora — vista de la cajera.
 *
 * Solo hace tres cosas: dice si el agente de esta PC responde, deja elegir la
 * impresora de ESTA PC (se guarda en el navegador, `posStore.printerName`, que
 * es lo que el POS usa al cobrar) y manda un ticket de prueba. El ancho de
 * papel se muestra pero no se edita: el ticket real sale con el de la
 * sucursal (`_resolve_printer` en el servidor), y eso lo fija el
 * administrador en la pantalla completa. Nada de aquí escribe en la sucursal,
 * así que dos cajas de la misma tienda no se pisan la configuración.
 */
export function PrinterSettingsCajera() {
  const branch = useAuthStore((s) => s.branch)
  const printerName = usePOSStore((s) => s.printerName)
  const setPrinterName = usePOSStore((s) => s.setPrinterName)

  const [agentOnline, setAgentOnline] = useState<boolean | null>(null)
  const [impresoras, setImpresoras] = useState<string[]>([])
  const [anchoPapel, setAnchoPapel] = useState<number | null>(null)
  const [testing, setTesting] = useState(false)

  const cargar = useCallback(async () => {
    const [vivo, lista] = await Promise.all([printerApi.pingAgent(), printerApi.getLocalPrinters()])
    setAgentOnline(vivo)
    setImpresoras(lista)
  }, [])

  useEffect(() => { cargar() }, [cargar])

  useEffect(() => {
    if (!branch?.id) return
    client.get(`/branches/${branch.id}`)
      .then(({ data }) => setAnchoPapel(data?.paper_width_mm ?? null))
      .catch(() => setAnchoPapel(null))
  }, [branch?.id])

  const probar = async () => {
    if (!printerName) { toast.error('Elige tu impresora primero.'); return }
    setTesting(true)
    try {
      const b64 = await printerApi.testPrintBase64({ printerName, paperWidthMm: anchoPapel ?? undefined })
      if (!b64) throw new Error('Sin datos del servidor')
      await printerApi.printViaAgent(printerName, b64)
      toast.success('Ticket de prueba enviado.')
    } catch (e: unknown) {
      toast.error((e as Error).message ?? 'No se pudo imprimir.')
    } finally { setTesting(false) }
  }

  // La impresora recordada puede no estar ya en la lista (otra PC, cola
  // renombrada): se muestra igual para que la cajera vea qué tiene elegido.
  const opciones = printerName && !impresoras.includes(printerName) ? [printerName, ...impresoras] : impresoras

  return (
    <div className="space-y-5 p-1 max-w-2xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-print text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black" style={{ color: 'var(--dax-text)' }}>Impresora</h1>
          {branch && <span className="text-xs text-slate-400">{branch.name}</span>}
        </div>
        <div className="flex gap-2">
          <button onClick={cargar} className="dax-btn-secondary text-xs" title="Volver a buscar impresoras">
            <i className="fa-solid fa-rotate" /> Actualizar
          </button>
          <button onClick={probar} disabled={testing || !printerName || !agentOnline}
                  className="dax-btn-primary text-xs disabled:opacity-40">
            {testing ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-paper-plane" /> Probar</>}
          </button>
        </div>
      </div>

      <AgentDiagnosticsPanel />

      {agentOnline === false && (
        <a href={AGENT_BASE + '/health'} target="_blank" rel="noreferrer"
           className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold"
           style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.35)' }}>
          <i className="fa-solid fa-triangle-exclamation text-lg flex-shrink-0" />
          <span className="flex-1">
            <span className="font-black">El agente de impresión no responde en esta PC.</span> Si ya está abierto, haz clic
            aquí para aceptar el certificado y vuelve a esta página. Si no, avísale a tu administrador.
          </span>
          <i className="fa-solid fa-arrow-up-right-from-square text-xs flex-shrink-0" />
        </a>
      )}

      <DaxCard>
        <div className="p-4 space-y-3">
          <h2 className="text-sm font-black" style={{ color: 'var(--dax-text)' }}>Mi impresora</h2>
          <p className="text-xs text-slate-400">
            La que elijas se guarda solo en esta PC. Es la que usa el punto de venta al cobrar y al reimprimir.
          </p>
          {opciones.length === 0 ? (
            <p className="text-sm text-slate-400">
              {agentOnline ? 'El agente no encontró impresoras en esta PC.' : 'Sin agente no hay lista de impresoras.'}
            </p>
          ) : (
            <div className="space-y-1.5">
              {opciones.map((p) => (
                <label key={p} className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer"
                       style={{ background: p === printerName ? 'rgba(99,102,241,0.15)' : 'var(--dax-elevated)' }}>
                  <input type="radio" name="impresora" checked={p === printerName} onChange={() => setPrinterName(p)} />
                  <span className="text-sm" style={{ color: 'var(--dax-text)' }}>{p}</span>
                  {p === printerName && !impresoras.includes(p) && (
                    <span className="text-[10px] text-amber-400">no aparece en esta PC</span>
                  )}
                </label>
              ))}
            </div>
          )}
        </div>
      </DaxCard>

      <DaxCard>
        <div className="p-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-black" style={{ color: 'var(--dax-text)' }}>Papel</h2>
            <p className="text-xs text-slate-400">Lo define tu administrador para toda la sucursal.</p>
          </div>
          <span className="text-lg font-black" style={{ color: 'var(--dax-text)' }}>
            {anchoPapel ? `${anchoPapel} mm` : '—'}
          </span>
        </div>
      </DaxCard>
    </div>
  )
}
