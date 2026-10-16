// server/push.js
// Envío de notificaciones Web Push (VAPID) a los navegadores suscritos.
//
// Flujo:
//   1. Node recibe un webhook de FastAPI con { not_cod, titulo, ... }
//   2. Este módulo pide a FastAPI las suscripciones activas
//   3. Envía un push a cada una (endpoint + claves p256dh/auth)
//   4. Si una suscripción responde 404/410 (caducada), la desactiva
//   5. Actualiza 'fec_ultimo_uso' de las que sí funcionaron
//
// El endpoint de suscripciones y el de "marcar uso" son internos de FastAPI,
// protegidos con el header 'X-Internal-Token'.

import webpush from 'web-push'
import { logger } from './middleware/logger.js'

// --- Configuración VAPID (desde .env) ---
const VAPID_PUBLIC = process.env.VAPID_PUBLIC_KEY
const VAPID_PRIVATE = process.env.VAPID_PRIVATE_KEY
const VAPID_SUBJECT = process.env.VAPID_SUBJECT || 'mailto:admin@steelnort.local'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'
const INTERNAL_TOKEN = process.env.INTERNAL_TOKEN

// Web Push NO está configurado si falta cualquier clave esencial.
const PUSH_HABILITADO = Boolean(VAPID_PUBLIC && VAPID_PRIVATE && INTERNAL_TOKEN)

if (PUSH_HABILITADO) {
  webpush.setVapidDetails(VAPID_SUBJECT, VAPID_PUBLIC, VAPID_PRIVATE)
  logger.info('[push] Web Push habilitado (VAPID configurado).')
} else {
  logger.warn(
    '[push] Web Push DESHABILITADO: faltan VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY o INTERNAL_TOKEN en el .env.'
  )
}

// --- Helper para hablar con FastAPI ---

async function fetchInterno(ruta, opciones = {}) {
  const url = `${BACKEND_URL}${ruta}`
  const headers = {
    'X-Internal-Token': INTERNAL_TOKEN,
    ...(opciones.headers || {}),
  }
  const respuesta = await fetch(url, { ...opciones, headers })
  if (!respuesta.ok) {
    const texto = await respuesta.text().catch(() => '')
    throw new Error(`FastAPI ${ruta} -> ${respuesta.status} ${texto.slice(0, 200)}`)
  }
  return respuesta.json().catch(() => null)
}

// --- Obtener suscripciones activas ---

async function obtenerSuscripcionesActivas() {
  try {
    const lista = await fetchInterno('/api/v2/internal/push/suscripciones')
    return Array.isArray(lista) ? lista : []
  } catch (err) {
    logger.error(`[push] No se pudieron obtener las suscripciones: ${err.message}`)
    return []
  }
}

async function marcarUsoSuscripcion(psuCod) {
  try {
    await fetchInterno(`/api/v2/internal/push/${psuCod}/uso`, { method: 'POST' })
  } catch (err) {
    // No es crítico, solo informativo.
    logger.debug(`[push] No se pudo marcar uso de ${psuCod}: ${err.message}`)
  }
}

// --- Envío individual ---

async function enviarUna(suscripcion, payload) {
  const subscription = {
    endpoint: suscripcion.psu_endpoint,
    keys: {
      p256dh: suscripcion.psu_p256dh,
      auth: suscripcion.psu_auth,
    },
  }

  try {
    await webpush.sendNotification(subscription, JSON.stringify(payload), {
      TTL: 60 * 60 * 24, // 24 h: si el navegador estaba apagado, guarda el mensaje
      urgency: payload.severidad === 'C' ? 'high' : 'normal',
    })
    return { ok: true }
  } catch (err) {
    const status = err.statusCode || 0
    // 404/410 = suscripción caducada. FastAPI la desactiva.
    if (status === 404 || status === 410) {
      return { ok: false, caducada: true, status }
    }
    return { ok: false, caducada: false, status, error: err.message }
  }
}

// --- Función pública: enviar a todos ---

/**
 * Envía una notificación push a todas las suscripciones activas.
 *
 * @param {object} payload
 * @param {string} payload.titulo
 * @param {string} [payload.detalle]
 * @param {string} payload.severidad   'C' | 'A' | 'M' | 'B'
 * @param {string} [payload.url]       Ruta del frontend para el click
 * @param {number} [payload.not_cod]   ID de la notificación en BD
 * @returns {Promise<{enviadas:number, fallidas:number, caducadas:number}>}
 */
export async function enviarPushATodos(payload) {
  if (!PUSH_HABILITADO) {
    logger.debug('[push] Ignorado: Web Push no está habilitado.')
    return { enviadas: 0, fallidas: 0, caducadas: 0 }
  }

  const suscripciones = await obtenerSuscripcionesActivas()
  if (suscripciones.length === 0) {
    logger.debug('[push] No hay suscripciones activas.')
    return { enviadas: 0, fallidas: 0, caducadas: 0 }
  }

  let enviadas = 0
  let fallidas = 0
  let caducadas = 0

  await Promise.all(
    suscripciones.map(async (s) => {
      const res = await enviarUna(s, payload)
      if (res.ok) {
        enviadas++
        // No bloqueamos el envío por el marcado de uso.
        marcarUsoSuscripcion(s.psu_cod).catch(() => {})
      } else if (res.caducada) {
        caducadas++
        logger.info(`[push] Suscripción ${s.psu_cod} caducada (${res.status}).`)
      } else {
        fallidas++
        logger.warn(
          `[push] Fallo al enviar a ${s.psu_cod}: ${res.status} ${res.error || ''}`
        )
      }
    })
  )

  logger.info(
    `[push] Envío completado: ${enviadas} OK, ${fallidas} fallo(s), ${caducadas} caducada(s).`
  )
  return { enviadas, fallidas, caducadas }
}

// --- Estado interno (para el health check) ---

export function pushEstado() {
  return {
    habilitado: PUSH_HABILITADO,
    tienePublicKey: Boolean(VAPID_PUBLIC),
    tienePrivateKey: Boolean(VAPID_PRIVATE),
    tieneToken: Boolean(INTERNAL_TOKEN),
    subject: VAPID_SUBJECT,
  }
}