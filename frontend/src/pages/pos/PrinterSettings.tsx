import { useEffect, useState, useCallback, useRef } from 'react'
import { printerApi, detectOS, AGENT_BASE } from '../../api/printer'
import { getDeviceIdShort } from '../../utils/device'

// Web Bluetooth API type declarations (not in TS lib by default)
declare global {
  interface Navigator { bluetooth?: WebBluetooth }
  interface WebBluetooth {
    requestDevice(options: { acceptAllDevices?: boolean; optionalServices?: string[] }): Promise<BluetoothDevice>
  }
  interface BluetoothDevice {
    name?: string
    gatt?: BluetoothRemoteGATTServer
    addEventListener(event: 'gattserverdisconnected', handler: () => void): void
  }
  interface BluetoothRemoteGATTServer {
    connect(): Promise<BluetoothRemoteGATTServer>
    disconnect(): void
    getPrimaryService(uuid: string): Promise<BluetoothRemoteGATTService>
  }
  interface BluetoothRemoteGATTService {
    getCharacteristic(uuid: string): Promise<BluetoothRemoteGATTCharacteristic>
  }
  interface BluetoothRemoteGATTCharacteristic {
    writeValueWithoutResponse(value: BufferSource): Promise<void>
  }
}
import { useAuthStore } from '../../store/authStore'
import { usePOSStore } from '../../store/posStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { AgentDiagnosticsPanel } from '../../components/pos/AgentDiagnosticsPanel'
import { PrinterInstallWizard } from '../../components/pos/PrinterInstallWizard'
import client from '../../api/client'
import { formatCurrency } from '../../utils/currency'

interface BranchConfig {
  printer_name: string | null
  logo_url: string | null
  paper_width_mm: number
  ticket_header: string | null
  ticket_footer: string | null
  open_drawer_on_print: boolean
}

interface OrgDetails {
  name: string
  tax_id: string | null
  address: string | null
  phone: string | null
}

type AgentMode = 'local' | 'server'
type Tab = 'windows' | 'linux' | 'mac' | 'bluetooth'

/** Comandos de conversión al autoarranque. Los nombres de archivo que aparecen
 *  en esta pantalla viven en https://github.com/Ecamposg95/Atlas-Print-Agent: en
 *  el repo de origen un renombrado dejó la pantalla dictando archivos
 *  inexistentes durante dos meses y el autoarranque quedó inalcanzable. */
const AUTOSTART_CMD_LINUX = 'sudo bash core/instalar-servicio-linux.sh'
/** macOS instala un LaunchAgent del usuario: sin sudo a propósito. */
const AUTOSTART_CMD_MAC = 'bash core/instalar-servicio-mac.sh'

type BtState = 'idle' | 'scanning' | 'connected' | 'error'
interface BtDevice { name: string; device: BluetoothDevice; char: BluetoothRemoteGATTCharacteristic }

const SAMPLE_ITEMS = [
  { name: 'Coca-Cola 600ml', qty: 2, unit: 18.5, total: 37.0 },
  { name: 'Sabritas Original', qty: 1, unit: 22.0, total: 22.0 },
  { name: 'Agua Ciel 1L', qty: 3, unit: 12.0, total: 36.0 },
]
const SAMPLE_SUBTOTAL = 81.03
const SAMPLE_IVA = 12.97
const SAMPLE_TOTAL = 94.0

