// Seguridad de archivos y cabeceras HTTP (Blindado).
import path from 'node:path'
import helmet from 'helmet'
import { logger } from './logger.js'

const SENSITIVE_PATTERNS = [
  /(^|\/)\.env(\..*)?$/i,
  /(^|\/)\.git(\/|$)/i,
  /(^|\/)\.svn(\/|$)/i,
  /(^|\/)\.hg(\/|$)/i,
  /node_modules(\/|$)/i,
  /\.venv(\/|$)/i,
  /__pycache__(\/|$)/i,
  /\.pyc$/i,
  /\.pem$/i,
  /\.key$/i,
  /\.crt$/i,
  /\.p12$/i,
  /\.\.(htaccess|htpasswd)$/i,
  /package-lock\.json$/i,
  /\.DS_Store$/i,
  /(^|\/)logs?(\/|$)/i,
]

function matchesSensitive(value) {
  return SENSITIVE_PATTERNS.some((re) => re.test(value))
}

const isProduction = process.env.NODE_ENV === 'production'

// Helmet: cabeceras de seguridad endurecidas y adaptadas por entorno
export const securityHeaders = helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      baseUri: ["'self'"],
      objectSrc: ["'none'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", 'data:'],
      // Restringe conexiones de desarrollo en producción
      connectSrc: isProduction 
        ? ["'self'"] 
        : ["'self'", 'ws://localhost:3000', 'http://localhost:5173', 'ws://localhost:5173'],
      fontSrc: ["'self'"],
      frameAncestors: ["'none'"],
      formAction: ["'self'"],
      upgradeInsecureRequests: [],
    },
  },
  crossOriginEmbedderPolicy: false,
  referrerPolicy: { policy: 'same-origin' },
  hsts: isProduction
    ? { maxAge: 31536000, includeSubDomains: true, preload: true }
    : false,
})

// Bloquea rutas que pidan archivos sensibles de forma blindada
export function denySensitiveFiles(req, res, next) {
  let pathname = req.path || ''

  try {
    pathname = decodeURIComponent(pathname)
  } catch (err) {
    const clientIp = typeof req.ip === 'string' ? req.ip.replace(/[\r\n]/g, '') : 'unknown'
    logger.warn(`Intento de acceso con URI malformada bloqueado: ${req.method} (${clientIp}) - Error: ${err.message}`)
    return res.status(400).json({
      detail: 'Solicitud inválida.',
    })
  }

  const normalizedPath = pathname.replace(/\\/g, '/')

  if (matchesSensitive(normalizedPath)) {
    const clientIp = typeof req.ip === 'string' ? req.ip.replace(/[\r\n]/g, '') : 'unknown'
    logger.warn(`Acceso bloqueado a archivo sensible: ${req.method} ${normalizedPath} (${clientIp})`)
    return res.status(403).json({
      detail: 'Acceso denegado: ruta reservada del sistema.',
    })
  }

  next()
}

// Opciones de express.static endurecidas
export const staticOptions = {
  dotfiles: 'deny',
  index: false,
  setHeaders(res, filePath) {
    if (filePath.includes(`${path.sep}assets${path.sep}`)) {
      res.setHeader('Cache-Control', 'public, max-age=31536000, immutable')
    } else {
      res.setHeader('Cache-Control', 'no-cache')
    }
    res.setHeader('X-Content-Type-Options', 'nosniff')
  },
}