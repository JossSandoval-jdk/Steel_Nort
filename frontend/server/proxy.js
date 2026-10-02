// Proxy reverso hacia el backend FastAPI (Blindado).
import { createProxyMiddleware } from 'http-proxy-middleware'
import { logger } from './logger.js'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8200'
const RAW_TIMEOUT = Number(process.env.PROXY_TIMEOUT_MS)
const TIMEOUT_MS = Number.isInteger(RAW_TIMEOUT) && RAW_TIMEOUT > 0 ? RAW_TIMEOUT : 30_000
const isProduction = process.env.NODE_ENV === 'production'

export const proxyApi = createProxyMiddleware({
  target: BACKEND_URL,
  changeOrigin: true,
  // El navegador pide /api/v2/... y el backend sirve bajo /api/v2, asi que la
  // ruta tiene que llegar INTACTA.
  //
  // Ojo: server.js monta esto con app.use('/api', proxyApi), y Express ya le
  // quita el '/api' de req.url antes de llamar al middleware. Por eso este
  // rewrite tiene que devolver el '/api' que Express se llevo, no quitarlo.
  // Con la version anterior (path.replace(/^\/api/, '')) el backend recibia
  // /v2/... y respondia 404 en todo.
  pathRewrite: (path) => (path.startsWith('/api') ? path : `/api${path}`),
  timeout: TIMEOUT_MS,
  proxyTimeout: TIMEOUT_MS,
  ws: true,
  on: {
    error: (err, _req, res) => {
      logger.error(`Error de comunicación con el backend FastAPI: ${err.message}`)
      
      if (res && !res.headersSent) {
        // En producción ocultamos detalles de infraestructura y rutas internas
        const errorMessage = isProduction 
          ? 'Error de comunicación con el servicio de backend.' 
          : `No se pudo alcanzar el backend en ${BACKEND_URL}: ${err.message}`

        res.status(502).json({
          detail: errorMessage,
        })
      }
    },
  },
})