// Servidor Express que actúa como capa de middleware entre el
// frontend React y el backend FastAPI (puerto 8200).

// ⚠️ DEBE ser el PRIMER import: carga .env ANTES de que cualquier otro
// módulo (como push.js) lea process.env. Si se pone después, las variables
// VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY e INTERNAL_TOKEN llegan como undefined.
import 'dotenv/config'

import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import express from 'express'
import { Server as SocketIOServer } from 'socket.io'
import { proxyApi } from './proxy.js'
import { logger, httpLogger } from './middleware/logger.js'
import { healthHandler } from './middleware/health.js'
import { initWebSocket } from './websocket.js'
import { securityHeaders, denySensitiveFiles, staticOptions } from './middleware/security.js'
import { protectModel } from './middleware/modelProtection.js'
import { apiLimiter, authLimiter, modelLimiter, ingestLimiter } from './middleware/rateLimit.js'
import { enviarPushATodos, pushEstado } from './push.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const DIST_DIR = path.join(ROOT, 'dist')

const IS_PRODUCTION = process.env.NODE_ENV === 'production'

const rawPort = Number(process.env.PORT)
const PORT = Number.isInteger(rawPort) && rawPort > 0 ? rawPort : 3000

// CORS de Socket.io: soporta lista separada por comas
const SOCKET_CORS_ORIGINS = (process.env.CORS_ORIGIN || 'http://localhost:5173')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean)

const app = express()

// --- Trust proxy ---
if (process.env.TRUST_PROXY !== undefined) {
  const trustValue = Number(process.env.TRUST_PROXY)
  app.set('trust proxy', Number.isInteger(trustValue) ? trustValue : 1)
} else if (IS_PRODUCTION) {
  app.set('trust proxy', 1)
}

// --- 1. Logging HTTP ---
app.use(httpLogger)

// --- 2. Cabeceras de seguridad ---
app.use(securityHeaders)

// --- 3. Bloqueo de archivos sensibles y artefactos ML ---
app.use(denySensitiveFiles)
app.use(protectModel)

// --- 4. Rate limiting por IP ---
app.use('/api/v2/auth', authLimiter)
app.use('/api/v2/modelo', modelLimiter)
app.use('/api/v2/telemetria/push', ingestLimiter)
app.use('/api', apiLimiter)

// --- 5. Health check ---
const health = healthHandler({ port: PORT, distDir: DIST_DIR })
app.get('/health', health)
app.get('/healthz', health)

// --- 6. Endpoints INTERNOS (solo para FastAPI, nunca desde fuera) ---
function verificarTokenInterno(req, res, next) {
  const esperado = process.env.INTERNAL_TOKEN
  if (!esperado) {
    logger.error('[internal] INTERNAL_TOKEN no configurado.')
    return res.status(500).json({ detail: 'Servidor mal configurado.' })
  }
  const recibido = req.headers['x-internal-token']
  if (recibido !== esperado) {
    logger.warn(
      `[internal] Token inválido en ${req.method} ${req.originalUrl} desde ${req.ip}`
    )
    return res.status(401).json({ detail: 'Token interno inválido.' })
  }
  next()
}

// Body parser SOLO para rutas internas (pequeño, limitado).
app.use('/internal', express.json({ limit: '32kb' }))

// Estado de Web Push (para debugging).
app.get('/internal/push/estado', verificarTokenInterno, (_req, res) => {
  res.json(pushEstado())
})

// Webhook: FastAPI avisa de una notificación nueva.
app.post('/internal/notificar', verificarTokenInterno, async (req, res) => {
  try {
    const { titulo, detalle, severidad, url, not_cod } = req.body || {}

    if (!titulo || !severidad) {
      return res
        .status(422)
        .json({ detail: 'Faltan campos obligatorios: titulo, severidad.' })
    }

    // 1) Emitir por WebSocket (import dinámico para evitar ciclos).
    try {
      const { broadcastAlert } = await import('./websocket.js')
      broadcastAlert({ titulo, detalle, severidad, url, not_cod })
    } catch (wsErr) {
      logger.warn(`[internal] No se pudo emitir por WebSocket: ${wsErr.message}`)
    }

    // 2) Enviar Web Push a todos los suscritos.
    const resultado = await enviarPushATodos({
      titulo,
      detalle,
      severidad,
      url: url || '/notificaciones',
      not_cod,
    })

    res.json({ ok: true, ...resultado })
  } catch (err) {
    logger.error(`[internal] Error en /internal/notificar: ${err.message}`)
    res.status(500).json({ detail: 'Error interno.' })
  }
})

