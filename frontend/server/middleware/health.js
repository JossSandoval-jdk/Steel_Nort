// Endpoint de health check blindado.
import { existsSync } from 'node:fs'
import http from 'node:http'
import https from 'node:https' // Añadido soporte seguro para HTTPS
import { logger } from './logger.js'

// Validación estricta y segura del entorno para prevenir SSRF básico
const RAW_BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8089'

let VALID_BACKEND_URL
try {
  const parsed = new URL(RAW_BACKEND_URL)
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('Esquema de URL no permitido para el backend.')
  }
  VALID_BACKEND_URL = parsed
} catch (err) {
  logger.error(`[Security] BACKEND_URL inválida o insegura: ${err.message}`)
  VALID_BACKEND_URL = new URL('http://localhost:8089') // Fallback seguro
}

function checkBackend() {
  return new Promise((resolve) => {
    try {
      const client = VALID_BACKEND_URL.protocol === 'https:' ? https : http
      
      const req = client.get(VALID_BACKEND_URL, (res) => {
        res.resume()
        resolve({
          ok: res.statusCode < 500,
          statusCode: res.statusCode,
        })
      })

      req.setTimeout(3000, () => {
        req.destroy()
        resolve({ ok: false, statusCode: 0, error: 'timeout' })
      })

      req.on('error', (err) => {
        const safeMessage = typeof err.message === 'string' ? err.message.replace(/[\r\n]/g, '') : 'unknown_error'
        resolve({ ok: false, statusCode: 0, error: safeMessage })
      })
    } catch (err) {
      // Uso de 'err' para evitar la alerta del linter y registrar el fallo síncrono
      logger.debug(`Excepción síncrona en checkBackend: ${err.message}`)
      resolve({ ok: false, statusCode: 0, error: 'execution_exception' })
    }
  })
}

export function healthHandler({ port, distDir }) {
  // Opcional recomendado: sanitizar valores de entrada
  const safePort = Number.isInteger(Number(port)) ? port : 3000
  const safeDistDir = typeof distDir === 'string' ? distDir : null

  return async (_req, res) => {
    const backend = await checkBackend()
    const distReady = safeDistDir ? existsSync(safeDistDir) : false

    // Evitar loguear objetos completos no saneados
    logger.debug(`Health check ejecutado. Backend status: ${backend.statusCode}`)

    res.status(backend.ok ? 200 : 503).json({
      status: backend.ok ? 'ok' : 'degraded',
      app: 'SteelNort Serve',
      uptime: process.uptime(),
      port: safePort,
      distReady,
      backend: { 
        url: VALID_BACKEND_URL.origin, // Ocultar credenciales si las hubiera en la URL
        ok: backend.ok,
        statusCode: backend.statusCode,
        ...(backend.error ? { error: backend.error } : {})
      },
    })
  }
}