// Hook de metricas del sistema (CPU y RAM) en tiempo real.
//
// Consume los endpoints del backend:
//   GET /metrics/sistema   -> estado puntual (tarjetas "en vivo").
//   GET /metrics/historial -> serie temporal en memoria (graficos).
//
// Hace un polling periodico (cada `intervaloMs`) y mantiene una ventana
// de historico en el frontend para alimentar los graficos "minuto a
// minuto". Usa el access token del AuthContext para autenticarse.
import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'

export function useSystemMetrics(intervaloMs = 3000, ventana = 80) {
  const { accessToken } = useAuth()

  // Estado puntual actual (para las tarjetas).
  const [actual, setActual] = useState(null)
  // Serie historica: { ts, cpuTotal, memPercent, nucleos }.
  const [historico, setHistorico] = useState([])
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  // Muestra puntual que se ejecuta en cada tick del polling.
  const tick = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/metrics/sistema', { token: accessToken })
      setActual({
        cpu: data.cpu.total,
        nucleos: data.cpu.nucleos,
        conteo: data.cpu.conteo,
        mem: data.mem.percent,
        memUsed: data.mem.used_mb,
        memTotal: data.mem.total_mb,
      })
      setError(null)
      // Acumula la muestra en la ventana del frente.
      setHistorico((prev) => {
        const next = prev.concat([{
          ts: data.ts,
          cpuTotal: data.cpu.total,
          memPercent: data.mem.percent,
          nucleos: data.cpu.nucleos,
        }])
        return next.length > ventana ? next.slice(next.length - ventana) : next
      })
    } catch (e) {
      setError(e.message || 'No se pudo obtener metricas del sistema')
    }
  }, [accessToken, ventana])

  // Carga inicial del historial y arranque/parada del polling.
  useEffect(() => {
    if (!accessToken) return undefined
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

  return { actual, historico, error }
}