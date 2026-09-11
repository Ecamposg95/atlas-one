import client from './client'

export interface PrinterSettings {
  printer_name: string | null
  paper_width_mm: number  // 58 | 80
  ticket_header: string | null
  ticket_footer: string | null
}

export const AGENT_BASE = 'https://localhost:9100'

/**
 * Error de conectividad con el agente local: está apagado, o su certificado
 * autofirmado no ha sido aceptado por el navegador. Un `fetch` a
 * https://localhost:9100 falla igual en ambos casos (TypeError "Failed to
 * fetch"), así que damos un mensaje accionable que cubre las dos causas.
 */
export class AgentUnreachableError extends Error {
  constructor() {
    super(
      'No se pudo conectar al Agente de Impresión (https://localhost:9100). ' +
      'Verifica que el agente esté abierto y que hayas aceptado su certificado: ' +
      'abre https://localhost:9100 una vez en el navegador y acepta la advertencia de seguridad.'
    )
    this.name = 'AgentUnreachableError'
  }
}

/** fetch contra el agente local que traduce errores de red a AgentUnreachableError. */
async function agentFetch(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<Response> {
  const { timeoutMs, signal, ...rest } = init
  try {
    return await fetch(`${AGENT_BASE}${path}`, {
      ...rest,
      signal: signal ?? (timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined),
    })
  } catch {
    // Network error / abort por timeout / cert rechazado → todos opacos para JS.
    throw new AgentUnreachableError()
  }
}

export interface AgentCupsQueue {
  name: string
  device_uri: string | null
  accepting: boolean
  enabled: boolean
  is_raw: boolean
}

export interface AgentCertInfo {
  exists: boolean
  expires_in_days?: number
  valid?: boolean
  common_name?: string
  error?: string
}

export interface AgentPrinterCandidate {
  kind: 'direct' | 'network' | string
  uri: string
  brand: string
  model: string
  queue_suggestion: string
  paper_width_mm: number
}

export interface AgentDetectResult {
  candidates: AgentPrinterCandidate[]
  count?: number
  note?: string
}

export interface AgentInstallStep {
  label: string
  cmd: string
  ok: boolean
  stdout?: string
  stderr?: string
  error?: string
}

export interface AgentInstallResult {
  status: 'installed'
  queue_name: string
  uri: string
  steps: AgentInstallStep[]
}

export interface AgentSystemSetupResult {
  status: 'ok' | 'error'
  package_manager: string
  elevation: string
  user: string | null
  packages: string[]
  returncode: number
  stdout: string
  stderr: string
  needs_relogin: boolean
}

export interface AgentSpoolerRepairResult {
  status: 'ok' | 'error'
  running: boolean
  was_running: boolean
  message: string
  steps: unknown[]
}

export interface AgentDiagnostics {
  version: string
  os: string
  os_release?: string
  python?: string
  cert: AgentCertInfo
  win32print_available?: boolean
  spooler_running?: boolean
  win32print_error?: string
  cups_daemon_running?: boolean
  lp_path?: string | null
  lpstat_path?: string | null
  lpadmin_path?: string | null
  queues_count?: number
  queues?: AgentCupsQueue[]
  raw_queues_count?: number
  issues: string[]
  warnings: string[]
  healthy: boolean
}

export function detectOS(): 'windows' | 'linux' | 'mac' | 'unknown' {
  const ua = navigator.userAgent.toLowerCase()
  if (ua.includes('win')) return 'windows'
  if (ua.includes('mac')) return 'mac'
  if (ua.includes('linux')) return 'linux'
  return 'unknown'
}

export const printerApi = {
  /** Impresoras detectadas por el agente local (https://localhost:9100) */
  getLocalPrinters: async (): Promise<string[]> => {
    try {
      const res = await fetch(`${AGENT_BASE}/printers`, { signal: AbortSignal.timeout(3000) })
      const data = await res.json()
      return data.printers ?? []
    } catch {
      return []
    }
  },

  /** Impresoras CUPS del servidor (Linux server-side) */
  getServerPrinters: async (): Promise<string[]> => {
    try {
      const { data } = await client.get<{ printers?: string[] } | string[]>('/printer/printers')
      return Array.isArray(data) ? data : (data?.printers ?? [])
    } catch {
      return []
    }
  },

  /** Ping al agente local — true si online */
  pingAgent: async (): Promise<boolean> => {
    try {
      const res = await fetch(`${AGENT_BASE}/health`, { signal: AbortSignal.timeout(2000) })
      return res.ok
    } catch {
      return false
    }
  },

  /**
   * GET /diagnostics del agente local — reporte completo para UI.
   * Devuelve null si el agente no responde.
   */
  getDiagnostics: async (): Promise<AgentDiagnostics | null> => {
    try {
      const res = await fetch(`${AGENT_BASE}/diagnostics`, { signal: AbortSignal.timeout(3000) })
      if (!res.ok) return null
      return await res.json()
    } catch {
      return null
    }
  },

  /**
   * GET /printers/detect — escanea dispositivos USB/red con lpinfo
   * y sugiere nombre de cola para cada uno (Linux/macOS solo).
   */
  detectPrinters: async (): Promise<AgentDetectResult> => {
    const res = await agentFetch('/printers/detect', { timeoutMs: 15000 })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Detect error ${res.status}`)
    }
    return res.json()
  },

  /**
   * POST /printers/install — crea cola CUPS en modo raw + enable + accept.
   */
  installPrinter: async (
    uri: string,
    queueName: string,
    setDefault = false,
  ): Promise<AgentInstallResult> => {
    const res = await agentFetch('/printers/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uri, queue_name: queueName, set_default: setDefault }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Install error ${res.status}`)
    }
    return res.json()
  },

  /** POST /printers/{name}/uninstall — elimina cola CUPS. */
  uninstallPrinter: async (queueName: string): Promise<void> => {
    const res = await fetch(`${AGENT_BASE}/printers/${encodeURIComponent(queueName)}/uninstall`, {
      method: 'POST',
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Uninstall error ${res.status}`)
    }
  },

  /** POST /printers/{name}/pause — cupsdisable. */
  pausePrinter: async (queueName: string): Promise<void> => {
    const res = await fetch(`${AGENT_BASE}/printers/${encodeURIComponent(queueName)}/pause`, {
      method: 'POST',
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Pause error ${res.status}`)
    }
  },

  /** POST /printers/{name}/resume — cupsenable + cupsaccept. */
  resumePrinter: async (queueName: string): Promise<void> => {
    const res = await fetch(`${AGENT_BASE}/printers/${encodeURIComponent(queueName)}/resume`, {
      method: 'POST',
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Resume error ${res.status}`)
    }
  },

  /** POST /printers/{name}/clear-queue — cancela trabajos pendientes. */
  clearPrinterQueue: async (queueName: string): Promise<number> => {
    const res = await fetch(`${AGENT_BASE}/printers/${encodeURIComponent(queueName)}/clear-queue`, {
      method: 'POST',
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Clear-queue error ${res.status}`)
    }
    const data = await res.json() as { cancelled_jobs?: number }
    return data.cancelled_jobs ?? 0
  },

  /**
   * POST /printers/test-print — imprime ticket de prueba auto-contenido
   * generado por el agente (no requiere backend).
   */
  testPrintOnQueue: async (queueName: string, paperWidthMm = 80): Promise<void> => {
    const res = await agentFetch('/printers/test-print', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ printer_name: queueName, paper_width_mm: paperWidthMm }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Test-print error ${res.status}`)
    }
  },

  /**
   * POST /system/setup — actualiza el sistema e instala CUPS + drivers de
   * impresora vía el gestor de paquetes (pide autorización gráfica con pkexec).
   * Solo Linux. Puede tardar varios minutos.
   */
  systemSetup: async (includeDrivers = true): Promise<AgentSystemSetupResult> => {
    const res = await agentFetch('/system/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include_drivers: includeDrivers }),
      timeoutMs: 600_000,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Setup error ${res.status}`)
    }
    return res.json()
  },

  /**
   * POST /system/spooler-repair — Windows: deja el Print Spooler en automático
   * y lo arranca (pide elevación UAC si hace falta).
   */
  repairSpooler: async (): Promise<AgentSpoolerRepairResult> => {
    const res = await agentFetch('/system/spooler-repair', { method: 'POST', timeoutMs: 90_000 })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Spooler error ${res.status}`)
    }
    return res.json()
  },

  /** URL de descarga del agente por plataforma */
  downloadAgentUrl: (platform: 'windows' | 'linux' | 'mac'): string =>
    `/api/printer/download-agent?platform=${platform}`,

  /**
   * Ticket de prueba en base64 desde backend. Acepta override opcional para
   * que la prueba refleje la impresora/ancho seleccionados en la UI aunque
   * todavía no se hayan guardado en la sucursal.
   */
  testPrintBase64: async (opts?: { printerName?: string | null; paperWidthMm?: number }): Promise<string> => {
    const body: Record<string, unknown> = {}
    if (opts?.printerName) body.printer_name = opts.printerName
    if (opts?.paperWidthMm) body.paper_width_mm = opts.paperWidthMm
    const { data } = await client.post<{ content_base64?: string; base64?: string }>(
      '/printer/test-print', body
    )
    return data.content_base64 ?? data.base64 ?? ''
  },

  /** Enviar base64 al agente local para imprimir */
  printViaAgent: async (printerName: string, base64: string): Promise<void> => {
    const res = await agentFetch('/print', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ printer_name: printerName, content_base64: base64 }),
      timeoutMs: 8000,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Agent error ${res.status}`)
    }
  },

  /** Abrir el cajón de dinero sin imprimir. Usa el mismo canal que /print. */
  openDrawerViaAgent: async (printerName: string): Promise<void> => {
    const res = await agentFetch('/drawer/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ printer_name: printerName }),
      timeoutMs: 8000,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(err?.detail ?? `Agent error ${res.status}`)
    }
  },

  /**
   * Track 4: TODA la impresión va por agente local. El backend solo genera
   * los bytes ESC/POS. Server-side CUPS deprecado.
   */

  /** Obtener ticket NUEVO en base64 (sin leyenda de reimpresión) */
  getNewTicketBase64: async (saleId: string): Promise<string> => {
    const { data } = await client.post<{ content_base64?: string; base64?: string }>(
      '/printer/print-ticket',
      { order_id: saleId }
    )
    return data.content_base64 ?? data.base64 ?? ''
  },

  /**
   * Obtener ticket en base64 para REimprimir (incluye leyenda COPIA).
   *
   * `pin` es la contraseña de un supervisor: el backend exige rol gerencial o
   * PIN para reimprimir (app/services/reprint_auth.py). Sin él responde 428 —
   * ver src/utils/reimpresion.ts.
   */
  getTicketBase64: async (saleId: string, pin?: string): Promise<string> => {
    const { data } = await client.post<{ content_base64?: string; base64?: string }>(
      `/printer/reprint-ticket/${saleId}`,
      pin ? { pin } : {}
    )
    return data.content_base64 ?? data.base64 ?? ''
  },

  /** Reimprimir ticket → bytes en base64 (caller envía a agente local) */
  reprintTicket: async (saleId: string, pin?: string): Promise<string> => {
    const { data } = await client.post<{ content_base64?: string; base64?: string }>(
      `/printer/reprint-ticket/${saleId}`,
      pin ? { pin } : {}
    )
    return data.content_base64 ?? data.base64 ?? ''
  },

  /** Obtener corte de caja en base64 para imprimir vía agente local */
  getCashCutBase64: async (sessionId: number): Promise<string> => {
    const { data } = await client.post<{ content_base64?: string; base64?: string }>(
      '/printer/print-cash-cut',
      { session_id: sessionId }
    )
    return data.content_base64 ?? data.base64 ?? ''
  },

  /**
   * Imprimir corte de caja end-to-end: pide bytes al backend y los envía
   * al agente local. Reemplaza al antiguo `printCashCut(server)`.
   */
  printCashCut: async (sessionId: number, printerName: string): Promise<void> => {
    const b64 = await printerApi.getCashCutBase64(sessionId)
    if (!b64) throw new Error('No se pudo generar el corte (bytes vacíos).')
    await printerApi.printViaAgent(printerName, b64)
  },
}
