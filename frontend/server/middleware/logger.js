// middleware/logger.js
// Logging blindado, sin fugas y a prueba de inyecciones.
import morgan from 'morgan'

// --- Configuración ---
const LEVELS = ['debug', 'info', 'warn', 'error']
const RAW_LEVEL = (process.env.LOG_LEVEL || 'info').toLowerCase()
const THRESHOLD = LEVELS.includes(RAW_LEVEL)
  ? LEVELS.indexOf(RAW_LEVEL)
  : LEVELS.indexOf('info')

const IS_PRODUCTION = process.env.NODE_ENV === 'production'
const MAX_STRING_LEN = 2000

// Claves cuyo valor NUNCA debe aparecer en logs
const REDACTED_KEYS = new Set([
  'authorization', 'cookie', 'set-cookie', 'proxy-authorization',
  'password', 'passwd', 'pwd', 'pass',
  'token', 'access_token', 'refresh_token', 'id_token',
  'api_key', 'apikey', 'api-key', 'x-api-key',
  'secret', 'client_secret', 'jwt', 'session', 'sessionid',
  'csrf', 'xsrf', 'private_key', 'secret_key',
])

// --- Sanitización ---

function sanitizeString(value) {
  if (typeof value !== 'string') return value
  return value
    // Elimina control chars (\x00-\x1f, \x7f) y secuencias ANSI en una sola pasada
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f]|\u001b\[[0-9;]*[A-Za-z]/g, '_')
    .slice(0, MAX_STRING_LEN)
}

function deepSanitize(value, seen = new WeakSet()) {
  if (value === null || value === undefined) return value

  const t = typeof value
  if (t === 'string') return sanitizeString(value)
  if (t === 'number' || t === 'boolean' || t === 'bigint') return value
  if (t === 'function') return `[Function: ${value.name || 'anonymous'}]`
  if (t === 'symbol') return value.toString()

  // Error: extrae solo lo seguro
  if (value instanceof Error) {
    const out = {
      name: sanitizeString(value.name),
      message: sanitizeString(value.message),
    }
    if (!IS_PRODUCTION && value.stack) out.stack = sanitizeString(value.stack)
    if (value.code) out.code = sanitizeString(String(value.code))
    // Propaga el 'cause' recursivamente, respetando el WeakSet de ciclos
    if (value.cause) out.cause = deepSanitize(value.cause, seen)
    return out
  }

  // Detección de ciclos
  if (seen.has(value)) return '[Circular]'
  seen.add(value)

  if (Array.isArray(value)) {
    return value.map((v) => deepSanitize(v, seen))
  }

  if (t === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(value)) {
      const key = String(k).toLowerCase()
      if (REDACTED_KEYS.has(key)) {
        out[k] = '[REDACTED]'
      } else {
        out[k] = deepSanitize(v, seen)
      }
    }
    return out
  }

  return String(value)
}

// --- Escritura ---
function write(level, args) {
  if (LEVELS.indexOf(level) < THRESHOLD) return

  const ts = new Date().toISOString()
  const prefix = `[${ts}] ${level.toUpperCase().padEnd(5)}`

  const safeArgs = args.map((v) => deepSanitize(v))

  const writer =
    level === 'error' ? console.error
    : level === 'warn' ? console.warn
    : console.log

  writer(prefix, ...safeArgs)
}

export const logger = {
  debug: (...a) => write('debug', a),
  info:  (...a) => write('info', a),
  warn:  (...a) => write('warn', a),
  error: (...a) => write('error', a),
}

// --- HTTP logger (morgan) ---

const SENSITIVE_QUERY = /([?&])(token|access_token|refresh_token|id_token|api_key|apikey|api-key|password|secret|jwt|code|state)=[^&#]*/gi

function redactUrl(url) {
  if (typeof url !== 'string') return ''
  return url.replace(SENSITIVE_QUERY, '$1$2=[REDACTED]')
}

morgan.token('safe-url',    (req) => sanitizeString(redactUrl(req.originalUrl || req.url)))
morgan.token('safe-ua',     (req) => sanitizeString(req.headers['user-agent'] || '-'))
morgan.token('safe-ref',    (req) => sanitizeString(req.headers['referer'] || '-'))
morgan.token('safe-remote', (req) => sanitizeString(req.ip || req.socket?.remoteAddress || '-'))

const HTTP_FORMAT = ':safe-remote :method :safe-url :status :res[content-length] - :response-time ms ":safe-ref" ":safe-ua"'

export const httpLogger = morgan(HTTP_FORMAT, {
  stream: {
    write: (msg) => logger.debug(msg.trim()),
  },
  skip: (req) => req.path === '/health' || req.path === '/healthz',
})