// Proxy reverso hacia el backend FastAPI (Blindado).
import { createProxyMiddleware } from 'http-proxy-middleware'
import { logger } from './logger.js'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8089'
const RAW_TIMEOUT = Number(process.env.PROXY_TIMEOUT_MS)
const TIMEOUT_MS = Number.isInteger(RAW_TIMEOUT) && RAW_TIMEOUT > 0 ? RAW_TIMEOUT : 30_000
const isProduction = process.env.NODE_ENV === 'production'

export const proxyApi = createProxyMiddleware({
  target: BACKEND_URL,
  changeOrigin: true,
  pathRewrite: (path) => path.replace(/^\/api/, ''),
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