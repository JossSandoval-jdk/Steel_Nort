// Hooks para datos agregados del Dashboard.
//
// useDashboardHeatmap:  grid de anomalías (hora x severidad).
// useDashboardDisponibilidad: uptime de servicios (7 días).
// useDashboardAnomaliasResumen: conteo de anomalías hoy.

import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'

export function useDashboardHeatmap(intervaloMs = 60000) {
  const { accessToken } = useAuth()
  const [datos, setDatos] = useState([])
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const cargar = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/dashboard/heatmap?dias=1', { token: accessToken })
      setDatos(data.datos || [])
      setDesde(data.desde || '')
      setHasta(data.hasta || '')
      setError(null)
    } catch (e) {
      setError(e.message || 'No se pudo cargar el heatmap')
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primerTick = setTimeout(cargar, 0)
    timerRef.current = setInterval(cargar, intervaloMs)
    return () => {
      clearTimeout(primerTick)
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [accessToken, intervaloMs, cargar])

  return { datos, desde, hasta, error, recargar: cargar }
}

export function useDashboardDisponibilidad(intervaloMs = 300000) {
  const { accessToken } = useAuth()
  const [dias, setDias] = useState([])
  const [promedio, setPromedio] = useState(100)
  const [etiquetas, setEtiquetas] = useState([])
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const cargar = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/dashboard/disponibilidad', { token: accessToken })
      setDias(data.dias || [])
      setPromedio(data.promedio ?? 100)
      setEtiquetas(data.etiquetas || [])
      setError(null)
    } catch (e) {
      setError(e.message || 'No se pudo cargar disponibilidad')
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primerTick = setTimeout(cargar, 0)
    timerRef.current = setInterval(cargar, intervaloMs)
    return () => {
      clearTimeout(primerTick)
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [accessToken, intervaloMs, cargar])

  return { dias, promedio, etiquetas, error, recargar: cargar }
}

export function useDashboardAnomaliasResumen(intervaloMs = 30000) {
  const { accessToken } = useAuth()
  const [resumen, setResumen] = useState({
    total_hoy: 0,
    hora_actual_cant: 0,
    alertas_activas: 0,
  })
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const cargar = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get('/dashboard/anomalias-resumen', { token: accessToken })
      setResumen(data)
      setError(null)
    } catch (e) {
      setError(e.message || 'No se pudo cargar resumen de anomalías')
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    const primerTick = setTimeout(cargar, 0)
    timerRef.current = setInterval(cargar, intervaloMs)
    return () => {
      clearTimeout(primerTick)
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [accessToken, intervaloMs, cargar])

  return { ...resumen, error, recargar: cargar }
}
