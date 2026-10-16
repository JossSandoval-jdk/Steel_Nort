// Endpoint de health check blindado.
import { existsSync } from 'node:fs'
import http from 'node:http'
import https from 'node:https'
import { logger } from './logger.js'

const IS_PRODUCTION = process.env.NODE_ENV === 'production'

// --- Validación de BACKEND_URL ---
const RAW_BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8200'
const FALLBACK_URL = 'http://localhost:8200'

function parseBackendUrl(raw) {
  try {
    const parsed = new URL(raw)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      throw new Error('Esquema no permitido (solo http/https).')
    }
    if (parsed.username || parsed.password) {
      throw new Error('Credenciales embebidas en la URL no permitidas.')
    }
    return parsed
  } catch (err) {
    logger.error(`[health] BACKEND_URL inválida: ${err.message}`)
    if (IS_PRODUCTION) {
      // En producción, no arranques con URL insegura.
      // Se adjunta 'cause' para preservar el error original (regla ESLint preserve-caught-error).
      throw new Error('BACKEND_URL inválida en producción. Abortando.', { cause: err })
    }
    return new URL(FALLBACK_URL)
  }
}

const VALID_BACKEND_URL = parseBackendUrl(RAW_BACKEND_URL)

// --- Caché del resultado ---
// Evita martillear al backend con múltiples health checks concurrentes.
const CACHE_TTL_MS = Number(process.env.HEALTH_CACHE_TTL_MS) || 5000
let cache = { at: 0, result: null }
let inflight = null

function getCachedOrFetch(fetchFn) {
  const now = Date.now()

  // 1. Si hay caché válido, devuélvelo
  if (cache.result && now - cache.at < CACHE_TTL_MS) {
    return Promise.resolve({ ...cache.result, cached: true })
  }

  // 2. Si hay una petición en vuelo, compártela (evita thundering herd)
  if (inflight) return inflight

  // 3. Nueva consulta
  inflight = fetchFn()
    .then((result) => {
      cache = { at: Date.now(), result }
      return result
    })
    .finally(() => {
      inflight = null
    })

  return inflight
}

// --- Comprobación del backend ---
function checkBackend() {
  return new Promise((resolve) => {
    const controller = new AbortController()
    const totalTimeoutMs = Number(process.env.HEALTH_TIMEOUT_MS) || 3000

    const timer = setTimeout(() => {
      controller.abort()
      resolve({ ok: false, statusCode: 0, error: 'timeout' })
    }, totalTimeoutMs)

    try {
      const client = VALID_BACKEND_URL.protocol === 'https:' ? https : http

      const req = client.get(
        VALID_BACKEND_URL,
        {
          signal: controller.signal,
          headers: { connection: 'close' },
        },
        (res) => {
          res.resume() // drena el body para liberar el socket
          clearTimeout(timer)
          resolve({
            ok: res.statusCode < 500,
            statusCode: res.statusCode,
          })
        }
      )

      req.on('error', (err) => {
        clearTimeout(timer)
        if (err.name === 'AbortError') return
        const safeMessage =
          typeof err.message === 'string'
            ? err.message.replace(/[\r\n]/g, '').slice(0, 200)
            : 'unknown_error'
        resolve({ ok: false, statusCode: 0, error: safeMessage })
      })
    } catch (err) {
      clearTimeout(timer)
      logger.debug(`Excepción síncrona en checkBackend: ${err.message}`)
      resolve({ ok: false, statusCode: 0, error: 'execution_exception' })
    }
  })
}

// --- Handler de health ---
export function healthHandler({ port, distDir } = {}) {
  const safePort = Number.isInteger(Number(port)) ? Number(port) : 3000
  const safeDistDir = typeof distDir === 'string' ? distDir : null

  // existsSync se llama una vez al arrancar, no en cada request
  const distReady = safeDistDir ? existsSync(safeDistDir) : false

  return async (_req, res) => {
    const backend = await getCachedOrFetch(checkBackend)

    // Log a debug solo si NO viene de caché, para no spamear
    if (!backend.cached) {
      logger.debug(
        `Health check ejecutado. Backend status: ${backend.statusCode}`
      )
    }

    const httpStatus = backend.ok ? 200 : 503

    // En producción, respuesta mínima (sin fugas)
    if (IS_PRODUCTION) {
      return res.status(httpStatus).json({
        status: backend.ok ? 'ok' : 'degraded',
      })
    }

    // En desarrollo, respuesta detallada para debugging
    return res.status(httpStatus).json({
      status: backend.ok ? 'ok' : 'degraded',
      app: 'SteelNort Serve',
      uptime: process.uptime(),
      port: safePort,
      distReady,
      backend: {
        ok: backend.ok,
        statusCode: backend.statusCode,
        cached: !!backend.cached,
        ...(backend.error ? { error: backend.error } : {}),
      },
    })
  }
}