export function PrinterSettings() {
  const { branch, org, user } = useAuthStore()
  // El bloque de autoarranque se le oculta a la cajera: su rutina de cada
  // mañana no cambia hasta que el dueño convierta la caja en persona.
  const esAdmin = user?.role === 'ADMINISTRADOR' || user?.role === 'DUEÑO'
  const setPrinterName = usePOSStore(s => s.setPrinterName)
  const detectedOS = detectOS()
  const initialTab: Tab = detectedOS === 'linux' ? 'linux' : detectedOS === 'mac' ? 'mac' : 'windows'
  const [tab, setTab] = useState<Tab>(initialTab)

  const [config, setConfig] = useState<BranchConfig>({
    printer_name: null,
    logo_url: null,
    paper_width_mm: 80,
    ticket_header: '',
    ticket_footer: '',
    open_drawer_on_print: true,
  })
  const [logoUploading, setLogoUploading] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)
  const logoInputRef = useRef<HTMLInputElement>(null)
  const [orgDetails, setOrgDetails] = useState<OrgDetails>({
    name: org?.name ?? '',
    tax_id: null,
    address: null,
    phone: null,
  })
  const [localPrinters, setLocalPrinters] = useState<string[]>([])
  const [serverPrinters, setServerPrinters] = useState<string[]>([])
  const [agentOnline, setAgentOnline] = useState(false)
  const [agentMode, setAgentMode] = useState<AgentMode>('local')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null)

  // Bluetooth state
  const [btState, setBtState] = useState<BtState>('idle')
  const [btDevice, setBtDevice] = useState<BtDevice | null>(null)
  const [btError, setBtError] = useState<string | null>(null)
  const btSupported = typeof navigator !== 'undefined' && 'bluetooth' in navigator

  const [wizardOpen, setWizardOpen] = useState(false)

  const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const loadBranchConfig = useCallback(async () => {
    if (!branch?.id) return
    try {
      const { data } = await client.get(`/branches/${branch.id}`)
      setConfig({
        printer_name: data.printer_name ?? null,
        logo_url: data.logo_url ?? null,
        paper_width_mm: data.paper_width_mm ?? 80,
        ticket_header: data.ticket_header ?? '',
        ticket_footer: data.ticket_footer ?? '',
        open_drawer_on_print: data.open_drawer_on_print ?? true,
      })
      if (data.printer_name) setPrinterName(data.printer_name)
    } catch { /* usa defaults */ }
  }, [branch?.id])

  const loadOrgDetails = useCallback(async () => {
    try {
      const { data } = await client.get('/organization/')
      setOrgDetails({
        name: data.name ?? org?.name ?? '',
        tax_id: data.tax_id ?? null,
        address: data.address ?? null,
        phone: data.phone ?? null,
      })
    } catch { /* usa org del store */ }
  }, [org?.name])

  const loadLocalPrinters = useCallback(async () => {
    const online = await printerApi.pingAgent()
    setAgentOnline(online)
    if (online) {
      const printers = await printerApi.getLocalPrinters()
      setLocalPrinters(printers)
    } else {
      setLocalPrinters([])
    }
  }, [])

  const loadServerPrinters = useCallback(async () => {
    const printers = await printerApi.getServerPrinters()
    setServerPrinters(printers)
  }, [])

  useEffect(() => {
    const init = async () => {
      await Promise.all([loadBranchConfig(), loadOrgDetails(), loadLocalPrinters(), loadServerPrinters()])
      setLoading(false)
    }
    init()
  }, [loadBranchConfig, loadOrgDetails, loadLocalPrinters, loadServerPrinters])

  /** Seleccionar impresora: actualiza config local + posStore (localStorage) */
  const selectPrinter = (p: string) => {
    setConfig(c => ({ ...c, printer_name: p }))
    setPrinterName(p)
  }

  const save = async () => {
    if (!branch?.id) { showToast('Sin sucursal activa', 'error'); return }
    setSaving(true)
    try {
      await client.put(`/branches/${branch.id}`, {
        printer_name: config.printer_name,
        paper_width_mm: config.paper_width_mm,
        ticket_header: config.ticket_header || null,
        ticket_footer: config.ticket_footer || null,
        open_drawer_on_print: config.open_drawer_on_print,
      })
      showToast('Configuración guardada')
    } catch { showToast('Error al guardar', 'error') }
    finally { setSaving(false) }
  }

  const uploadBranchLogo = async (file: File) => {
    if (!branch?.id) return
    setLogoError(null)
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setLogoError('Solo PNG, JPEG o WEBP')
      return
    }
    if (file.size > 1024 * 1024) {
      setLogoError('La imagen no debe superar 1 MB')
      return
    }
    setLogoUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await client.post(`/branches/${branch.id}/logo`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setConfig(c => ({ ...c, logo_url: data.logo_url }))
    } catch { setLogoError('Error al subir logo') }
    finally { setLogoUploading(false) }
  }

  const deleteBranchLogo = async () => {
    if (!branch?.id) return
    try {
      await client.delete(`/branches/${branch.id}/logo`)
      setConfig(c => ({ ...c, logo_url: null }))
    } catch { /* ignore */ }
  }

  const testPrint = async () => {
    if (!config.printer_name) { showToast('Selecciona una impresora primero', 'error'); return }
    setTesting(true)
    try {
      // Track 4: solo agente local. Server-side CUPS deprecado.
      // Refleja la selección actual aunque no se haya guardado todavía.
      const b64 = await printerApi.testPrintBase64({
        printerName: config.printer_name,
        paperWidthMm: config.paper_width_mm,
      })
      if (!b64) throw new Error('Sin datos del servidor')
      await printerApi.printViaAgent(config.printer_name, b64)
      showToast('Ticket de prueba enviado')
    } catch (e: unknown) {
      showToast(`Error: ${(e as Error).message ?? 'desconocido'}`, 'error')
    } finally { setTesting(false) }
  }

  // ── Bluetooth helpers ─────────────────────────────────────────────────────
  // UUIDs comunes de impresoras térmicas BLE (ESC/POS over BLE)
  const BT_SERVICE_UUIDS = [
    '000018f0-0000-1000-8000-00805f9b34fb', // Impresoras genéricas BLE
    '49535343-fe7d-4ae5-8fa9-9fafd205e455', // Goojprt, Peripage, etc.
    '0000ff00-0000-1000-8000-00805f9b34fb', // Xprinter, ZJ-80
  ]
  const BT_CHAR_UUIDS = [
    '00002af1-0000-1000-8000-00805f9b34fb',
    '49535343-8841-43f4-a8d4-ecbe34729bb3',
    '0000ff02-0000-1000-8000-00805f9b34fb',
  ]

  const connectBluetooth = async () => {
    if (!btSupported) return
    setBtState('scanning')
    setBtError(null)
    try {
      const device = await (navigator as any).bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices: BT_SERVICE_UUIDS,
      })
      const server = await device.gatt!.connect()

      // Buscar servicio y característica compatibles
      let char: BluetoothRemoteGATTCharacteristic | null = null
      for (const svcUuid of BT_SERVICE_UUIDS) {
        try {
          const svc = await server.getPrimaryService(svcUuid)
          for (const charUuid of BT_CHAR_UUIDS) {
            try {
              char = await svc.getCharacteristic(charUuid)
              if (char) break
            } catch { /* siguiente */ }
          }
          if (char) break
        } catch { /* siguiente servicio */ }
      }

      if (!char) {
        device.gatt!.disconnect()
        setBtState('error')
        setBtError('No se encontró una característica de escritura compatible. Verifica que es una impresora ESC/POS BLE.')
        return
      }

      setBtDevice({ name: device.name ?? 'Impresora BT', device, char })
      setBtState('connected')
      setConfig(c => ({ ...c, printer_name: `BT:${device.name ?? 'bluetooth'}` }))

      device.addEventListener('gattserverdisconnected', () => {
        setBtDevice(null)
        setBtState('idle')
        setBtError('Dispositivo desconectado.')
      })
    } catch (e: unknown) {
      const msg = (e as Error).message ?? ''
      if (msg.includes('cancelled') || msg.includes('cancel')) {
        setBtState('idle') // usuario canceló el diálogo
      } else {
        setBtState('error')
        setBtError(msg || 'Error al conectar')
      }
    }
  }

  const disconnectBluetooth = () => {
    btDevice?.device.gatt?.disconnect()
    setBtDevice(null)
    setBtState('idle')
    setBtError(null)
    setConfig(c => ({ ...c, printer_name: null }))
  }

  const testPrintBluetooth = async () => {
    if (!btDevice) return
    setTesting(true)
    try {
      const b64 = await printerApi.testPrintBase64({ paperWidthMm: config.paper_width_mm })
      if (!b64) throw new Error('Sin datos del servidor')
      const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
      // Enviar en chunks de 512 bytes (límite BLE MTU)
      const CHUNK = 512
      for (let i = 0; i < raw.length; i += CHUNK) {
        await btDevice.char.writeValueWithoutResponse(raw.slice(i, i + CHUNK))
      }
      showToast('Ticket enviado por Bluetooth')
    } catch (e: unknown) {
      showToast(`Error BT: ${(e as Error).message ?? 'desconocido'}`, 'error')
    } finally { setTesting(false) }
  }

  const handleTestPrint = async () => {
    if (tab === 'bluetooth') { await testPrintBluetooth(); return }
    await testPrint()
  }

  if (loading) return <Spinner text="Cargando configuración..." />

  return (
    <div className="space-y-5 p-1">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-xl shadow-xl text-sm font-semibold flex items-center gap-2 ${
          toast.type === 'success' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
        }`}>
          <i className={`fa-solid ${toast.type === 'success' ? 'fa-check' : 'fa-xmark'}`} />
          {toast.msg}
        </div>
      )}

      {/* Agente local — estado + diagnóstico */}
      <AgentDiagnosticsPanel />

      <PrinterInstallWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onInstalled={async () => {
          // Refresca la lista de impresoras locales después de instalar
          const locals = await printerApi.getLocalPrinters()
          setLocalPrinters(locals)
        }}
      />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-print text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black" style={{ color: 'var(--dax-text)' }}>Impresora</h1>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setWizardOpen(true)}
            className="dax-btn-secondary text-xs"
            title="Detectar e instalar una impresora térmica USB en modo raw"
          >
            <i className="fa-solid fa-plus" /> Instalar impresora
          </button>
          <button onClick={save} disabled={saving} className="dax-btn-primary text-xs">
            {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-floppy-disk" /> Guardar</>}
          </button>
          <button
            onClick={handleTestPrint}
            disabled={testing || (tab === 'bluetooth' ? !btDevice : !config.printer_name)}
            className="dax-btn-secondary text-xs disabled:opacity-40"
          >
            {testing ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-paper-plane" /> Probar</>}
          </button>
        </div>
      </div>

      {/* OS / Mode Tabs */}
      <div className="flex flex-wrap gap-1 p-1 rounded-xl w-fit" style={{ background: 'var(--dax-elevated)' }}>
        {([
          { id: 'windows' as Tab, icon: 'fa-brands fa-windows', label: 'Windows' },
          { id: 'linux'   as Tab, icon: 'fa-brands fa-linux',   label: 'Linux'   },
          { id: 'mac'     as Tab, icon: 'fa-brands fa-apple',   label: 'macOS'   },
          { id: 'bluetooth' as Tab, icon: 'fa-solid fa-bluetooth', label: 'Bluetooth' },
        ]).map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              tab === t.id ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-white'
            }`}
          >
            <i className={t.icon} />
            {t.label}
            {detectedOS === t.id && (
              <span className="text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full font-black">
                detectado
              </span>
            )}
            {t.id === 'bluetooth' && btDevice && (
              <span className="text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full font-black">
                conectado
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Banner: agente offline — acepta el certificado */}
      {!agentOnline && tab !== 'bluetooth' && (
        <a
          href={AGENT_BASE + '/health'}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-colors"
          style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.35)' }}
        >
          <i className="fa-solid fa-triangle-exclamation text-lg flex-shrink-0" />
          <span className="flex-1">
            <span className="font-black">Agente offline.</span> Si ya lo ejecutaste, haz clic aquí para aceptar el certificado SSL en el navegador y luego regresa a esta página.
          </span>
          <i className="fa-solid fa-arrow-up-right-from-square text-xs flex-shrink-0" />
        </a>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Columna izquierda — agente */}
        <div className="space-y-4">

          {tab === 'windows' && (
            <>
              <DaxCard>
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                       style={{ background: 'rgba(99,102,241,0.15)' }}>
                    <i className="fa-brands fa-windows text-indigo-400 text-lg" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold" style={{ color: 'var(--dax-text)' }}>Agente Local de Impresión</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--dax-text-muted)' }}>
                      Requerido para imprimir desde el navegador en Windows
                    </p>
                  </div>
                  <a
                    href={printerApi.downloadAgentUrl('windows')}
                    className="flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg transition-colors flex-shrink-0"
                    style={{ background: 'rgba(99,102,241,0.2)', color: '#a5b4fc' }}
                  >
                    <i className="fa-solid fa-download" /> Descargar
                  </a>
                </div>
                <div className="mt-4 space-y-2">
                  <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                    Instrucciones
                  </p>
                  {[
                    'Descomprime el ZIP en el Escritorio o cualquier carpeta.',
                    'Abre Atlas-Print-Agent-main/legacy/print_agent y ejecuta impresora_win.bat (doble clic).',
                    'Si Windows bloquea: «Más información → Ejecutar de todas formas».',
                    'Deja la ventana negra abierta — es el agente corriendo.',
                    'Acepta el certificado haciendo clic en el botón de abajo.',
                    'Regresa aquí y haz clic en «Buscar impresoras».',
                  ].map((step, i) => (
                    <div key={i} className="flex items-start gap-2.5">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black"
                            style={{ background: 'var(--dax-elevated)', color: 'var(--dax-text-muted)' }}>
                        {i + 1}
                      </span>
                      <p className="text-xs leading-relaxed" style={{ color: 'var(--dax-text-muted)' }}>{step}</p>
                    </div>
                  ))}
                  <a
                    href={AGENT_BASE + '/health'}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-bold transition-colors"
                    style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.3)' }}
                  >
                    <i className="fa-solid fa-shield-halved" />
                    Paso 5: Aceptar certificado del agente
                    <i className="fa-solid fa-arrow-up-right-from-square text-[10px]" />
                  </a>
                </div>
              </DaxCard>

              <DaxCard>
                <div className="flex items-center justify-between mb-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                    Impresoras detectadas
                  </p>
                  <div className="flex items-center gap-2">
                    <span className={`flex items-center gap-1 text-[10px] font-bold ${agentOnline ? 'text-emerald-400' : 'text-red-400'}`}>
                      <i className="fa-solid fa-circle text-[7px]" />
                      Agente {agentOnline ? 'online' : 'offline'}
                    </span>
                    <button
                      onClick={loadLocalPrinters}
                      className="text-[10px] text-slate-500 hover:text-white px-2 py-1 rounded-lg transition-colors"
                      style={{ border: '1px solid var(--dax-border-dim)' }}
                    >
                      <i className="fa-solid fa-rotate-right" /> Buscar
                    </button>
                  </div>
                </div>
                <PrinterList
                  printers={localPrinters}
                  selected={config.printer_name}
                  onSelect={selectPrinter}
                  emptyMsg="Agente offline o sin impresoras. Descarga y ejecuta el agente primero."
                />
              </DaxCard>
            </>
          )}

          {tab === 'linux' && (
            <>
              <DaxCard>
                <p className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: 'var(--dax-text-faint)' }}>
                  Modo de impresión
                </p>
                <div className="flex items-center gap-2 p-2 rounded-lg" style={{ background: 'rgba(99,102,241,0.1)' }}>
                  <i className="fa-solid fa-laptop text-indigo-400 text-base" />
                  <div className="flex-1">
                    <p className="text-xs font-bold text-white">Agente Local (esta PC)</p>
                    <p className="text-[10px]" style={{ color: 'var(--dax-text-faint)' }}>
                      Cada PC imprime en su propia impresora local. ID: <code>...{getDeviceIdShort()}</code>
                    </p>
                  </div>
                </div>
              </DaxCard>

              {true && (
                <DaxCard>
                  <div className="flex items-start gap-3 mb-4">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                         style={{ background: 'rgba(34,197,94,0.1)' }}>
                      <i className="fa-brands fa-linux text-emerald-400 text-lg" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-bold" style={{ color: 'var(--dax-text)' }}>Agente Linux</p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--dax-text-muted)' }}>Requiere Python 3.10+ y CUPS instalado</p>
                    </div>
                    <a
                      href={printerApi.downloadAgentUrl('linux')}
                      className="flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg transition-colors flex-shrink-0"
                      style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80' }}
                    >
                      <i className="fa-solid fa-download" /> Descargar
                    </a>
                  </div>
                  <div className="space-y-2 mb-4">
                    <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                      Instrucciones Linux
                    </p>
                    {[
                      'Descomprime el ZIP y entra a Atlas-Print-Agent-main/legacy/print_agent.',
                      'Instala CUPS si no lo tienes: sudo apt install cups',
                      'Ejecuta el agente: bash impresora_linux.sh',
                      'Acepta el certificado haciendo clic en el botón de abajo.',
                      'Deja la terminal abierta y haz clic en «Buscar impresoras».',
                      'Para que arranque solo al prender la PC: sudo bash core/instalar-servicio-linux.sh (ver INSTALL_LINUX.txt).',
                    ].map((step, i) => (
                      <div key={i} className="flex items-start gap-2.5">
                        <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black"
                              style={{ background: 'var(--dax-elevated)', color: 'var(--dax-text-muted)' }}>
                          {i + 1}
                        </span>
                        <p className="text-xs leading-relaxed" style={{ color: 'var(--dax-text-muted)' }}>{step}</p>
                      </div>
                    ))}
                    <a
                      href={AGENT_BASE + '/health'}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-bold transition-colors"
                      style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.3)' }}
                    >
                      <i className="fa-solid fa-shield-halved" />
                      Paso 4: Aceptar certificado del agente
                      <i className="fa-solid fa-arrow-up-right-from-square text-[10px]" />
                    </a>
                  </div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                      Impresoras detectadas
                    </p>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold ${agentOnline ? 'text-emerald-400' : 'text-red-400'}`}>
                        <i className="fa-solid fa-circle text-[7px]" /> {agentOnline ? 'Online' : 'Offline'}
                      </span>
                      <button
                        onClick={loadLocalPrinters}
                        className="text-[10px] text-slate-500 hover:text-white px-2 py-1 rounded-lg transition-colors"
                        style={{ border: '1px solid var(--dax-border-dim)' }}
                      >
                        <i className="fa-solid fa-rotate-right" /> Buscar
                      </button>
                    </div>
                  </div>
                  <PrinterList
                    printers={localPrinters}
                    selected={config.printer_name}
                    onSelect={selectPrinter}
                    emptyMsg="Agente offline. Sigue las instrucciones arriba."
                  />
                </DaxCard>
              )}

              {esAdmin && (
                <AutostartCard
                  cmd={AUTOSTART_CMD_LINUX}
                  bullets={[
                    'Conserva el certificado que este navegador ya aceptó — no hay que volver a aceptarlo.',
                    'Sin sudo también funciona: instala un servicio de usuario con arranque al prender.',
                    'Deja el agente en /opt/atlas-print-agent, no en Descargas.',
                    'Después de esto, abrir el .sh a mano muestra «ya está activo» en vez de un error.',
                  ]}
                  onToast={showToast}
                />
              )}

              {/* Track 4: server-side CUPS mode eliminado. Solo agente local. */}
            </>
          )}

          {tab === 'mac' && (
            <>
              <DaxCard>
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                       style={{ background: 'rgba(148,163,184,0.15)' }}>
                    <i className="fa-brands fa-apple text-slate-300 text-lg" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold" style={{ color: 'var(--dax-text)' }}>Agente macOS</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--dax-text-muted)' }}>
                      Requiere Python 3.10+ · CUPS incluido en macOS
                    </p>
                  </div>
                  <a
                    href={printerApi.downloadAgentUrl('mac')}
                    className="flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg transition-colors flex-shrink-0"
                    style={{ background: 'rgba(148,163,184,0.15)', color: '#cbd5e1' }}
                  >
                    <i className="fa-solid fa-download" /> Descargar
                  </a>
                </div>
                <div className="mt-4 space-y-2">
                  <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                    Instrucciones macOS
                  </p>
                  {[
                    'Descomprime el ZIP y entra a Atlas-Print-Agent-main/legacy/print_agent.',
                    'Abre Terminal (Finder → Aplicaciones → Utilidades → Terminal).',
                    'Arrastra impresora_mac.sh a la terminal y presiona Enter.',
                    'Acepta el certificado haciendo clic en el botón de abajo.',
                    'Deja la terminal abierta y haz clic en «Buscar impresoras».',
                  ].map((step, i) => (
                    <div key={i} className="flex items-start gap-2.5">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black"
                            style={{ background: 'var(--dax-elevated)', color: 'var(--dax-text-muted)' }}>
                        {i + 1}
                      </span>
                      <p className="text-xs leading-relaxed" style={{ color: 'var(--dax-text-muted)' }}>{step}</p>
                    </div>
                  ))}
                  <a
                    href={AGENT_BASE + '/health'}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-bold transition-colors"
                    style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.3)' }}
                  >
                    <i className="fa-solid fa-shield-halved" />
                    Paso 4: Aceptar certificado del agente
                    <i className="fa-solid fa-arrow-up-right-from-square text-[10px]" />
                  </a>
                </div>
              </DaxCard>

              {esAdmin && (
                <AutostartCard
                  cmd={AUTOSTART_CMD_MAC}
                  bullets={[
                    'Se instala en ~/Library/Application Support/AtlasPrintAgent, no en Descargas.',
                    'Arranca al iniciar sesión y launchd lo revive si se cae.',
                    'Conserva el certificado que este navegador ya aceptó.',
                    'No uses sudo para instalarlo: es un servicio de tu usuario. Y córrelo en la Mac, no por SSH.',
                    'macOS 14+ ya no admite colas raw: la cola se crea con un PPD genérico y el agente fuerza el raw en cada impresión.',
                    'Alta de la cola: sudo lpadmin -p ticket -E -v "<uri de lpinfo -v>" -P /System/Library/Frameworks/ApplicationServices.framework/Versions/A/Frameworks/PrintCore.framework/Versions/A/Resources/Generic.ppd',
                    'Prueba a mano: printf \'PRUEBA\\n\\n\\n\\n\' | lp -d ticket -o raw',
                  ]}
                  onToast={showToast}
                />
              )}

              <DaxCard>
                <div className="flex items-center justify-between mb-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                    Impresoras detectadas
                  </p>
                  <div className="flex items-center gap-2">
                    <span className={`flex items-center gap-1 text-[10px] font-bold ${agentOnline ? 'text-emerald-400' : 'text-red-400'}`}>
                      <i className="fa-solid fa-circle text-[7px]" />
                      Agente {agentOnline ? 'online' : 'offline'}
                    </span>
                    <button
                      onClick={loadLocalPrinters}
                      className="text-[10px] text-slate-500 hover:text-white px-2 py-1 rounded-lg transition-colors"
                      style={{ border: '1px solid var(--dax-border-dim)' }}
                    >
                      <i className="fa-solid fa-rotate-right" /> Buscar
                    </button>
                  </div>
                </div>
                <PrinterList
                  printers={localPrinters}
                  selected={config.printer_name}
                  onSelect={selectPrinter}
                  emptyMsg="Agente offline. Sigue las instrucciones arriba."
                />
              </DaxCard>
            </>
          )}

          {tab === 'bluetooth' && (
            <DaxCard>
              <div className="flex items-center gap-2 mb-4">
                <i className="fa-solid fa-bluetooth text-blue-400 text-xl" />
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--dax-text)' }}>Impresora Bluetooth</p>
                  <p className="text-xs" style={{ color: 'var(--dax-text-muted)' }}>
                    Conexión directa sin agente local · requiere Chrome/Edge
                  </p>
                </div>
              </div>

              {!btSupported && (
                <div className="p-3 rounded-xl mb-4" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)' }}>
                  <p className="text-xs font-bold text-red-400 mb-1"><i className="fa-solid fa-xmark-circle mr-1" />Web Bluetooth no disponible</p>
                  <p className="text-[10px]" style={{ color: 'var(--dax-text-muted)' }}>
                    Usa Chrome o Edge en HTTPS. Firefox y Safari no soportan Web Bluetooth.
                  </p>
                </div>
              )}

              {btSupported && btState === 'idle' && (
                <button
                  onClick={connectBluetooth}
                  className="w-full py-3 rounded-xl text-sm font-bold transition-colors flex items-center justify-center gap-2"
                  style={{ background: 'rgba(59,130,246,0.2)', color: '#93c5fd', border: '1px solid rgba(59,130,246,0.3)' }}
                >
                  <i className="fa-solid fa-bluetooth" />
                  Buscar e conectar impresora
                </button>
              )}

              {btState === 'scanning' && (
                <div className="text-center py-6">
                  <i className="fa-solid fa-spinner fa-spin text-blue-400 text-2xl mb-2 block" />
                  <p className="text-xs" style={{ color: 'var(--dax-text-muted)' }}>Buscando dispositivos Bluetooth...</p>
                  <p className="text-[10px] mt-1" style={{ color: 'var(--dax-text-faint)' }}>Selecciona tu impresora en el diálogo del navegador</p>
                </div>
              )}

              {btState === 'connected' && btDevice && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-3 rounded-xl"
                       style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)' }}>
                    <i className="fa-solid fa-circle text-emerald-400 text-[8px]" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-emerald-400">{btDevice.name}</p>
                      <p className="text-[10px]" style={{ color: 'var(--dax-text-faint)' }}>Conectado via BLE · ESC/POS listo</p>
                    </div>
                    <button
                      onClick={disconnectBluetooth}
                      className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded-lg transition-colors"
                      style={{ border: '1px solid rgba(239,68,68,0.2)' }}
                    >
                      <i className="fa-solid fa-xmark" /> Desconectar
                    </button>
                  </div>
                </div>
              )}

              {btState === 'error' && (
                <div className="space-y-3">
                  <div className="p-3 rounded-xl" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
                    <p className="text-xs font-bold text-red-400 mb-1"><i className="fa-solid fa-triangle-exclamation mr-1" />Error de conexión</p>
                    <p className="text-[10px]" style={{ color: 'var(--dax-text-muted)' }}>{btError}</p>
                  </div>
                  <button
                    onClick={connectBluetooth}
                    className="w-full py-2.5 rounded-xl text-xs font-bold transition-colors"
                    style={{ background: 'rgba(59,130,246,0.15)', color: '#93c5fd', border: '1px solid rgba(59,130,246,0.2)' }}
                  >
                    <i className="fa-solid fa-rotate-right mr-1" /> Reintentar
                  </button>
                </div>
              )}

              <div className="mt-4 p-3 rounded-xl space-y-1.5" style={{ background: 'var(--dax-elevated)' }}>
                <p className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: 'var(--dax-text-faint)' }}>
                  Impresoras compatibles (BLE ESC/POS)
                </p>
                {['Goojprt PT-210 / PT-100', 'Peripage A6 / A9', 'Xprinter XP-P300 / XP-P800', 'HOIN HOP-E200 / E300', 'Cualquier impresora ESC/POS BLE'].map((m, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <i className="fa-solid fa-check text-emerald-400 text-[10px]" />
                    <span className="text-[10px]" style={{ color: 'var(--dax-text-muted)' }}>{m}</span>
                  </div>
                ))}
              </div>
            </DaxCard>
          )}

        </div>

        {/* Columna derecha — Editor de ticket */}
        <div className="space-y-4">

          {/* Ancho de papel */}
          <DaxCard>
            <p className="text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: 'var(--dax-text-faint)' }}>
              Ancho de Papel
            </p>
            <div className="flex gap-2">
              {[58, 80].map(w => (
                <button
                  key={w}
                  onClick={() => setConfig(c => ({ ...c, paper_width_mm: w }))}
                  className={`flex-1 py-2.5 rounded-xl border text-sm font-semibold transition-colors ${
                    config.paper_width_mm === w ? 'border-indigo-500 bg-indigo-600/20 text-white' : 'text-slate-400 hover:border-slate-600'
                  }`}
                  style={{ borderColor: config.paper_width_mm === w ? undefined : 'var(--dax-border-dim)' }}
                >
                  {w} mm
                </button>
              ))}
            </div>
          </DaxCard>

          {/* Cajón de dinero */}
          <DaxCard>
            <p className="text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: 'var(--dax-text-faint)' }}>
              <i className="fa-solid fa-cash-register mr-1.5" />Cajón de Dinero
            </p>
            <label className="flex items-start gap-3 cursor-pointer mb-3">
              <input
                type="checkbox"
                checked={config.open_drawer_on_print}
                onChange={e => setConfig(c => ({ ...c, open_drawer_on_print: e.target.checked }))}
                className="mt-0.5 accent-indigo-500"
              />
              <span className="text-sm text-slate-300 leading-tight">
                Abrir cajón al imprimir ticket
                <span className="block text-[11px] text-slate-500 mt-0.5">
                  Solo se abre si el pago incluye efectivo. El cajón debe estar conectado a la térmica por RJ-11.
                </span>
              </span>
            </label>
            <button
              disabled={!config.printer_name || !agentOnline}
              onClick={async () => {
                if (!config.printer_name) return
                try {
                  await printerApi.openDrawerViaAgent(config.printer_name)
                  showToast('Cajón abierto')
                } catch (e) {
                  showToast(`Error: ${(e as Error).message}`, 'error')
                }
              }}
              className="w-full py-2 rounded-xl border text-sm font-semibold text-white bg-indigo-600/10 border-indigo-500/40 hover:bg-indigo-600/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <i className="fa-solid fa-inbox mr-2" />Abrir cajón ahora
            </button>
          </DaxCard>

          {/* Logo de sucursal */}
          <DaxCard>
            <p className="text-[10px] font-bold uppercase tracking-widest mb-4" style={{ color: 'var(--dax-text-faint)' }}>
              <i className="fa-solid fa-image mr-1.5" />Logo de la Sucursal
            </p>
            <p className="text-[11px] mb-3" style={{ color: 'var(--dax-text-muted)' }}>
              Si se configura, reemplaza el logo de la organización en el ticket de esta sucursal.
            </p>
            <div className="flex items-start gap-4">
              {config.logo_url ? (
                <div className="flex flex-col items-center gap-2">
                  <img
                    src={config.logo_url}
                    alt="Logo sucursal"
                    className="h-16 w-16 object-contain rounded-lg"
                    style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)', padding: '4px' }}
                  />
                  <button
                    onClick={deleteBranchLogo}
                    className="text-[10px] text-red-400 hover:text-red-300 flex items-center gap-1"
                  >
                    <i className="fa-solid fa-trash" /> Eliminar
                  </button>
                </div>
              ) : (
                <div className="h-16 w-16 rounded-lg flex items-center justify-center flex-shrink-0"
                     style={{ background: 'var(--dax-elevated)', border: '1px dashed var(--dax-border-dim)' }}>
                  <i className="fa-solid fa-image text-xl" style={{ color: 'var(--dax-text-faint)' }} />
                </div>
              )}
              <div className="flex-1">
                <input
                  ref={logoInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadBranchLogo(f) }}
                />
                <button
                  onClick={() => logoInputRef.current?.click()}
                  disabled={logoUploading}
                  className="dax-btn-secondary text-xs disabled:opacity-40"
                >
                  {logoUploading
                    ? <i className="fa-solid fa-spinner fa-spin" />
                    : <><i className="fa-solid fa-upload" /> {config.logo_url ? 'Cambiar logo' : 'Subir logo'}</>}
                </button>
                <p className="text-[10px] mt-1.5" style={{ color: 'var(--dax-text-faint)' }}>
                  PNG, JPEG o WEBP · máx 1 MB
                </p>
                {logoError && <p className="text-[10px] mt-1 text-red-400">{logoError}</p>}
              </div>
            </div>
          </DaxCard>

          {/* Editor de ticket */}
          <DaxCard>
            <p className="text-[10px] font-bold uppercase tracking-widest mb-4" style={{ color: 'var(--dax-text-faint)' }}>
              <i className="fa-solid fa-receipt mr-1.5" />Editor de Ticket
            </p>

            <div className="flex flex-col gap-4">

              {/* Encabezado editable */}
              <div>
                <label className="text-[10px] font-bold uppercase tracking-widest block mb-1.5"
                       style={{ color: 'var(--dax-text-faint)' }}>
                  <i className="fa-solid fa-pen-to-square mr-1" />Encabezado personalizado
                </label>
                <textarea
                  value={config.ticket_header ?? ''}
                  onChange={e => setConfig(c => ({ ...c, ticket_header: e.target.value }))}
                  className="dax-input w-full h-20 resize-none font-mono text-xs"
                  placeholder={'Texto extra encima del nombre\nPromoción, horario, etc.'}
                />
                <p className="text-[10px] mt-1" style={{ color: 'var(--dax-text-faint)' }}>
                  Se imprime antes del nombre de la empresa. Cada línea = 1 línea en el ticket.{' '}
                  <span style={{ color: 'var(--dax-text-muted)', fontStyle: 'italic' }}>
                    (usa el de organización si está vacío)
                  </span>
                </p>
              </div>

              {/* Vista previa realista */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest"
                         style={{ color: 'var(--dax-text-faint)' }}>
                    <i className="fa-solid fa-eye mr-1" />Vista previa
                  </label>
                  <span className="text-[9px] px-2 py-0.5 rounded-full font-bold"
                        style={{ background: 'var(--dax-elevated)', color: 'var(--dax-text-faint)' }}>
                    {config.paper_width_mm}mm · datos de ejemplo
                  </span>
                </div>

                {/* Papel térmico simulado */}
                <div className="flex justify-center">
                  <TicketPreview
                    paperWidth={config.paper_width_mm}
                    header={config.ticket_header ?? ''}
                    footer={config.ticket_footer ?? ''}
                    orgName={orgDetails.name}
                    taxId={orgDetails.tax_id}
                    address={orgDetails.address}
                    phone={orgDetails.phone}
                    branchName={branch?.name ?? null}
                    logoUrl={config.logo_url}
                  />
                </div>
              </div>

              {/* Pie de página editable */}
              <div>
                <label className="text-[10px] font-bold uppercase tracking-widest block mb-1.5"
                       style={{ color: 'var(--dax-text-faint)' }}>
                  <i className="fa-solid fa-pen-to-square mr-1" />Pie de página
                </label>
                <textarea
                  value={config.ticket_footer ?? ''}
                  onChange={e => setConfig(c => ({ ...c, ticket_footer: e.target.value }))}
                  className="dax-input w-full h-16 resize-none font-mono text-xs"
                  placeholder={'¡Gracias por su compra!\nVuelva pronto'}
                />
                <p className="text-[10px] mt-1" style={{ color: 'var(--dax-text-faint)' }}>
                  <span style={{ color: 'var(--dax-text-muted)', fontStyle: 'italic' }}>
                    (usa el de organización si está vacío)
                  </span>
                </p>
              </div>

            </div>
          </DaxCard>

        </div>
      </div>
    </div>
  )
}

// ─── Ticket Preview Component ────────────────────────────────────────────────

function TicketPreview({
  paperWidth,
  header,
  footer,
  orgName,
  taxId,
  address,
  phone,
  branchName,
  logoUrl,
}: {
  paperWidth: number
  header: string
  footer: string
  orgName: string
  taxId: string | null
  address: string | null
  phone: string | null
  branchName: string | null
  logoUrl?: string | null
}) {
  const width = paperWidth === 58 ? 216 : 286
  const now = new Date()
  const dateStr = now.toLocaleDateString('es-MX', { day: '2-digit', month: '2-digit', year: 'numeric' })
  const timeStr = now.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })

  return (
    <div
      className="rounded shadow-lg overflow-hidden"
      style={{
        width: `${width}px`,
        background: '#fff',
        fontFamily: '"Courier New", Courier, monospace',
        fontSize: '10px',
        color: '#111',
        lineHeight: '1.45',
        boxShadow: '0 2px 12px rgba(0,0,0,0.35)',
      }}
    >
      {/* Borde superior papel */}
      <div style={{ height: '6px', background: 'repeating-linear-gradient(90deg,#e5e7eb 0,#e5e7eb 6px,#fff 6px,#fff 12px)' }} />

      <div className="px-3 py-3">

        {/* Logo */}
        {logoUrl && (
          <div style={{ textAlign: 'center', marginBottom: '4px' }}>
            <img src={logoUrl} alt="Logo" style={{ maxHeight: '48px', maxWidth: '100%', objectFit: 'contain' }} />
          </div>
        )}

        {/* Header personalizado */}
        {header.trim() && (
          <>
            {header.split('\n').map((line, i) => (
              <div key={i} style={{ textAlign: 'center', whiteSpace: 'pre' }}>{line || ' '}</div>
            ))}
            <TkSep />
          </>
        )}

        {/* Nombre empresa */}
        <div style={{ textAlign: 'center', fontWeight: 'bold', fontSize: '12px', marginBottom: '1px' }}>
          {orgName || 'NOMBRE EMPRESA'}
        </div>
        {taxId && <div style={{ textAlign: 'center' }}>RFC: {taxId}</div>}
        {address && <div style={{ textAlign: 'center' }}>{address}</div>}
        {phone && <div style={{ textAlign: 'center' }}>Tel: {phone}</div>}
        {branchName && <div style={{ textAlign: 'center', fontSize: '9px', marginTop: '1px' }}>Suc: {branchName}</div>}

        <TkSep />

        {/* Folio + fecha */}
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 'bold' }}>NOTA DE VENTA</span>
          <span>#TK-0001</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: '#555' }}>
          <span>{dateStr}</span>
          <span>{timeStr}</span>
        </div>
        <div style={{ fontSize: '9px', color: '#555' }}>Cajero: Juan P.</div>

        <TkSep />

        {/* Cabecera columnas */}
        <div style={{ display: 'flex', fontWeight: 'bold', fontSize: '9px', color: '#444', marginBottom: '2px' }}>
          <span style={{ width: '24px' }}>Cant</span>
          <span style={{ flex: 1 }}>Producto</span>
          <span style={{ width: '52px', textAlign: 'right' }}>Total</span>
        </div>

        {/* Items */}
        {SAMPLE_ITEMS.map((item, i) => (
          <div key={i}>
            <div style={{ display: 'flex' }}>
              <span style={{ width: '24px' }}>{item.qty}</span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
              <span style={{ width: '52px', textAlign: 'right' }}>{formatCurrency(item.total)}</span>
            </div>
            <div style={{ fontSize: '9px', color: '#666', paddingLeft: '4px' }}>
              @ {formatCurrency(item.unit)} c/u
            </div>
          </div>
        ))}

        {/* Conteo artículos */}
        <div style={{ textAlign: 'right', fontSize: '9px', color: '#555', marginTop: '2px' }}>
          Artículos: {SAMPLE_ITEMS.reduce((s, i) => s + i.qty, 0)}
        </div>

        <TkSep />

        {/* Subtotal / IVA / Total */}
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: '#444' }}>
          <span>Subtotal:</span><span>{formatCurrency(SAMPLE_SUBTOTAL)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: '#444' }}>
          <span>IVA (16%):</span><span>{formatCurrency(SAMPLE_IVA)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 'bold', fontSize: '12px', marginTop: '2px' }}>
          <span>TOTAL VENTA</span><span>{formatCurrency(SAMPLE_TOTAL)}</span>
        </div>

        <TkSep />

        {/* Pago */}
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Efectivo</span><span>{formatCurrency(100)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 'bold' }}>
          <span>Cambio</span><span>{formatCurrency(6)}</span>
        </div>

        <TkSep />

        {/* Footer personalizado */}
        {footer.trim()
          ? footer.split('\n').map((line, i) => (
              <div key={i} style={{ textAlign: 'center' }}>{line || ' '}</div>
            ))
          : <div style={{ textAlign: 'center', color: '#999', fontStyle: 'italic' }}>¡Gracias por su compra!</div>
        }

        {/* Desarrollado con ❤️ */}
        <div style={{ textAlign: 'center', fontSize: '8px', color: '#bbb', marginTop: '6px' }}>
          Desarrollado con ❤️ por Atlas Tech
        </div>
      </div>

      {/* Borde inferior papel (corte) */}
      <div style={{ height: '6px', background: 'repeating-linear-gradient(90deg,#e5e7eb 0,#e5e7eb 6px,#fff 6px,#fff 12px)' }} />
    </div>
  )
}

function TkSep() {
  return (
    <div style={{ borderTop: '1px dashed #aaa', margin: '4px 0' }} />
  )
}

// ─── PrinterList Component ───────────────────────────────────────────────────

/**
 * Bloque "Instalación automática" — solo ADMINISTRADOR/DUEÑO.
 *
 * La cajera NO ve este bloque a propósito: su flujo de cada mañana (abrir el
 * launcher a mano) no debe cambiar hasta que el dueño visite la caja y haga la
 * conversión él mismo. Ver docs/superpowers/runbooks/print-agent-autostart.md
 *
 * Es el mismo bloque para Linux y macOS: solo cambian el comando y las viñetas.
 */
function AutostartCard({
  cmd,
  bullets,
  onToast,
}: {
  cmd: string
  bullets: string[]
  onToast: (msg: string, type?: 'success' | 'error') => void
}) {
  return (
    <DaxCard>
      <div className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
             style={{ background: 'rgba(99,102,241,0.12)' }}>
          <i className="fa-solid fa-bolt text-indigo-400 text-lg" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-bold" style={{ color: 'var(--dax-text)' }}>
            Instalación automática <span className="text-[10px] font-bold px-1.5 py-0.5 rounded ml-1"
              style={{ background: 'rgba(99,102,241,0.2)', color: '#a5b4fc' }}>solo admin</span>
          </p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--dax-text-muted)' }}>
            El agente arranca solo. La cajera ya no abre nada.
          </p>
        </div>
      </div>
      <p className="text-xs leading-relaxed mb-3" style={{ color: 'var(--dax-text-muted)' }}>
        En la carpeta donde ya está el agente de esta PC, abre una terminal y corre:
      </p>
      <div className="flex items-center gap-2 p-2.5 rounded-xl mb-3"
           style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
        <code className="flex-1 text-[11px] font-mono break-all" style={{ color: '#a5b4fc' }}>
          {cmd}
        </code>
        <button
          onClick={() => {
            navigator.clipboard?.writeText(cmd)
              .then(() => onToast('Comando copiado', 'success'))
              .catch(() => onToast('No se pudo copiar', 'error'))
          }}
          className="flex-shrink-0 text-[10px] font-bold px-2.5 py-1.5 rounded-lg transition-colors"
          style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc' }}
        >
          <i className="fa-solid fa-copy" /> Copiar
        </button>
      </div>
      <ul className="space-y-1.5">
        {bullets.map((texto, i) => (
          <li key={i} className="flex items-start gap-2 text-[11px] leading-relaxed"
              style={{ color: 'var(--dax-text-faint)' }}>
            <i className="fa-solid fa-check text-emerald-400 text-[9px] mt-1 flex-shrink-0" />
            {/* break-words: la ruta del PPD genérico de macOS mide ~130 caracteres */}
            <span className="min-w-0 break-words">{texto}</span>
          </li>
        ))}
      </ul>
    </DaxCard>
  )
}

function PrinterList({
  printers,
  selected,
  onSelect,
  emptyMsg,
}: {
  printers: string[]
  selected: string | null
  onSelect: (p: string) => void
  emptyMsg: string
}) {
  if (printers.length === 0) {
    return (
      <div className="text-center py-6">
        <i className="fa-solid fa-print text-2xl mb-2 block" style={{ color: 'var(--dax-text-faint)' }} />
        <p className="text-xs" style={{ color: 'var(--dax-text-muted)' }}>{emptyMsg}</p>
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      {printers.map(p => (
        <button
          key={p}
          onClick={() => onSelect(p)}
          className={`w-full flex items-center gap-3 p-2.5 rounded-xl border transition-colors text-left ${
            selected === p ? 'border-indigo-500 bg-indigo-600/10' : 'hover:border-slate-600'
          }`}
          style={{ borderColor: selected === p ? undefined : 'var(--dax-border-dim)' }}
        >
          <i className={`fa-solid fa-print ${selected === p ? 'text-indigo-400' : 'text-slate-500'}`} />
          <span className={`text-sm font-medium flex-1 truncate ${selected === p ? 'text-white' : 'text-slate-300'}`}>{p}</span>
          {selected === p && <i className="fa-solid fa-check text-indigo-400 text-xs" />}
        </button>
      ))}
    </div>
  )
}
