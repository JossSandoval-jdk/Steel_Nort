// Servidor WebSocket (Socket.io) para telemetria y alertas en tiempo real (Blindado).
import { logger } from './middleware/logger.js'

let ioRef = null

const rawMaxConn = Number(process.env.WS_MAX_CONN_PER_IP)
const MAX_PER_IP = Number.isInteger(rawMaxConn) && rawMaxConn > 0 ? rawMaxConn : 5
const conexionesPorIp = new Map()

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

function ipDe(socket) {
  // Si está detrás de un proxy confiable, Socket.io lee las cabeceras x-forwarded-for si está habilitado.
  // Como fallback seguro, usamos address o un valor genérico.
  const address = socket.handshake.headers['x-forwarded-for'] || socket.handshake.address
  return typeof address === 'string' ? address.replace(/[\r\n]/g, '') : 'unknown'
}

export function initWebSocket(io) {
  ioRef = io

  io.on('connection', (socket) => {
    const ip = ipDe(socket)
    const conectadas = (conexionesPorIp.get(ip) || new Set()).size

    if (conectadas >= MAX_PER_IP) {
      logger.warn(
        `WebSocket rechazado: ${ip} supera ${MAX_PER_IP} conexiones simultaneas`
      )
      socket.emit('error', { detail: 'Demasiadas conexiones abiertas.' })
      socket.disconnect(true)
      return
    }

    registrarConexion(ip, socket.id)
    logger.info(`WebSocket conectado: ${socket.id} (${ip})`)

    socket.on('telemetry:subscribe', () => {
      socket.join('telemetry')
      logger.debug(`Socket ${socket.id} se suscribio a telemetry`)
    })

    socket.on('alert:subscribe', () => {
      socket.join('alerts')
      logger.debug(`Socket ${socket.id} se suscribio a alerts`)
    })

    socket.on('disconnect', () => {
      liberarConexion(ip, socket.id)
      logger.info(`WebSocket desconectado: ${socket.id}`)
    })
  })

  return io
}

export function broadcastTelemetry(data) {
  if (ioRef) ioRef.to('telemetry').emit('telemetry', data)
}

export function broadcastAlert(data) {
  if (ioRef) {
    ioRef.to('alerts').emit('alert', data)
    ioRef.emit('alert:global', data)
  }
}

export function broadcastSystemStatus(data) {
  if (ioRef) ioRef.emit('system:status', data)
}