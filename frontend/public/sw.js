// frontend/public/sw.js
// Service Worker que recibe Web Push y muestra la notificación en el escritorio,
// incluso cuando el navegador está cerrado.

self.addEventListener('install', () => {
  // Activa este SW inmediatamente sin esperar a que se cierre la pestaña actual.
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  // Toma el control de las pestañas abiertas sin recargar.
  event.waitUntil(self.clients.claim())
})

// ==== Manejo del push entrante ====
self.addEventListener('push', (event) => {
  if (!event.data) return

  let payload
  try {
    payload = event.data.json()
  } catch {
    payload = { titulo: 'SteelNort', detalle: event.data.text() }
  }

  const titulo = payload.titulo || 'SteelNort'
  const opciones = {
    body: payload.detalle || '',
    icon: '/favicon.ico',
    badge: '/favicon.ico',
    tag: payload.not_cod ? `not-${payload.not_cod}` : `alert-${Date.now()}`,
    requireInteraction: payload.severidad === 'C',   // críticas no se cierran solas
    data: {
      url: payload.url || '/notificaciones',
      severidad: payload.severidad || 'A',
      not_cod: payload.not_cod || null,
    },
  }

  event.waitUntil(self.registration.showNotification(titulo, opciones))
})

// ==== Click en la notificación ====
self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const url = event.notification.data?.url || '/notificaciones'

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientes) => {
      // Si ya hay una pestaña abierta, la enfocamos y navegamos.
      for (const cliente of clientes) {
        if ('focus' in cliente) {
          cliente.focus()
          if ('navigate' in cliente) cliente.navigate(url)
          return
        }
      }
      // Si no hay pestaña, abrimos una nueva.
      if (self.clients.openWindow) return self.clients.openWindow(url)
    })
  )
})