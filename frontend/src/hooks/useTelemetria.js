// Hook de telemetria en tiempo real via SSE.
//
// Consume GET /telemetria/live usando fetch + ReadableStream para
// poder enviar Authorization Bearer (EventSource nativo no soporta
// headers custom). Parsea el protocolo SSE manualmente.
//
// Acumula las ultimas ``ventana`` muestras por nodo en state.
// Devuelve helper ``ultimaMuestra(nodo)`` y ``serie(nodo, n)`` para
// que los componentes grafiquen datos en vivo.

import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../config.js'
import { useAuth } from '../context/AuthContext.jsx'

export function useTelemetria(ventana = 80) {
  const { accessToken } = useAuth()
  const [muestras, setMuestras] = useState({})
  const [conectado, setConectado] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const cerrar = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setConectado(false)
  }, [])

  useEffect(() => {
    if (!accessToken) {
      cerrar()
      return undefined
    }

    const ac = new AbortController()
    abortRef.current = ac

    let buffer = ''
    let seq = 0
    let activo = true

    const url = `${API_BASE_URL}/telemetria/live?token=${encodeURIComponent(accessToken)}`

    async function conectar() {
      while (activo && !ac.signal.aborted) {
        try {
          setConectado(false)
          const resp = await fetch(url, {
            headers: { Accept: 'text/event-stream' },
            credentials: 'include',
            signal: ac.signal,
          })

          if (!resp.ok) {
            if (resp.status === 401 || resp.status === 403) {
              setError('Sesion expirada. Inicie sesion nuevamente.')
              break
            }
            setError(`Error SSE: ${resp.status}`)
            break
          }

          setConectado(true)
          setError(null)
          buffer = ''
          const reader = resp.body.getReader()
          const decoder = new TextDecoder()

          while (activo && !ac.signal.aborted) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lineas = buffer.split('\n')
            buffer = lineas.pop()

            let tipoEvento = null
            let dataLinea = ''

            for (const linea of lineas) {
              if (linea.startsWith('event:')) {
                tipoEvento = linea.slice(6).trim()
              } else if (linea.startsWith('data:')) {
                dataLinea = linea.slice(5).trim()
              } else if (linea === '' && tipoEvento) {
                if (tipoEvento === 'muestra' && dataLinea) {
                  try {
                    const parsed = JSON.parse(dataLinea)
                    const nodo = parsed.nodo || 'default'
                    seq = parsed.seq || seq

                    setMuestras((prev) => {
                      const arr = prev[nodo] || []
                      const next = [...arr, parsed]
                      return {
                        ...prev,
                        [nodo]: next.length > ventana
                          ? next.slice(next.length - ventana)
                          : next,
                      }
                    })
                  } catch {
                    // SSE linea malformada, ignorar
                  }
                }
                tipoEvento = null
                dataLinea = ''
              }
            }
          }
        } catch (e) {
          if (ac.signal.aborted) break
          setError(e.message || 'Conexion SSE perdida')
        }

        setConectado(false)
        if (activo && !ac.signal.aborted) {
          await new Promise((r) => setTimeout(r, 3000))
        }
      }
    }

    conectar()

    return () => {
      activo = false
      ac.abort()
    }
  }, [accessToken, ventana, cerrar])

  const ultimaMuestra = useCallback(
    (nodo) => {
      const arr = muestras[nodo]
      if (!arr || arr.length === 0) return null
      return arr[arr.length - 1]
    },
    [muestras],
  )

  const serie = useCallback(
    (nodo, n) => {
      const arr = muestras[nodo] || []
      if (!n) return arr
      return arr.slice(-n)
    },
    [muestras],
  )

  return { muestras, conectado, error, ultimaMuestra, serie }
}
