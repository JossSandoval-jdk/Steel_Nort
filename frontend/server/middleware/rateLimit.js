// Limitacion de peticiones (rate limiting) por IP.
import rateLimit, { ipKeyGenerator } from 'express-rate-limit'

// Validación defensiva y segura de la ventana de tiempo (fallback a 15 minutos)
const rawWindowMin = Number(process.env.RATE_LIMIT_WINDOW_MIN)
const windowMs = (Number.isInteger(rawWindowMin) && rawWindowMin > 0 ? rawWindowMin : 15) * 60 * 1000

function jsonHandler(message) {
  return (_req, res) => {
    res.status(429).json({ detail: message })
  }
}

const baseOptions = {
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: ipKeyGenerator,
}

// Función auxiliar segura para parsear límites máximos con fallback
function getLimit(envValue, defaultValue) {
  const parsed = Number(envValue)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : defaultValue
}

export const apiLimiter = rateLimit({
  ...baseOptions,
  windowMs,
  limit: getLimit(process.env.RATE_LIMIT_API_MAX, 1000),
  skip: (req) => req.path.startsWith('/api/telemetria/muestras'),
  handler: jsonHandler(
    'Demasiadas peticiones a la API. Intente de nuevo mas tarde.'
  ),
})

export const authLimiter = rateLimit({
  ...baseOptions,
  windowMs,
  limit: getLimit(process.env.RATE_LIMIT_AUTH_MAX, 20),
  handler: jsonHandler(
    'Demasiados intentos de autenticacion. Espere unos minutos.'
  ),
})

// Rutas del modelo: consultar metadatos y disparar reentrenamiento.
export const modelLimiter = rateLimit({
  ...baseOptions,
  windowMs,
  limit: getLimit(process.env.RATE_LIMIT_MODEL_MAX, 60),
  handler: jsonHandler(
    'Demasiadas peticiones de configuracion del modelo ML.'
  ),
})

// Ingesta del daemon: unificado con el formato JSON estándar de la aplicación
export const ingestLimiter = rateLimit({
  ...baseOptions,
  windowMs,
  limit: getLimit(process.env.RATE_LIMIT_INGEST_MAX, 2000),
  handler: jsonHandler(
    'Demasiadas muestras de telemetria enviadas. Superado el limite del daemon.'
  ),
})