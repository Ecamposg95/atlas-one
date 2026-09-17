/**
 * Offline queue para ventas POS usando IndexedDB nativo.
 *
 * Cuando `POST /api/sales` falla por error de red (no por 4xx/5xx del backend),
 * la venta se persiste aquí y se reintenta al reconectar.
 *
 * IDEMPOTENCIA: cada intento de cobro lleva un `client_uuid` en el payload
 * (ver POS.tsx). Como aquí el payload se guarda y se reenvía tal cual, el
 * reintento llega con el MISMO valor y el backend devuelve la venta original
 * en vez de crear un ticket duplicado.
 *
 * La espera de 2 min de `flushPending` se conserva como segunda barrera: cubre
 * los payloads encolados por versiones anteriores del POS, que no traen
 * `client_uuid`.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { formatCurrency } from './currency'
import { errorDetailText } from './errorDetail'

const DB_NAME = 'atlas_pos_offline'
const DB_VERSION = 1
const STORE = 'pending_sales'

/** Mínimo tiempo de espera antes de reintentar una venta encolada (ms). */
export const REPLAY_MIN_AGE_MS = 2 * 60 * 1000 // 2 min

export interface PendingSale {
  id: string // UUID v4 generado en cliente
  payload: unknown // body tal como se mandaría a POST /api/sales
  enqueued_at: number // epoch ms
  attempts: number
  last_error?: string
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'))
  })
}

function tx(db: IDBDatabase, mode: IDBTransactionMode): IDBObjectStore {
  return db.transaction(STORE, mode).objectStore(STORE)
}

