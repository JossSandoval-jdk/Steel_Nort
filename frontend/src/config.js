// Configuracion central del frontend.
//
// En desarrollo (Vite) se usa la URL del backend FastAPI directamente
// mediante VITE_API_URL o el proxy integrado de Vite. En produccion el
// servidor Express actua como proxy reverso, asi que todas las
// llamadas van a la ruta relativa "/api" del mismo origen.
const API_BASE_URL =
  import.meta.env.VITE_API_URL || 'http://localhost:5173/api'
  import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

// URL del socket para telemetria en tiempo real (mismo origen que la API).
const SOCKET_URL =
  import.meta.env.VITE_SOCKET_URL || 'http://localhost:5173'

// Claves de almacenamiento local (token CSRF). El ACCESS token se
// guarda en memoria (AuthContext), nunca en localStorage.
const STORAGE_KEYS = {
  csrf: 'steelnort_csrf',
}

export { API_BASE_URL, SOCKET_URL, STORAGE_KEYS }