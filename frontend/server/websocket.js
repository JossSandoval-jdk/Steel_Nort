// Servidor WebSocket (Socket.io) para telemetría y alertas en tiempo real (Blindado v2).
import { logger } from './middleware/logger.js'

// --- Config ---
const MAX_PER_IP = (() => {
  const v = Number(process.env.WS_MAX_CONN_PER_IP)
  return Number.isInteger(v) && v > 0 ? v : 5
})()

const MAX_EVENTS_PER_MINUTE = (() => {
  const v = Number(process.env.WS_MAX_EVENTS_PER_MIN)
  return Number.isInteger(v) && v > 0 ? v : 60
})()

const HANDSHAKE_AUTH_TIMEOUT_MS = 10_000
const ALLOWED_ROOMS = new Set(['telemetry', 'alerts'])

// --- Estado en memoria ---
let ioRef = null
const conexionesPorIp = new Map()

// --- Helpers ---

function sanitizeForLog(value) {
  if (typeof value !== 'string') return 'unknown'
  // eslint-disable-next-line no-control-regex
  return value.replace(/[\u0000-\u001f\u007f]|\u001b\[[0-9;]*[A-Za-z]/g, '_').slice(0, 200)
}

// Extrae la IP real. Confiamos en x-forwarded-for SOLO si hay proxy delante
// (ya está configurado con app.set('trust proxy', 1) en Express).
function ipDe(socket) {
  const xff = socket.handshake.headers['x-forwarded-for']
  if (typeof xff === 'string' && xff.length > 0) {
    // x-forwarded-for puede ser "cliente, proxy1, proxy2"
    const first = xff.split(',')[0].trim()
    if (first) return sanitizeForLog(first)
  }
  return sanitizeForLog(socket.handshake.address || 'unknown')
}

function registrarConexion(ip, socketId) {
  let sockets = conexionesPorIp.get(ip)
  if (!sockets) {
    sockets = new Set()
    conexionesPorIp.set(ip, sockets)
  }
  sockets.add(socketId)
}

function liberarConexion(ip, socketId) {
  const sockets = conexionesPorIp.get(ip)
  if (!sockets) return
  sockets.delete(socketId)
  if (sockets.size === 0) conexionesPorIp.delete(ip)
}

// --- Init ---

export function initWebSocket(io) {
  ioRef = io

  // 🔐 1. Middleware de autenticación (handshake)
  // ESTE ES EL PUNTO CLAVE. Ajusta la validación según tu auth real.
  io.use((socket, next) => {
    try {
      const token =
        socket.handshake.auth?.token ||
        // Fallback: Authorization: Bearer xxx
        (socket.handshake.headers.authorization || '').replace(/^Bearer\s+/i, '')

      if (!token) {
        logger.warn(`[ws] Handshake sin token rechazado: ${ipDe(socket)}`)
        return next(new Error('AUTH_REQUIRED'))
      }

      // TODO: aquí valida tu JWT. Ejemplos:
      //   import jwt from 'jsonwebtoken'
      //   const payload = jwt.verify(token, process.env.JWT_SECRET)
      //   socket.data.user = { id: payload.sub, role: payload.role }
      //
      // O llama a FastAPI para validar:
      //   const r = await fetch(`${BACKEND_URL}/api/auth/verify`, {...})
      //
      // Por ahora asumimos un placeholder. REEMPLAZA ESTO.

      // ⚠️ Placeholder SOLO para desarrollo:
      if (process.env.NODE_ENV === 'production') {
        return next(new Error('AUTH_NOT_IMPLEMENTED'))
      }
      socket.data.user = { id: 'dev-user', role: 'admin' }

      next()
    } catch (err) {
      logger.warn(`[ws] Handshake error: ${sanitizeForLog(err.message)}`)
      next(new Error('AUTH_ERROR'))
    }
  })

  // 🔐 2. Timeout para handshake sin autenticar
  io.use((socket, next) => {
    const timer = setTimeout(() => {
      if (!socket.data.user) {
        logger.warn(`[ws] Handshake timeout desde ${ipDe(socket)}`)
        socket.disconnect(true)
      }
    }, HANDSHAKE_AUTH_TIMEOUT_MS)
    socket.once('disconnect', () => clearTimeout(timer))
    next()
  })

  // 🔐 3. Conexión
  io.on('connection', (socket) => {
    const ip = ipDe(socket)
    const conectadas = (conexionesPorIp.get(ip) || new Set()).size

    if (conectadas >= MAX_PER_IP) {
      logger.warn(
        `[ws] Rechazado: ${ip} supera ${MAX_PER_IP} conexiones simultáneas`
      )
      socket.emit('error', { code: 'TOO_MANY_CONNECTIONS' })
      // Pequeño delay para que el cliente reciba el error antes de cerrar
      setTimeout(() => socket.disconnect(true), 100)
      return
    }

    registrarConexion(ip, socket.id)
    logger.info(
      `[ws] Conectado: ${sanitizeForLog(socket.id)} user=${sanitizeForLog(socket.data.user?.id)} (${ip})`
    )

    // 🔐 4. Rate limit por socket
    let eventCount = 0
    const windowStart = Date.now()

    const canEmit = () => {
      const now = Date.now()
      if (now - windowStart > 60_000) {
        eventCount = 0
        return true
      }
      eventCount++
      return eventCount <= MAX_EVENTS_PER_MINUTE
    }

    // 🔐 5. Suscripciones con validación
    const handleSubscribe = (room) => {
      if (!canEmit()) {
        socket.emit('error', { code: 'RATE_LIMIT' })
        return
      }
      if (!ALLOWED_ROOMS.has(room)) {
        logger.warn(`[ws] Suscripción a sala no permitida: ${sanitizeForLog(room)}`)
        socket.emit('error', { code: 'INVALID_ROOM' })
        return
      }
      socket.join(room)
      logger.debug(`[ws] ${sanitizeForLog(socket.id)} → room ${room}`)
    }

    socket.on('telemetry:subscribe', () => handleSubscribe('telemetry'))
    socket.on('alert:subscribe', () => handleSubscribe('alerts'))

    // 🔐 6. Desconexión
    socket.on('disconnect', (reason) => {
      liberarConexion(ip, socket.id)
      logger.info(`[ws] Desconectado: ${sanitizeForLog(socket.id)} (${sanitizeForLog(reason)})`)
    })

    // 🔐 7. Manejo de errores del socket
    socket.on('error', (err) => {
      logger.warn(`[ws] Error en socket ${sanitizeForLog(socket.id)}: ${sanitizeForLog(err?.message)}`)
    })
  })

  return io
}

// --- Broadcasts (solo a salas específicas) ---

export function broadcastTelemetry(data) {
  if (ioRef) ioRef.to('telemetry').emit('telemetry', data)
}

export function broadcastAlert(data) {
  if (ioRef) ioRef.to('alerts').emit('alert', data)
  // ❌ Eliminado ioRef.emit('alert:global', data): filtraba a todos.
}

export function broadcastSystemStatus(data) {
  if (ioRef) ioRef.emit('system:status', data)
}