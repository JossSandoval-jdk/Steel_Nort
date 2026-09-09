// Configuracion central del frontend.
// Centraliza la URL base de la API y los nombres de almacenamiento de
// tokens para facilitar la escalabilidad y el cambio de despliegue.
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8089'

// Claves de almacenamiento local (token CSRF). El ACCESS token se
// guarda en memoria (AuthContext), nunca en localStorage.
const STORAGE_KEYS = {
  csrf: 'steelnort_csrf',
}

export { API_BASE_URL, STORAGE_KEYS }