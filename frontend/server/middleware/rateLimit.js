// middleware/rateLimit.js
// Limitación de peticiones (rate limiting) por IP, con stores en memoria.
import rateLimit from 'express-rate-limit'
import { logger } from './logger.js'

// --- Helpers de configuración ---

const rawWindowMin = Number(process.env.RATE_LIMIT_WINDOW_MIN)
const windowMs =
  (Number.isInteger(rawWindowMin) && rawWindowMin > 0 ? rawWindowMin : 15) *
  60 * 1000

const rawAuthWindowMin = Number(process.env.RATE_LIMIT_AUTH_WINDOW_MIN)
const authWindowMs =
  (Number.isInteger(rawAuthWindowMin) && rawAuthWindowMin > 0
    ? rawAuthWindowMin
    : 60) *
  60 * 1000

function getLimit(envValue, defaultValue) {
  const parsed = Number(envValue)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : defaultValue
}

// Handler que loguea + responde JSON
function jsonHandler(message, scope) {
  return (req, res) => {
    const clientIp =
      typeof req.ip === 'string' ? req.ip.replace(/[\r\n]/g, '') : 'unknown'
    logger.warn(
      `[rateLimit:${scope}] Bloqueado: ${req.method} ${req.originalUrl} (${clientIp})`
    )
    res.status(429).json({ detail: message })
  }
}

// Opciones base compartidas
const baseOptions = {
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  skip: (req) => req.method === 'OPTIONS',
  // NO pasamos keyGenerator: express-rate-limit ya usa ipKeyGenerator por defecto.
}

// --- Limiters ---

// General para toda la API
export const apiLimiter = rateLimit({
  ...baseOptions,
  windowMs,
  limit: getLimit(process.env.RATE_LIMIT_API_MAX, 1000),
  handler: jsonHandler(
    'Demasiadas peticiones a la API. Intente de nuevo más tarde.',
    'api'
  ),
})

// Autenticación: ventana larga + solo cuenta fallos
export const authLimiter = rateLimit({
  ...baseOptions,
  windowMs: authWindowMs,
  limit: getLimit(process.env.RATE_LIMIT_AUTH_MAX, 20),
  skipSuccessfulRequests: true, // ← solo cuenta intentos fallidos
  handler: jsonHandler(
    'Demasiados intentos de autenticación. Espere unos minutos.',
    'auth'
  ),
})

// Modelo ML: consultas de metadatos y reentrenamiento
export const modelLimiter = rateLimit({
  ...baseOptions,
  windowMs,
  limit: getLimit(process.env.RATE_LIMIT_MODEL_MAX, 60),
  handler: jsonHandler(
    'Demasiadas peticiones de configuración del modelo ML.',
    'model'
  ),
})

// Ingesta del daemon de telemetría
export const ingestLimiter = rateLimit({
  ...baseOptions,
  windowMs,
  limit: getLimit(process.env.RATE_LIMIT_INGEST_MAX, 2000),
  // Solo aceptar ingestas desde localhost (ajusta según tu despliegue real)
  skip: (req) =>
    req.method === 'OPTIONS' ||
    (req.ip !== '127.0.0.1' && req.ip !== '::1' && req.ip !== '::ffff:127.0.0.1'),
  handler: jsonHandler(
    'Demasiadas muestras de telemetría. Superado el límite del daemon.',
    'ingest'
  ),
})