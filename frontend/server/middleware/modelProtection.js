// Proteccion de los artefactos del modelo ML (Blindado).
import { logger } from './logger.js'

const MODEL_PATTERNS = [
  /\bmodelo_isolation_forest\.joblib$/i,
  /\bscaler\.joblib$/i,
  /\.joblib$/i,
  /\.pkl$/i,
  /\.pickle$/i,
  /(^|\/)(?:ml\/)?artifacts(\/|$)/i,
  /\breglas_umbrales\.csv$/i,
  /\bfeatures_modelo\.csv$/i,
  /\bvariables_correlacion\.csv$/i,
  /\bimportancia_variables\.csv$/i,
]

function matchesModel(value) {
  return MODEL_PATTERNS.some((re) => re.test(value))
}

export function protectModel(req, res, next) {
  let pathname = req.path || ''

  // Protección robusta contra URI malformadas (Previene DoS por URIError)
  try {
    pathname = decodeURIComponent(pathname)
  } catch (err) {
    // Uso de 'err' para evitar la alerta del linter y registrar el motivo técnico
    logger.warn(`Intento de acceso con URI malformada bloqueado: ${req.method} (${req.ip}) - Error: ${err.message}`)
    return res.status(400).json({
      detail: 'Solicitud inválida.',
    })
  }

  // Normalización defensiva para evitar bypasses básicos
  const normalizedPath = pathname.replace(/\\/g, '/')

  if (matchesModel(normalizedPath)) {
    // Sanitizar IP para evitar log injection
    const clientIp = typeof req.ip === 'string' ? req.ip.replace(/[\r\n]/g, '') : 'unknown'
    
    logger.warn(
      `Acceso a artefacto ML bloqueado: ${req.method} ${normalizedPath} (${clientIp})`
    )
    return res.status(403).json({
      detail: 'Acceso denegado: recursos del modelo ML son privados.',
    })
  }

  next()
}