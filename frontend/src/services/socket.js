// Cliente Socket.io para telemetria en tiempo real.
import { io } from 'socket.io-client'
import { SOCKET_URL } from '../config.js'

let socket = null

// Conecta al gateway WebSocket (una sola instancia reutilizable).
export function connectSocket(options = {}) {
  if (socket && socket.connected) return socket

  socket = io(SOCKET_URL, {
    autoConnect: true,
    transports: ['websocket'],
    ...options,
  })
  return socket
}

// Devuelve el socket activo (crea la conexion si aun no existe).
export function getSocket() {
  if (!socket) return connectSocket()
  return socket
}

// Suscribe el callback a un evento del socket y devuelve una funcion
// para cancelar la suscripcion.
export function onSocketEvent(event, callback) {
  const s = getSocket()
  s.on(event, callback)
  return () => s.off(event, callback)
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect()
    socket = null
  }
}