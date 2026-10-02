// Hooks para datos agregados del Dashboard.
//
// useDashboardHeatmap:        grid de anomalías (hora x severidad).
// useDashboardDisponibilidad: uptime de servicios (7 días).
// useDashboardAnomaliasResumen: conteo de anomalías hoy.
//
// Las tres leen de la API v2 (prefijo /api/v2). Antes apuntaban a rutas de la
// v1 (/dashboard/heatmap, /dashboard/disponibilidad, /dashboard/anomalias-resumen)
// que la v2 no expone, así que el tablero salía vacío.
//
// Mapa de calor -> GET /sistema/resumen/heatmap?dia=YYYY-MM-DD
// Resumen        -> GET /sistema/resumen
//
// Las dos rutas piden el permiso "tablero:leer" (por eso App.jsx protege
// /dashboard con ese permiso y no con "datos:leer").

import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'

// La tabla heatmap_anomalias guarda 3 niveles, pero el trigger
// TR_alertas_hma_rollup solo escribe dos: 'A' (critica o alta) y 'B'
// (media o baja). El mapa del tablero tiene tres filas, asi que la baja se
// dibuja siempre vacia.
const SEV_A_NIVEL = { A: 'alerta_alta', B: 'alerta_baja' }

// Fechas en UTC, no en hora local.
//
// El detector sella las ventanas con utc_now() (app/ml/detector.py), alt_fec
// sale de ahi y el trigger TR_alertas_hma_rollup hace DATEPART(HOUR, alt_fec).
// O sea, heatmap_anomalias esta indexado en UTC. Con hora local el tablero
// pedia un dia/hora que no existia y el mapa salia vacio.
function hoy() {
  const d = new Date()
  const mes = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dia = String(d.getUTCDate()).padStart(2, '0')
  return `${d.getUTCFullYear()}-${mes}-${dia}`
}

export function rangoHoyUtc() {
  return {
    desde: `${hoy()}T00:00:00`,
    hasta: new Date().toISOString().slice(0, 19),
  }
}

export function rangoUltimosSieteDiasUtc() {
  const desde = new Date(`${hoy()}T00:00:00Z`)
  desde.setUTCDate(desde.getUTCDate() - 6)
  return {
    desde: desde.toISOString().slice(0, 19),
    hasta: new Date().toISOString().slice(0, 19),
  }
}

// Hora UTC actual, la misma que usa DATEPART(HOUR, alt_fec).
function horaUtc() {
  return new Date().getUTCHours()
}

function etiquetaDia(iso) {
  if (iso === hoy()) return 'Hoy'
  const nombre = new Date(`${iso}T12:00:00Z`).toLocaleDateString('es', {
    weekday: 'short',
    timeZone: 'UTC',
  })
  return nombre.charAt(0).toUpperCase() + nombre.slice(1)
}

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
      const dia = hoy()
      const celdas = await api.get(`/sistema/resumen/heatmap?dia=${dia}`, { token: accessToken })
      setDatos(
        (celdas || [])
          .filter((c) => SEV_A_NIVEL[c.severidad])
          .map((c) => ({ ...c, severidad: SEV_A_NIVEL[c.severidad] }))
      )
      setDesde(`${dia}T00:00`)
      setHasta(`${dia}T23:59`)
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

// Disponibilidad = porcentaje de ventanas sanas por dia.
//
// La v1 sacaba el uptime de `estadisticas_carga`, que en v2 no escribe nadie
// (solo el POST manual de /datos/cargas la toca). Por eso este widget vivio
// con ceros fijos. Ahora sale de GET /sistema/resumen/disponibilidad, que
// cuenta ventanas evaluadas vs ventanas no anomalas por dia.
export function useDashboardDisponibilidad(intervaloMs = 300000, cantidadDias = 7) {
  const { accessToken } = useAuth()
  const [dias, setDias] = useState([])
  const [promedio, setPromedio] = useState(0)
  const [etiquetas, setEtiquetas] = useState([])
  const [conDatos, setConDatos] = useState(false)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const cargar = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get(`/sistema/resumen/disponibilidad?dias=${cantidadDias}`, { token: accessToken })
      const lista = data?.dias || []
      setDias(lista.map((d) => d.pct))
      setEtiquetas(lista.map((d) => etiquetaDia(d.dia)))
      setPromedio(data?.promedio ?? 0)
      setConDatos(Boolean(data?.con_datos))
      setError(null)
    } catch (e) {
      setError(e.message || 'No se pudo cargar la disponibilidad')
    }
  }, [accessToken, cantidadDias])

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

  return { dias, promedio, etiquetas, conDatos, error, recargar: cargar }
}

export function useDashboardTransacciones(intervaloMs = 300000, cantidadDias = 7) {
  const { accessToken } = useAuth()
  const [dias, setDias] = useState([])
  const [promedio, setPromedio] = useState(null)
  const [etiquetas, setEtiquetas] = useState([])
  const [conDatos, setConDatos] = useState(false)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const cargar = useCallback(async () => {
    if (!accessToken) return
    try {
      const data = await api.get(`/sistema/resumen/transacciones?dias=${cantidadDias}`, { token: accessToken })
      const lista = data?.dias || []
      setDias(lista.map((dia) => dia.promedio))
      setEtiquetas(lista.map((dia) => etiquetaDia(dia.dia)))
      setPromedio(data?.promedio ?? null)
      setConDatos(Boolean(data?.con_datos))
      setError(null)
    } catch (e) {
      setError(e.message || 'No se pudieron cargar las transacciones diarias')
    }
  }, [accessToken, cantidadDias])

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

  return { dias, promedio, etiquetas, conDatos, error, recargar: cargar }
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
      // /sistema/resumen trae alertas_activas (alertas con alt_est = 'A').
      const dia = hoy()
      const hora = horaUtc()
      const [plano, celdas] = await Promise.all([
        api.get('/sistema/resumen', { token: accessToken }),
        api.get(`/sistema/resumen/heatmap?dia=${dia}`, { token: accessToken }),
      ])
      const lista = celdas || []
      setResumen({
        total_hoy: lista.reduce((suma, c) => suma + (c.cantidad || 0), 0),
        hora_actual_cant: lista
          .filter((c) => c.hora === hora)
          .reduce((suma, c) => suma + (c.cantidad || 0), 0),
        alertas_activas: plano.alertas || 0,
      })
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