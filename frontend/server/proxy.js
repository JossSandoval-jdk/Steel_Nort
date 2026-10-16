// Proxy reverso hacia el backend FastAPI (Blindado v2).
import { createProxyMiddleware } from 'http-proxy-middleware'
import { logger } from './middleware/logger.js'   // ✅ BIEN

const isProduction = process.env.NODE_ENV === 'production'

// --- Validación de BACKEND_URL (misma lógica que health.js) ---
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
    logger.error(`[proxy] BACKEND_URL inválida: ${err.message}`)
    if (isProduction) {
      throw new Error('BACKEND_URL inválida en producción. Abortando.', { cause: err })
    }
    return new URL(FALLBACK_URL)
  }
}

const BACKEND_URL = parseBackendUrl(RAW_BACKEND_URL)

// --- Timeout ---
const RAW_TIMEOUT = Number(process.env.PROXY_TIMEOUT_MS)
const TIMEOUT_MS =
  Number.isInteger(RAW_TIMEOUT) && RAW_TIMEOUT > 0 ? RAW_TIMEOUT : 30_000

// --- Sanitización para logs ---
function sanitizeForLog(value) {
  if (typeof value !== 'string') return 'unknown'
  // eslint-disable-next-line no-control-regex
  return value.replace(/[\u0000-\u001f\u007f]|\u001b\[[0-9;]*[A-Za-z]/g, '_').slice(0, 500)
}

// Headers que NO deben llegar al backend tal cual vienen del cliente.
// OJO: la cookie NO se elimina; la API v2 necesita la cookie "csrf_token" para
// validar el doble-envio del token CSRF (S1-8).
const STRIP_REQUEST_HEADERS = [
  'x-forwarded-for',
  'x-forwarded-host',
  'x-forwarded-proto',
  'x-real-ip',
]

// Headers del backend que NO deben llegar al cliente (revelan infra)
const STRIP_RESPONSE_HEADERS = [
  'x-powered-by',
  'server',
  'x-aspnet-version',
  'x-aspnetmvc-version',
]

// --- Proxy ---
export const proxyApi = createProxyMiddleware({
  target: BACKEND_URL,

  // Reescribe el Host header al del backend (necesario para FastAPI/VirtualHost)
  changeOrigin: true,

  // Añade X-Forwarded-* automáticamente (útil si FastAPI los necesita)
  xfwd: true,

  // Timeouts
  timeout: TIMEOUT_MS,
  proxyTimeout: TIMEOUT_MS,

  // WebSocket: activado, pero DEBES autenticar el upgrade en server.js
  // (ver nota al final). El middleware chain no corre en upgrades WS.
  ws: true,

  // --- Path rewrite ---
  // Express monta este proxy con app.use('/api', proxyApi). Antes de llegar
  // aquí, Express ya le quitó el '/api' a req.url. Por eso lo re-añadimos.
  // Resultado: el cliente pide /api/v2/telemetria/push → FastAPI recibe
  // /api/v2/telemetria/push.
  pathRewrite: (path) => (path.startsWith('/api') ? path : `/api${path}`),

  on: {
    // --- 1. Antes de enviar al backend: limpiar headers peligrosos ---
    proxyReq: (proxyReq) => {
      for (const h of STRIP_REQUEST_HEADERS) {
        proxyReq.removeHeader(h)
      }

      // Elimina headers condicionales de caché que podrían causar
      // respuestas inconsistentes si el backend los interpreta
      proxyReq.removeHeader('if-none-match')
      proxyReq.removeHeader('if-modified-since')
    },

    // --- 2. Al recibir la respuesta: limpiar headers que revelan infra ---
    proxyRes: (proxyRes) => {
      for (const h of STRIP_RESPONSE_HEADERS) {
        delete proxyRes.headers[h]
      }
    },

    // --- 3. Errores de comunicación ---
    error: (err, req, res) => {
      const method = sanitizeForLog(req?.method)
      const url = sanitizeForLog(req?.originalUrl)
      const code = err?.code || 'UNKNOWN'

      logger.error(
        `[proxy] Error hacia FastAPI: ${code} en ${method} ${url} - ${sanitizeForLog(err?.message)}`
      )

      if (!res || res.headersSent) return
      if (typeof res.writeHead !== 'function') {
        // Es un socket WebSocket, no una respuesta HTTP
        try { res.destroy?.() } catch { /* ignore */ }
        return
      }

      // Mensajes específicos según el tipo de error
      let detail
      let status = 502

      if (err?.code === 'ECONNREFUSED') {
        detail = isProduction
          ? 'Servicio no disponible temporalmente.'
          : `Backend no responde en ${BACKEND_URL.origin} (ECONNREFUSED)`
        status = 503
      } else if (err?.code === 'ETIMEDOUT' || err?.code === 'ESOCKETTIMEDOUT') {
        detail = isProduction
          ? 'Servicio no disponible temporalmente.'
          : `Timeout esperando a ${BACKEND_URL.origin}`
        status = 504
      } else if (err?.code === 'ECONNRESET') {
        detail = 'Conexión interrumpida.'
        status = 502
      } else {
        detail = isProduction
          ? 'Error de comunicación con el servicio de backend.'
          : `Error del proxy: ${err?.message || 'desconocido'}`
      }

      res.status(status).json({ detail })
    },
  },
})