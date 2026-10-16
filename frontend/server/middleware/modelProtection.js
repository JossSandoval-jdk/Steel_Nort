// middleware/modelProtection.js
// Protección de los artefactos del modelo ML (Blindado v2).
import path from 'node:path'
import { logger } from './logger.js'

// --- Helpers ---

// Sanitiza cualquier string que vaya a ir a un log (evita log injection)
function sanitizeForLog(value) {
  if (typeof value !== 'string') return 'unknown'
  return value.replace(/[\r\n\t]/g, '').slice(0, 500)
}

// Patrones de artefactos ML. Nota: usamos regex sin redundancias.
const MODEL_PATTERNS = [
  // Extensiones típicas de modelos serializados
  /\.joblib$/i,
  /\.pkl$/i,
  /\.pickle$/i,
  /\.h5$/i,          // Keras / TensorFlow
  /\.onnx$/i,        // ONNX
  /\.pt$/i,          // PyTorch
  /\.pth$/i,         // PyTorch legacy
  /\.tflite$/i,      // TensorFlow Lite
  /\.safetensors$/i, // HuggingFace
  /\.cbm$/i,         // CatBoost
  /\.model$/i,       // Genérico

  // Directorios y nombres concretos de tu proyecto
  /(^|\/)(?:ml\/)?artifacts(\/|$)/i,
  /\breglas_umbrales\.csv$/i,
  /\bfeatures_modelo\.csv$/i,
  /\bvariables_correlacion\.csv$/i,
  /\bimportancia_variables\.csv$/i,
]

function matchesModel(value) {
  return MODEL_PATTERNS.some((re) => re.test(value))
}

// Analiza un path y devuelve { safe, normalized } o null si es sospechoso
function analyzePath(rawPath) {
  if (!rawPath || typeof rawPath !== 'string') return null

  let decoded
  try {
    decoded = decodeURIComponent(rawPath)
  } catch {
    return { error: 'malformed' }
  }

  // Normaliza backslashes y resuelve ./../
  let normalized = decoded.replace(/\\/g, '/')
  normalized = path.posix.normalize(normalized)

  // Si después de normalizar aún contiene '..', es traversal
  if (normalized.includes('..')) {
    return { error: 'traversal', normalized }
  }

  return { safe: true, normalized }
}

// --- Middleware ---

export function protectModel(req, res, next) {
  const clientIp = sanitizeForLog(req.ip)
  const method = sanitizeForLog(req.method)

  // Analizamos tanto req.path como req.originalUrl (sin query string)
  const pathsToCheck = [
    req.path,
    req.originalUrl ? req.originalUrl.split('?')[0] : null,
  ].filter(Boolean)

  for (const rawPath of pathsToCheck) {
    const result = analyzePath(rawPath)

    if (!result) continue

    if (result.error === 'malformed') {
      logger.warn(
        `Intento de acceso con URI malformada bloqueado: ${method} (${clientIp})`
      )
      return res.status(400).json({ detail: 'Solicitud inválida.' })
    }

    if (result.error === 'traversal') {
      logger.warn(
        `Path traversal detectado: ${method} ${sanitizeForLog(result.normalized)} (${clientIp})`
      )
      return res.status(403).json({ detail: 'Ruta inválida.' })
    }

    if (matchesModel(result.normalized)) {
      logger.warn(
        `Acceso a artefacto ML bloqueado: ${method} ${sanitizeForLog(result.normalized)} (${clientIp})`
      )
      return res.status(403).json({
        detail: 'Acceso denegado: recursos del modelo ML son privados.',
      })
    }
  }

  next()
}