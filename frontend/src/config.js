// Configuracion central del frontend.
//
// En desarrollo (Vite) el proxy de vite.config.js reenvia /api/v2 al backend
// FastAPI de la v2, asi que aqui solo hay rutas relativas: no hay ninguna URL
// fija que haya que cambiar al desplegar. En produccion el servidor Express
// hace de proxy inverso con la misma ruta.
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v2'

// URL del socket para telemetria en tiempo real (mismo origen que la API).
const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:5173'

export { API_BASE_URL, SOCKET_URL }
