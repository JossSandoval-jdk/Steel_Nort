// Cliente HTTP base para la API v2 de SteelNort (prefijo /api/v2).
//
// El JWT va en la cabecera "Authorization: Bearer <token>" y lo administra el
// AuthContext (vive en memoria). No hay token CSRF en la v2: al no usar
// cookies de sesion, el navegador no puede reenviar el token por su cuenta.
//
// Devuelve el JSON de la respuesta o lanza un error normalizado con el codigo
// HTTP (err.status) y el detalle que envio el backend.
import { API_BASE_URL } from '../config.js'

// Convierte la respuesta HTTP en datos o en un error descriptivo.
async function handleResponse(resp) {
  const contentType = resp.headers.get('content-type') || ''
  const body = contentType.includes('application/json')
    ? await resp.json()
    : await resp.text()

  if (!resp.ok) {
    // 403 = falta permiso; el texto ya viene en espanol del backend.
    let detail = 'Error en la peticion.'
    if (body && typeof body === 'object' && body.detail) {
      if (Array.isArray(body.detail)) {
        // Errores de validacion de FastAPI (422): un array con la
        // descripcion de cada campo invalido.
        detail = body.detail
          .map((d) => (typeof d === 'object' && d.msg ? d.msg : String(d)))
          .join(' · ')
      } else {
        detail = body.detail
      }
    } else if (typeof body === 'string' && body) {
      detail = body
    }
    const err = new Error(detail)
    err.status = resp.status
    throw err
  }

  return body
}

// Arma las cabeceras comunes de cada peticion.
function cabeceras(conToken, conCuerpo) {
  const headers = { accept: 'application/json' }
  if (conCuerpo) headers['content-type'] = 'application/json'
  if (conToken) headers.Authorization = `Bearer ${conToken}`
  return headers
}

async function get(path, { token } = {}) {
  const resp = await fetch(`${API_BASE_URL}${path}`, { headers: cabeceras(token, false) })
  return handleResponse(resp)
}

async function post(path, data, { token } = {}) {
  console.log('Enviando a:', `${API_BASE_URL}${path}`, 'con datos:', data); // <-- Agrega esto para depurar
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: cabeceras(token, true),
    body: JSON.stringify(data ?? {}),
  })
  return handleResponse(resp)
}

async function patch(path, data, { token } = {}) {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    headers: cabeceras(token, true),
    body: JSON.stringify(data ?? {}),
  })
  return handleResponse(resp)
}

async function put(path, data, { token } = {}) {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PUT',
    headers: cabeceras(token, true),
    body: JSON.stringify(data ?? {}),
  })
  return handleResponse(resp)
}

async function del(path, { token } = {}) {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    headers: cabeceras(token, false),
  })
  return handleResponse(resp)
}

// Peticion POST multipart/form-data (subida de archivos).
async function upload(path, formData, { token } = {}) {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: cabeceras(token, false),
    body: formData,
  })
  return handleResponse(resp)
}

const api = { get, post, patch, put, del, upload }
export default api
