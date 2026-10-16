// Seguridad de archivos y cabeceras HTTP (Blindado v3).
import path from 'node:path'
import helmet from 'helmet'
import { logger } from './logger.js'

// --- Patrones de archivos/directorios sensibles ---
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
  /\.(htaccess|htpasswd)$/i,
  /package-lock\.json$/i,
  /\.DS_Store$/i,
  /(^|\/)logs?(\/|$)/i,
]

// Métodos HTTP permitidos
const ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']

const isProduction = process.env.NODE_ENV === 'production'

// --- Helpers ---

// Sanitiza cualquier string que vaya a un log (evita log injection)
function sanitizeForLog(value) {
  if (typeof value !== 'string') return 'unknown'
  // eslint-disable-next-line no-control-regex
  return value.replace(/[\u0000-\u001f\u007f]|\u001b\[[0-9;]*[A-Za-z]/g, '_').slice(0, 500)
}

function matchesSensitive(value) {
  return SENSITIVE_PATTERNS.some((re) => re.test(value))
}

// --- Helmet ---
export const securityHeaders = helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      baseUri: ["'self'"],
      objectSrc: ["'none'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"], // TODO: migrar a nonce cuando sea posible
      imgSrc: ["'self'", 'data:'],
      // Dev: permite conexiones al proxy Node (3000) y a Vite (5173)
      connectSrc: isProduction
        ? ["'self'"]
        : [
            "'self'",
            'ws://localhost:5173',
            'http://localhost:5173',
            'ws://localhost:3000',
            'http://localhost:3000',
          ],
      fontSrc: ["'self'"],
      frameAncestors: ["'none'"],
      formAction: ["'self'"],
      // Solo forzar HTTPS en producción: en dev rompería localhost
      upgradeInsecureRequests: isProduction ? [] : null,
    },
  },
  crossOriginEmbedderPolicy: false,
  referrerPolicy: { policy: 'same-origin' },
  hsts: isProduction
    ? { maxAge: 31536000, includeSubDomains: true, preload: true }
    : false,
})

// --- Bloqueo de archivos sensibles + path traversal + métodos raros ---
export function denySensitiveFiles(req, res, next) {
  const clientIp = sanitizeForLog(req.ip)

  // 1. Método HTTP permitido
  if (!ALLOWED_METHODS.includes(req.method)) {
    logger.warn(`Método HTTP no permitido: ${sanitizeForLog(req.method)} (${clientIp})`)
    return res.status(405).json({ detail: 'Método no permitido.' })
  }

  // 2. Decodificar con seguridad (bloquea URIs malformadas)
  let pathname = req.path || ''
  try {
    pathname = decodeURIComponent(pathname)
  } catch {
    logger.warn(`URI malformada bloqueada: ${sanitizeForLog(req.method)} (${clientIp})`)
    return res.status(400).json({ detail: 'Solicitud inválida.' })
  }

  // 3. Normalizar backslashes (sin resolver todavía los "..")
  let normalizedPath = pathname.replace(/\\/g, '/')

  // 4. Bloquear path traversal ANTES de normalizar.
  //    path.posix.normalize() ELIMINA los "..", por eso hay que detectarlos aquí.
  //    Cubre: "/api/../x", "/api/..%2f..%2fx" (ya decodificado), "/..", ".."
  if (/(^|\/)\.\.(\/|$)/.test(normalizedPath)) {
    logger.warn(
      `Path traversal detectado: ${sanitizeForLog(req.method)} ${sanitizeForLog(normalizedPath)} (${clientIp})`
    )
    return res.status(403).json({ detail: 'Ruta inválida.' })
  }

  // 5. Ahora sí, normalizar para el check de archivos sensibles
  normalizedPath = path.posix.normalize(normalizedPath)

  // 6. Bloquear archivos/directorios sensibles
  if (matchesSensitive(normalizedPath)) {
    logger.warn(
      `Acceso bloqueado a archivo sensible: ${sanitizeForLog(req.method)} ${sanitizeForLog(normalizedPath)} (${clientIp})`
    )
    return res.status(403).json({ detail: 'Acceso denegado: ruta reservada del sistema.' })
  }

  next()
}

// --- Opciones de express.static endurecidas ---
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