function uuid(): string {
  // crypto.randomUUID es estándar en navegadores modernos; fallback seguro.
  const c: any = globalThis.crypto
  if (c?.randomUUID) return c.randomUUID()
  // RFC4122 v4 fallback
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0
    const v = ch === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export async function enqueueSale(payload: unknown): Promise<PendingSale> {
  const entry: PendingSale = {
    id: uuid(),
    payload,
    enqueued_at: Date.now(),
    attempts: 0,
  }
  const db = await openDB()
  await new Promise<void>((resolve, reject) => {
    const req = tx(db, 'readwrite').add(entry)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })
  db.close()
  return entry
}

export async function listPending(): Promise<PendingSale[]> {
  const db = await openDB()
  const items = await new Promise<PendingSale[]>((resolve, reject) => {
    const req = tx(db, 'readonly').getAll()
    req.onsuccess = () => resolve((req.result ?? []) as PendingSale[])
    req.onerror = () => reject(req.error)
  })
  db.close()
  return items.sort((a, b) => a.enqueued_at - b.enqueued_at)
}

export async function removePending(id: string): Promise<void> {
  const db = await openDB()
  await new Promise<void>((resolve, reject) => {
    const req = tx(db, 'readwrite').delete(id)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })
  db.close()
}

async function updatePending(entry: PendingSale): Promise<void> {
  const db = await openDB()
  await new Promise<void>((resolve, reject) => {
    const req = tx(db, 'readwrite').put(entry)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })
  db.close()
}

/**
 * Detecta si un error de Axios es de red (no respuesta HTTP del server).
 * Solo estos deben encolar o mantener la venta en la cola.
 */
export function isNetworkError(err: any): boolean {
  if (!err) return false
  // Axios: si hay response, el servidor respondió (aunque sea 4xx/5xx).
  if (err.response) return false
  const code = err.code as string | undefined
  if (code === 'ECONNABORTED' || code === 'ERR_NETWORK' || code === 'ETIMEDOUT') return true
  const msg = (err.message ?? '').toString().toLowerCase()
  if (msg.includes('network error') || msg.includes('timeout') || msg.includes('failed to fetch')) return true
  // offline según el navegador
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true
  return false
}

export interface FlushResult {
  sent: number
  dropped: number // 4xx (inválidas o duplicadas) — se quitan y se loggea
  kept: number // siguen pendientes (sin red aún o muy recientes)
  /**
   * Un aviso por cada venta descartada, con monto y motivo. El contador no
   * basta: ese cobro YA ocurrió en el mundo real y no va a quedar registrado
   * en ningún lado, así que la cajera tiene que enterarse de cuál fue y por
   * qué (ver `droppedSaleMessage`).
   */
  droppedMessages: string[]
}

/** Lo que el cliente pagó según el payload encolado. 0 si no se puede leer. */
function paidAmountOf(payload: unknown): number {
  const pagos = (payload as { payments?: unknown })?.payments
  if (!Array.isArray(pagos)) return 0
  const suma = pagos.reduce((s: number, p: any) => s + (Number(p?.amount) || 0), 0)
  return Number.isFinite(suma) ? suma : 0
}

/**
 * Aviso para una venta encolada que el backend rechazó con 4xx.
 *
 * Se descarta a propósito (reintentarla daría el mismo 4xx para siempre), pero
 * el cobro ya ocurrió: el cliente pagó y se llevó la mercancía. Un
 * `console.warn` deja ese descuadre invisible, así que el texto lleva el monto
 * y el motivo para que la cajera lo capture a mano o llame al gerente.
 *
 * El caso real que lo dispara: el administrador cambia el porcentaje de
 * comisión mientras el POS está sin red; al reconectar, la venta con tarjeta
 * encolada trae el importe viejo y el backend la rechaza con 422.
 */
export function droppedSaleMessage(entry: PendingSale, err: any): string {
  const monto = formatCurrency(paidAmountOf(entry?.payload))
  const status = err?.response?.status
  const motivo = errorDetailText(
    err?.response?.data?.detail,
    status ? `el servidor la rechazó (HTTP ${status})` : 'el servidor la rechazó',
  )
  return `No se pudo registrar la venta de ${monto}: ${motivo}`
}

/**
 * Recorre la cola y reintenta cada venta vía `poster`.
 * - 200 OK → remove
 * - 4xx   → remove + console.warn (likely duplicate/invalid)
 * - 5xx   → keep (backend problem, retry later)
 * - network error → keep (still offline)
 * - edad < REPLAY_MIN_AGE_MS → skip (kept)
 */
export async function flushPending(
  poster: (payload: unknown) => Promise<unknown>,
): Promise<FlushResult> {
  const result: FlushResult = { sent: 0, dropped: 0, kept: 0, droppedMessages: [] }
  let pending: PendingSale[]
  try {
    pending = await listPending()
  } catch (e) {
    console.warn('[offlineQueue] listPending failed:', e)
    return result
  }

  const now = Date.now()
  for (const entry of pending) {
    // Defensive: si la venta fue encolada hace <2min, deja que el POST online
    // que acaba de disparar el usuario (si lo hubo) termine primero.
    if (now - entry.enqueued_at < REPLAY_MIN_AGE_MS) {
      result.kept++
      continue
    }
    try {
      await poster(entry.payload)
      await removePending(entry.id)
      result.sent++
    } catch (err: any) {
      if (isNetworkError(err)) {
        // Sin conexión, no hay nada que hacer. Mantén para el próximo intento.
        try {
          await updatePending({
            ...entry,
            attempts: entry.attempts + 1,
            last_error: 'network',
          })
        } catch {}
        result.kept++
      } else {
        const status = err?.response?.status as number | undefined
        if (status && status >= 400 && status < 500) {
          // 4xx: payload inválido o duplicado. No tiene sentido reintentar.
          console.warn(
            `[offlineQueue] dropping sale ${entry.id} (HTTP ${status}):`,
            err?.response?.data,
          )
          await removePending(entry.id).catch(() => {})
          result.dropped++
          result.droppedMessages.push(droppedSaleMessage(entry, err))
        } else {
          // 5xx u otro: mantén para reintento posterior.
          try {
            await updatePending({
              ...entry,
              attempts: entry.attempts + 1,
              last_error: status ? `HTTP ${status}` : 'unknown',
            })
          } catch {}
          result.kept++
        }
      }
    }
  }
  return result
}
