import { useEffect, useState } from 'react'
import { canalApi, type SucursalCanal } from '../../api/canal'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { toast } from '../../store/toastStore'

/** Configuración del canal «Tienda en línea»: qué sucursales que venden publican su existencia en la web. */
export function TiendaEnLinea() {
  const [cargando, setCargando] = useState(true)
  const [sucursales, setSucursales] = useState<SucursalCanal[]>([])
  const [todas, setTodas] = useState(true)
  const [elegidas, setElegidas] = useState<Set<number>>(new Set())
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    canalApi.getConfig()
      .then((c) => {
        setSucursales(c.sucursales.filter((s) => s.can_sell))
        setTodas(c.sucursales_web === null)
        setElegidas(new Set(c.sucursales_web ?? []))
      })
      .catch(() => toast.error('No se pudo cargar la configuración de la tienda en línea.'))
      .finally(() => setCargando(false))
  }, [])

  const alternar = (id: number) => setElegidas((prev) => {
    const sig = new Set(prev)
    if (sig.has(id)) sig.delete(id); else sig.add(id)
    return sig
  })

  const guardar = async () => {
    setGuardando(true)
    try {
      await canalApi.putConfig(todas ? null : sucursales.filter((s) => elegidas.has(s.id)).map((s) => s.id))
      toast.success('Configuración guardada.')
    } catch { toast.error('No se pudo guardar la configuración.') }
    finally { setGuardando(false) }
  }

  if (cargando) return <Spinner text="Cargando..." />
  return (
    <DaxCard>
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-black">Sucursales de la tienda en línea</h2>
          <p className="text-sm text-dax-muted">Elige de qué sucursales se toma la existencia que ve la tienda web.</p>
        </div>
        <label className="flex items-center gap-2 text-sm max-md:min-h-[44px]">
          <input type="checkbox" checked={todas} onChange={(e) => setTodas(e.target.checked)} />
          Todas las que venden
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {sucursales.map((s) => (
            <label key={s.id} className="flex items-center gap-2 text-sm max-md:min-h-[44px]">
              <input type="checkbox" disabled={todas} checked={todas || elegidas.has(s.id)} onChange={() => alternar(s.id)} />
              {s.name}
            </label>
          ))}
        </div>
        <button type="button" className="dax-btn-primary max-md:min-h-[44px]" onClick={guardar} disabled={guardando}>Guardar</button>
      </div>
    </DaxCard>
  )
}
