import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // El prefijo /api NO se reescribe: el frontend llama /api/v2/... y la
      // app v2 (app.v2.main:app) monta sus routers bajo /api/v2. Si se
      // quitara el prefijo, las rutas ya no existirian.
      //
      // El 8200 es el mismo que arranca backend\run_backend.bat y el que
      // espera server\.env (BACKEND_URL).
      '/api': {
        target: 'http://127.0.0.1:8200',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})