// --- 7. Proxy reverso hacia FastAPI ---
app.use('/api', proxyApi)

// --- 8. Body parsers globales ---
app.use(express.json({ limit: '100kb' }))
app.use(express.urlencoded({ extended: false, limit: '100kb' }))

// --- 9. Estáticos + SPA ---
if (IS_PRODUCTION) {
  app.use(express.static(DIST_DIR, staticOptions))

  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api')) return next()
    res.sendFile(path.join(DIST_DIR, 'index.html'))
  })
} else {
  app.get('/', (_req, res) => {
    res.json({
      app: 'SteelNort Serve',
      status: 'ok',
      mode: 'development',
      note: 'Frontend en http://localhost:5173',
    })
  })
  logger.info('Modo desarrollo: frontend se sirve vía Vite en http://localhost:5173')
}

// --- 10. 404 ---
app.use((req, res) => {
  res.status(404).json({ detail: 'Recurso no encontrado.' })
})

// --- 11. Manejador de errores GLOBAL ---
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, _next) => {
  const clientIp =
    typeof req.ip === 'string' ? req.ip.replace(/[\r\n]/g, '') : 'unknown'

  logger.error(
    `Error no manejado: ${req.method} ${req.originalUrl} (${clientIp})`,
    err
  )

  if (res.headersSent) return

  const status = Number.isInteger(err?.status) ? err.status : 500
  const detail = IS_PRODUCTION
    ? 'Error interno del servidor.'
    : err?.message || 'Error desconocido'

  res.status(status).json({ detail })
})

// ==============================================================================
// HTTP + WebSocket
// ==============================================================================
const server = http.createServer(app)

const io = new SocketIOServer(server, {
  path: '/socket.io',
  cors: {
    origin: SOCKET_CORS_ORIGINS,
    methods: ['GET', 'POST'],
    credentials: true,
  },
  maxHttpBufferSize: 1e6,
  pingInterval: 25_000,
  pingTimeout: 20_000,
})

initWebSocket(io)

server.listen(PORT, () => {
  logger.info(`Servidor Express escuchando en http://localhost:${PORT}`)
  logger.info(`Proxy API -> ${process.env.BACKEND_URL || 'http://localhost:8200'}`)
  logger.info(`Socket.io CORS origin(s): ${SOCKET_CORS_ORIGINS.join(', ')}`)

  // Estado de Web Push al arrancar
  const estado = pushEstado()
  if (estado.habilitado) {
    logger.info('[push] Web Push habilitado (VAPID configurado).')
  } else {
    logger.warn(
      `[push] Web Push DESHABILITADO (public=${estado.tienePublicKey}, private=${estado.tienePrivateKey}, token=${estado.tieneToken}).`
    )
  }
})

// ==============================================================================
// Graceful shutdown
// ==============================================================================
let shuttingDown = false

function shutdown(signal) {
  if (shuttingDown) return
  shuttingDown = true

  logger.info(`Recibida señal ${signal}, cerrando servidor...`)

  server.close((err) => {
    if (err) {
      logger.error(`Error cerrando servidor HTTP: ${err.message}`)
      process.exit(1)
    }
    logger.info('Servidor HTTP cerrado correctamente')
    process.exit(0)
  })

  io.close(() => {
    logger.info('Socket.io cerrado')
  })

  setTimeout(() => {
    logger.error('Cierre forzado tras timeout de 10s')
    process.exit(1)
  }, 10_000).unref()
}

process.on('SIGTERM', () => shutdown('SIGTERM'))
process.on('SIGINT', () => shutdown('SIGINT'))

process.on('uncaughtException', (err) => {
  logger.error('uncaughtException:', err)
  shutdown('uncaughtException')
})
process.on('unhandledRejection', (reason) => {
  logger.error('unhandledRejection:', reason)
})