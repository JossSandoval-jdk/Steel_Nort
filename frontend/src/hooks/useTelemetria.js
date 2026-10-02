// Hook de telemetria en tiempo real.
//
// ANTES: consumia GET /telemetria/live por SSE. Esa ruta es de la v1 y la v2
// no la expone, asi que el fetch devolvia 404 y `muestras` se quedaba SIEMPRE
// vacio. De ahi que los graficos de CPU, memoria y latencia salieran planos:
// la serie nunca tenia datos.
//
// AHORA: sondea GET /telemetria/actual (la ruta que la v2 si expone) cada
// `intervaloMs` y acumula las ultimas `ventana` muestras por nodo. La
// respuesta trae `metricas` con el estado del instante.
//
// Devuelve helper ``ultimaMuestra(nodo)`` y ``serie(nodo, n)`` para
// que los componentes grafiquen datos en vivo.

import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'

export function useTelemetria(ventana = 80, intervaloMs = 3000) {
  const { accessToken } = useAuth()
  const [muestras, setMuestras] = useState({})
  const [conectado, setConectado] = useState(false)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const tick = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/telemetria/actual', { token: accessToken })

      const metricas = data?.metricas || data?.data?.muestra || null
      if (!metricas) {
        setConectado(false)
        return
      }

      const nodo = data.nodo || data.nodo_nom || 'Servidor Negocio'
      const punto = {
        nodo,
        seq: data.seq,
        muestra: metricas,
        ts: data.fecha_str || new Date().toISOString(),
      }

      setMuestras((prev) => {
        const arr = prev[nodo] || []
        const next = [...arr, punto]
        return {
          ...prev,
          [nodo]: next.length > ventana ? next.slice(next.length - ventana) : next,
        }
      })
      setConectado(true)
      setError(null)
    } catch (e) {
      setConectado(false)
      setError(e.message || 'No se pudo obtener la telemetria')
    }
  }, [accessToken, ventana])

  useEffect(() => {
    if (!accessToken) {
      const t = setTimeout(() => setConectado(false), 0)
      return () => clearTimeout(t)
    }
    const primerTick = setTimeout(tick, 0)
    timerRef.current = setInterval(tick, intervaloMs)
    return () => {
      clearTimeout(primerTick)
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [accessToken, intervaloMs, tick])

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
