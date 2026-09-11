// Cliente HTTP base para la API SteelNort.
//
// Encapsula el uso de ``fetch`` con la estrategia de doble token:
//   - access_token (JWT): se inyecta en "Authorization: Bearer <token>".
//     El token lo administra el AuthContext (en memoria) y se le pasa a
//     esta capa al llamar.
//   - csrf_token: se lee de localStorage y se envia en "X-CSRF-Token".
//
// Devuelve el JSON de la respuesta o lanza un error normalizado con el
// codigo HTTP y el detalle enviado por el backend.
import { API_BASE_URL, STORAGE_KEYS } from '../config.js'

// Lee el token CSRF guardado en localStorage (puede ser null).
function getCsrfToken() {
  const raw = localStorage.getItem(STORAGE_KEYS.csrf)
  return raw || null
}

// Convierte la respuesta HTTP en datos o en un error descriptivo.
async function handleResponse(resp) {
  const contentType = resp.headers.get('content-type') || ''
  const body = contentType.includes('application/json')
    ? await resp.json()
    : await resp.text()

  if (!resp.ok) {
    // Forma un error con status y detalle legible.
    const detail =
      (body && typeof body === 'object' && body.detail) ||
      (typeof body === 'string' && body) ||
      'Error en la peticion.'
    const err = new Error(detail)
    err.status = resp.status
    throw err
  }

  return body
}

// Peticion GET con tokens opcionales.
async function get(path, { token } = {}) {
  const headers = {
    accept: 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`

  const resp = await fetch(`${API_BASE_URL}${path}`, { headers, credentials: 'include' })
  return handleResponse(resp)
}

// Peticion POST. ``withCsrf`` activa el header de validacion (solo
// guarda el token si se hace en una ruta de escritura que lo exige,
// p. ej. logout ; el login no envia csrf porque aun no lo posee).
async function post(path, data, { token, csrf } = {}) {
  const headers = {
    'content-type': 'application/json',
    accept: 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`
  if (csrf) headers['X-CSRF-Token'] = csrf

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify(data),
  })
  return handleResponse(resp)
}

// Peticion PATCH (edicion parcial de un recurso).
async function patch(path, data, { token, csrf } = {}) {
  const headers = {
    'content-type': 'application/json',
    accept: 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`
  if (csrf) headers['X-CSRF-Token'] = csrf

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    headers,
    credentials: 'include',
    body: JSON.stringify(data),
  })
  return handleResponse(resp)
}

// Peticion DELETE (eliminacion de un recurso).
async function del(path, { token, csrf } = {}) {
  const headers = {
    accept: 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`
  if (csrf) headers['X-CSRF-Token'] = csrf

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    headers,
    credentials: 'include',
  })
  return handleResponse(resp)
}

// Peticion POST multipart/form-data (subida de archivos).
async function upload(path, formData, { token, csrf } = {}) {
  const headers = {
    accept: 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`
  if (csrf) headers['X-CSRF-Token'] = csrf

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: formData,
  })
  return handleResponse(resp)
}

const api = { get, post, patch, del, upload, getCsrfToken }
export default api