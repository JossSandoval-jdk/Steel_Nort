// Hook para manejar la suscripción Web Push del navegador.
// Devuelve el estado y las acciones para suscribir/desuscribir.
import { useState, useEffect, useCallback } from 'react'

const VAPID_PUBLIC_KEY = import.meta.env.VITE_VAPID_PUBLIC_KEY

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = atob(base64)
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)))
}

export function usePushSubscription() {
  const soportado =
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window

  const [permiso, setPermiso] = useState(() => {
    if (!soportado) return 'unsupported'
    return Notification.permission
  })

  const [suscrito, setSuscrito] = useState(false)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState(null)

  // Verificar si ya está suscrito
  useEffect(() => {
    if (!soportado) return
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => setSuscrito(Boolean(sub)))
      .catch(() => setSuscrito(false))
  }, [soportado])

  const pedirPermiso = useCallback(async () => {
    if (!soportado) return 'unsupported'
    const p = await Notification.requestPermission()
    setPermiso(p)
    return p
  }, [soportado])

  const suscribir = useCallback(
    async (apiToken) => {
      if (!soportado) {
        setError('Este navegador no soporta notificaciones push.')
        return null
      }
      if (!VAPID_PUBLIC_KEY) {
        setError('Falta VITE_VAPID_PUBLIC_KEY en el .env del frontend.')
        return null
      }
      setCargando(true)
      setError(null)
      try {
        // 1) Pedir permiso si no está concedido.
        if (Notification.permission !== 'granted') {
          const p = await Notification.requestPermission()
          setPermiso(p)
          if (p !== 'granted') {
            setError('Permiso de notificaciones denegado.')
            return null
          }
        }

        // 2) Registrar el Service Worker.
        const reg = await navigator.serviceWorker.register('/sw.js')
        await navigator.serviceWorker.ready

        // 3) Suscribirse con VAPID.
        let sub = await reg.pushManager.getSubscription()
        if (!sub) {
          sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
          })
        }

        // 4) Enviar la suscripción al backend.
        const respuesta = await fetch('/api/v2/notificaciones/push/suscribir', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${apiToken}`,
          },
          body: JSON.stringify(sub.toJSON()),
        })

        if (!respuesta.ok) {
          const txt = await respuesta.text()
          throw new Error(`Servidor rechazó la suscripción: ${respuesta.status} ${txt.slice(0, 200)}`)
        }

        setSuscrito(true)
        return sub
      } catch (err) {
        setError(err.message || 'Error suscribiendo.')
        return null
      } finally {
        setCargando(false)
      }
    },
    [soportado]
  )

  const desuscribir = useCallback(async (apiToken) => {
    if (!soportado) return
    setCargando(true)
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) {
        await fetch(`/api/v2/notificaciones/push/desuscribir?endpoint=${encodeURIComponent(sub.endpoint)}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${apiToken}` },
        })
        await sub.unsubscribe()
      }
      setSuscrito(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setCargando(false)
    }
  }, [soportado])

  return { soportado, permiso, suscrito, cargando, error, pedirPermiso, suscribir, desuscribir }
}