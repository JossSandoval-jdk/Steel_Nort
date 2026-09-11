// Servidor Express que actua como capa de middleware entre el
// frontend React y el backend FastAPI (puerto 8089).
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

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const DIST_DIR = path.join(ROOT, 'dist')

const rawPort = Number(process.env.PORT)
const PORT = Number.isInteger(rawPort) && rawPort > 0 ? rawPort : 3000

// Crea la aplicacion Express.
const app = express()

// Confia en la IP del proxy en produccion si esta detras de uno.
if (process.env.TRUST_PROXY) {
  const trustValue = Number(process.env.TRUST_PROXY)
  app.set('trust proxy', Number.isInteger(trustValue) ? trustValue : 1)
}

// Logging HTTP (Morgan). Se registra antes que las demas rutas.
app.use(httpLogger)

// 1. Cabeceras de seguridad y bloqueo de archivos sensibles.
app.use(securityHeaders)
app.use(denySensitiveFiles)

// 2. Bloqueo de artefactos del modelo ML.
app.use(protectModel)

// 3. Rate limiting por IP.
app.use('/api/auth', authLimiter)
app.use('/api/dominio/ml', modelLimiter)
app.use('/api/telemetria/muestras', ingestLimiter)
app.use('/api', apiLimiter)

// 4. Health check: visible para infraestructura/orquestadores.
app.get('/health', healthHandler({ port: PORT, distDir: DIST_DIR }))

// 5. Proxy reverso: reenvia /api/* al backend FastAPI.
app.use('/api', proxyApi)

// Peticiones JSON para las rutas locales que no pasan por el proxy.
app.use(express.json({ limit: '1mb' }))
app.use(express.urlencoded({ extended: false }))

// Estado de la API del backend (por compatibilidad).
app.get('/', (_req, res) => {
  res.json({ app: 'SteelNort Serve', status: 'ok' })
})

// == SPA routing ==============================================================
const isProdOrTest = process.env.NODE_ENV === 'production' || process.env.NODE_ENV === 'test'

if (isProdOrTest) {
  app.use(express.static(DIST_DIR, staticOptions))

  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api')) return next()
    res.sendFile(path.join(DIST_DIR, 'index.html'))
  })
} else {
  logger.info('Modo desarrollo: sirviendo via Vite en http://localhost:5173')
}

// ==============================================================================
// HTTP + WebSocket
// ==============================================================================
const server = http.createServer(app)
const io = new SocketIOServer(server, {
  cors: {
    origin: process.env.CORS_ORIGIN || 'http://localhost:5173',
    methods: ['GET', 'POST'],
  },
})

initWebSocket(io)

server.listen(PORT, () => {
  logger.info(`Servidor Express escuchando en http://localhost:${PORT}`)
  logger.info(`Proxy API -> ${process.env.BACKEND_URL || 'http://localhost:8089'}`)
})