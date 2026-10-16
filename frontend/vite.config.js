import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
//
// En desarrollo, Vite reenvía las llamadas al backend FastAPI (puerto 8200)
// que llegan con el prefijo /api, y los WebSockets de Socket.io al servidor
// Express (puerto 3000). Así el frontend solo usa rutas relativas (/api/v2)
// y no hace falta ninguna URL fija por entorno.
//
// En producción el servidor Express (frontend/server/server.js) hace de proxy
// inverso con el mismo prefijo, por lo que esta configuración es solo local.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // API v2 -> FastAPI (mantiene el prefijo /api/v2).
      '/api': {
        target: 'http://localhost:8200',
        changeOrigin: true,
      },
      // Socket.io -> Express (telemetria en tiempo real / notificaciones).
      '/socket.io': {
        target: 'http://localhost:3000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})