import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'

export function useSystemMetrics(intervaloMs = 3000, ventana = 80) {
  const { accessToken } = useAuth()

  const [actual, setActual] = useState(null)
  const [historico, setHistorico] = useState([])
  const [error, setError] = useState(null)
  const timerRef = useRef(null)
const tick = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/telemetria/actual', { token: accessToken })
      
      // Validamos y extraemos las métricas directamente del objeto que retorna /actual
      if (data.estado === 'ok') {
        const muestra = data.metricas || data.data?.muestra || {}
        
        const cpuVal = Math.round(Number(muestra.cpu_usr || 0) + Number(muestra.cpu_sys || 0));
        const memVal = Math.round(Number(muestra.memory_percent || 0));
        const memUsedVal = Number(muestra.memory_used_mb || 0);
        const memTotalVal = memVal > 0 ? memUsedVal / (memVal / 100) : 0; 
        const timestamp = data.fecha_str || new Date().toISOString()

        setActual({
          cpu: cpuVal,
          nucleos: muestra.nucleos || 4,
          conteo: muestra.conteo || 1,
          mem: memVal,
          memUsed: memUsedVal,
          memTotal: memTotalVal,
          // Agregamos las métricas transaccionales aquí para tenerlas disponibles globalmente:
          active_sessions: Number(muestra.active_sessions || muestra.active_requests || 0),
          idle_sessions: Number(muestra.idle_sessions || muestra.long_queries || 0),
          api_latency_ms: Number(muestra.api_latency_ms || muestra.duration_avg_ms || 0)
        })
        setError(null)

        setHistorico((prev) => {
          const next = prev.concat([{
            ts: timestamp,
            cpuTotal: cpuVal,
            memPercent: memVal,
            nucleos: muestra.nucleos || 4,
          }])
          return next.length > ventana ? next.slice(next.length - ventana) : next
        })
      }
    } catch (e) {
      setError(e.message || 'No se pudo obtener la telemetría del sistema')
    }
  }, [accessToken, ventana])

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