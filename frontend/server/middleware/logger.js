// Logging del servidor Express blindado y robusto.
import morgan from 'morgan'

const LEVELS = ['debug', 'info', 'warn', 'error']
const RAW_LEVEL = (process.env.LOG_LEVEL || 'info').toLowerCase()

// Fallback seguro: si el nivel no existe, por defecto usa 'info'
const THRESHOLD = LEVELS.includes(RAW_LEVEL) ? LEVELS.indexOf(RAW_LEVEL) : LEVELS.indexOf('info')

function sanitizeLogInput(value) {
  if (typeof value === 'string') {
    // Previene log injection removiendo retornos de carro y saltos de línea maliciosos
    return value.replace(/[\r\n]/g, '_')
  }
  return value
}

function write(level, args) {
  if (LEVELS.indexOf(level) < THRESHOLD) return
  
  const ts = new Date().toISOString()
  const [msg, ...meta] = args
  const prefix = `[${ts}] ${level.toUpperCase().padEnd(5)}`
  
  const safeMsg = sanitizeLogInput(msg)
  const safeMeta = meta.map(sanitizeLogInput)

  if (safeMeta.length) {
    if (level === 'error') console.error(prefix, safeMsg, ...safeMeta)
    else if (level === 'warn') console.warn(prefix, safeMsg, ...safeMeta)
    else console.log(prefix, safeMsg, ...safeMeta)
  } else {
    if (level === 'error') console.error(prefix, safeMsg)
    else if (level === 'warn') console.warn(prefix, safeMsg)
    else console.log(prefix, safeMsg)
  }
}

export const logger = {
  debug: (...a) => write('debug', a),
  info: (...a) => write('info', a),
  warn: (...a) => write('warn', a),
  error: (...a) => write('error', a),
}

export const httpLogger = morgan('combined', {
  stream: {
    write: (msg) => logger.debug(msg.trim()),
  },
})