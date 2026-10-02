import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import { Fragment, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import api from '../services/api.js'
import { alertasDesdePagina } from '../services/severidad.js'
import {
  rangoHoyUtc,
  useDashboardAnomaliasResumen,
  useDashboardHeatmap,
} from '../hooks/useDashboardData.js'
import '../css/Layout.css'
import '../css/Alertas.css'

function IconAlerta() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

function MiniChart({ data }) {
  const W = 120
  const H = 48
  const max = Math.max(...data)
  const min = Math.min(...data)
  const span = max - min || 1
  const step = W / (Math.max(data.length - 1, 1))
  const pts = data
    .map((v, i) => {
      const x = i * step
      const y = H - ((v - min) / span) * (H - 8) - 4
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg className="mini-chart" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <defs>
        <linearGradient id="grad-mini" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0269a1" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#0269a1" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${H} ${pts} ${W},${H}`} fill="url(#grad-mini)" />
      <polyline points={pts} fill="none" stroke="#0269a1" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

const SERIES = [
  { key: 'criticas', stroke: '#dc2626' },
  { key: 'advertencia', stroke: '#d97706' },
  { key: 'informacion', stroke: '#0891b2' },
]

function TendenciaChart({ dias, tendencia }) {
  const W = 440
  const H = 170
  const PAD_L = 30
  const PAD_R = 10
  const PAD_T = 12
  const PAD_B = 24
  const PLOT_W = W - PAD_L - PAD_R
  const PLOT_H = H - PAD_T - PAD_B
  const n = dias.length
  const valores = SERIES.flatMap(({ key }) => tendencia[key] || [])
  const maxY = Math.max(1, ...valores)
  const baseY = H - PAD_B
  const stepX = n > 1 ? PLOT_W / (n - 1) : 0

  const seriePoints = (arr) =>
    arr
      .map((v, i) => {
        const x = PAD_L + i * stepX
        const y = PAD_T + (1 - v / maxY) * PLOT_H
        return `${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')

  return (
    <svg className="tendencia-svg" viewBox={`0 0 ${W} ${H}`} role="img">
      <defs>
        {SERIES.map(({ key, stroke }) => (
          <linearGradient key={key} id={`grad-tend-${key}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        ))}
      </defs>
      {[0, maxY / 2, maxY].map((lv) => {
        const y = PAD_T + (1 - lv / maxY) * PLOT_H
        return (
          <g key={lv}>
            <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="rgba(19,41,61,0.08)" strokeDasharray="4 4" />
            <text x={PAD_L - 8} y={y + 4} textAnchor="end" fontSize="11" fill="#8a94a0">
              {Math.round(lv)}
            </text>
          </g>
        )
      })}
      {dias.map((d, i) => d && (
        <text key={d + i} x={PAD_L + i * stepX} y={H - 8} textAnchor="middle" fontSize="11" fill="#8a94a0">
          {d}
        </text>
      ))}
      {SERIES.map(({ key }) => (
        <polygon
          key={`area-${key}`}
          points={`${PAD_L},${baseY} ${seriePoints(tendencia[key] || [])} ${W - PAD_R},${baseY}`}
          fill={`url(#grad-tend-${key})`}
        />
      ))}
      {SERIES.map(({ key, stroke }) => (
        <polyline
          key={key}
          points={seriePoints(tendencia[key] || [])}
          fill="none"
          stroke={stroke}
          strokeWidth="2.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
    </svg>
  )
}

const TIPO_ALERTA = { anomalia_ml: 'anomalía ML', sincronizacion: 'sincronización', vps: 'VPS', daemon: 'daemon' }

function formatearFecha(iso, incluirFecha) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  const hoy = new Date()
  const esHoy = d.toDateString() === hoy.toDateString()
  const hora = d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })
  if (!incluirFecha || esHoy) return hora
  return `${d.toLocaleDateString('es', { day: '2-digit', month: 'short' })} ${hora}`
}

function formatearValor(valor, unidad = '') {
  const numero = Number(valor)
  if (!Number.isFinite(numero)) return valor ?? '—'
  return `${new Intl.NumberFormat('es', { maximumFractionDigits: 2 }).format(numero)}${unidad}`
}

function etiquetaSeveridad(severidad) {
  return { critica: 'Crítica', alta: 'Alta', media: 'Media', baja: 'Baja' }[severidad] || 'Media'
}

// Informe para operaciones: resume la señal y conecta eventos, sesiones y logs.
function DetalleAlerta({ alerta, informe }) {
  const explicacion = informe?.explicacion
  const variables = informe?.variables || []
  const eventos = informe?.eventos || []
  const logs = informe?.logs_sql || []
  const prediccion = informe?.prediccion
  const severidad = alerta?.alt_sev || 'media'

  return (
    <div className="detalle-alerta">
      <div className="detalle-seccion detalle-explicacion">
        <div className="detalle-explicacion-cabecera">
          <div>
            <h4 className="detalle-titulo">Qué ocurrió</h4>
            <p className="detalle-diag">
              {explicacion?.texto || 'El sistema observó un cambio sostenido en el comportamiento habitual del servidor.'}
            </p>
          </div>
          <span className={`rol-pill ${severidad}`}>{etiquetaSeveridad(severidad)}</span>
        </div>
        {explicacion?.sospecha && (
          <div className="detalle-sospecha">
            <strong>Posible causa</strong>
            <p>{explicacion.sospecha}</p>
          </div>
        )}
        {prediccion && (
          <p className="detalle-vacio">
            Periodo observado: {formatearFecha(prediccion.inicio, true)} – {formatearFecha(prediccion.fin, true)}
          </p>
        )}
      </div>

      <div className="detalle-seccion">
        <h4 className="detalle-titulo">Indicadores fuera de su nivel habitual</h4>
        {variables.length ? variables.slice(0, 5).map((variable) => (
          <div className="indicador-explicado" key={variable.alv_cod}>
            <strong>{variable.etiqueta}</strong>
            <span>{formatearValor(variable.alv_valor, variable.unidad)}</span>
            <small>{variable.interpretacion}</small>
          </div>
        )) : <p className="detalle-vacio">No hay indicadores adicionales para esta alerta.</p>}
      </div>

      <div className="detalle-seccion detalle-evidencia">
        <h4 className="detalle-titulo">Actividad SQL relacionada ({eventos.length})</h4>
        {eventos.length ? eventos.map((evento, indice) => (
          <article className="evento-explicado" key={`${evento.fecha}-${indice}`}>
            <div className="evento-explicado-cabecera">
              <strong>{evento.actividad}</strong>
              <time>{formatearFecha(evento.fecha, true)}</time>
            </div>
            <p className="detalle-vacio">
              {evento.duracion != null && `Duración: ${formatearValor(evento.duracion / 1000, ' ms')}`}
              {evento.lecturas != null && ` · Lecturas: ${formatearValor(evento.lecturas)}`}
            </p>
            {evento.sesion ? (
              <p className="evento-sesion">
                Sesión {evento.sesion.id}
                {evento.sesion.usuario && ` · Usuario ${evento.sesion.usuario}`}
                {evento.sesion.equipo && ` · Equipo ${evento.sesion.equipo}`}
                {evento.sesion.aplicacion && ` · Aplicación ${evento.sesion.aplicacion}`}
              </p>
            ) : (
              <p className="detalle-vacio">No se identificó una sesión para esta actividad.</p>
            )}
            {evento.sql && (
              <details className="evento-sql">
                <summary>Ver detalle de la consulta</summary>
                <pre>{evento.sql}</pre>
              </details>
            )}
          </article>
        )) : <p className="detalle-vacio">No se registraron eventos SQL en el periodo de esta alerta.</p>}
      </div>

      <div className="detalle-seccion detalle-evidencia">
        <h4 className="detalle-titulo">Registros de error SQL ({logs.length})</h4>
        {logs.length ? logs.map((registro, indice) => (
          <article className="log-explicado" key={`${registro.fecha}-${indice}`}>
            <span className={`log-nivel ${registro.nivel || ''}`}>{registro.nivel_texto || 'Registro'}</span>
            <time>{formatearFecha(registro.fecha, true)}</time>
            <p>{registro.mensaje}</p>
          </article>
        )) : <p className="detalle-vacio">SQL Server no reportó errores en el periodo de esta alerta.</p>}
      </div>
    </div>
  )
}

function Alertas() {
  const { user, accessToken } = useAuth()
  const [alertas, setAlertas] = useState([])
  const [resumen, setResumen] = useState([])
  const [error, setError] = useState('')
  // Detalle de la alerta desplegada: variables anomalas y arbol de causa raiz.
  const [detalle, setDetalle] = useState(null)
  const [detalleCargando, setDetalleCargando] = useState(false)
  const [detalleError, setDetalleError] = useState('')
  const { datos: heatmapDatos } = useDashboardHeatmap(60000)
  const { hora_actual_cant } = useDashboardAnomaliasResumen(60000)

  useEffect(() => {
    let activo = true
    const cargarAlertas = () => {
      const rangoHoy = rangoHoyUtc()
      const parametros = new URLSearchParams({
        pagina: '1',
        tamano: '200',
        orden: '-alt_fec',
        desde: rangoHoy.desde,
        hasta: rangoHoy.hasta,
      })
      api.get(`/deteccion/alertas?${parametros.toString()}`, { token: accessToken })
        .then((hoy) => {
        if (!activo) return
        const alertasHoy = alertasDesdePagina(hoy).sort((a, b) => new Date(b.alt_fec) - new Date(a.alt_fec))
        setAlertas(alertasHoy)

        setResumen([
          { id: 'criticas', label: 'Críticas', valor: alertasHoy.filter((a) => a.alt_sev === 'critica').length, tone: 'criticas' },
          { id: 'advertencia', label: 'Advertencia', valor: alertasHoy.filter((a) => a.alt_sev === 'alta' || a.alt_sev === 'media').length, tone: 'advertencia' },
          { id: 'informacion', label: 'Información', valor: alertasHoy.filter((a) => a.alt_sev === 'baja').length, tone: 'informacion' },
        ])

      })
      .catch((err) => {
        if (activo) setError(err.message || 'No se pudieron cargar las alertas.')
      })
    }
    cargarAlertas()
    const timer = setInterval(cargarAlertas, 30000)
    return () => {
      activo = false
      clearInterval(timer)
    }
  }, [accessToken])

  // Toggle: volver a pulsar la misma fila la cierra.
  const alternarDetalle = (alerta) => {
    if (detalle && detalle.alerta.alt_cod === alerta.alt_cod) {
      setDetalle(null)
      return
    }
    setDetalle({ alerta, informe: null })
    setDetalleCargando(true)
    setDetalleError('')
    const cod = alerta.alt_cod
    api.get(`/deteccion/alertas/${cod}/informe`, { token: accessToken })
      .then((informe) => {
        setDetalle({ alerta, informe })
        setDetalleCargando(false)
      })
      .catch((err) => {
        setDetalleError(err.message || 'No se pudo cargar el detalle de la alerta.')
        setDetalleCargando(false)
      })
  }

  const porHora = useMemo(() => {
    const arr = Array.from({ length: 24 }, () => 0)
    if (heatmapDatos && heatmapDatos.length > 0) {
      for (const d of heatmapDatos) {
        if (d.hora >= 0 && d.hora < 24) arr[d.hora] += d.cantidad || 0
      }
    }
    return arr
  }, [heatmapDatos])

  const tendenciaHoy = useMemo(() => {
    const horas = Array.from({ length: 24 }, (_, hora) => hora)
    const resultado = {
      dias: horas.map((hora) => ([0, 6, 12, 18, 23].includes(hora) ? `${String(hora).padStart(2, '0')}:00` : '')),
      criticas: Array(24).fill(0),
      advertencia: Array(24).fill(0),
      informacion: Array(24).fill(0),
    }
    for (const alerta of alertas) {
      const fechaAlerta = new Date(alerta.alt_fec)
      if (Number.isNaN(fechaAlerta.getTime())) continue
      const hora = fechaAlerta.getUTCHours()
      if (alerta.alt_sev === 'critica') resultado.criticas[hora] += 1
      else if (alerta.alt_sev === 'alta' || alerta.alt_sev === 'media') resultado.advertencia[hora] += 1
      else if (alerta.alt_sev === 'baja') resultado.informacion[hora] += 1
    }
    return resultado
  }, [alertas])

  const nombre = user?.usu_nom || 'Nombre Usuario'
  const cargo = user?.usu_rol || 'Cargo'
  const visibles = alertas.slice(0, 20)

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={nombre} cargo={cargo} />
        <main className="layout-content">
          <div className="alertas">
            <article className="card">
              <div className="resumen-title">Resumen de alertas de hoy</div>

              <div className="resumen-celdas">
                {resumen.map((r) => (
                  <div key={r.id} className="resumen-celda">
                    <label>{r.label}</label>
                    <div className="resumen-principal">
                      <span className={`resumen-icono ${r.tone}`}>
                        <IconAlerta />
                      </span>
                      <span className="resumen-num">{r.valor}</span>
                    </div>
                  </div>
                ))}

                <div className="resumen-celda">
                  <label>Tasa de anomalías (hora)</label>
                  <div className="resumen-principal">
                    <div className="resumen-metrica">
                      <span className="resumen-num">{hora_actual_cant}</span>
                      <span className="resumen-desc">/h</span>
                    </div>
                    <span className="resumen-icono anomalias">
                      <IconAlerta />
                    </span>
                  </div>
                </div>

                <div className="resumen-celda grafico">
                  <MiniChart data={porHora} />
                </div>
              </div>
            </article>

            <div className="alertas-secundario">
              <article className="card alerts-tabla-card">
                <div className="card-head">
                  <h3 className="card-title">Alertas recientes</h3>
                </div>
                <div className="alerts-table-scroll">
                  <table className="alerts-table">
                    <thead>
                      <tr>
                        <th>Hora</th>
                        <th>Alerta</th>
                        <th>Severidad</th>
                        <th>Diagnóstico</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibles.map((a) => (
                        <Fragment key={a.alt_cod}>
                          <tr
                            className={`fila-alerta${detalle && detalle.alerta.alt_cod === a.alt_cod ? ' abierta' : ''}`}
                            onClick={() => alternarDetalle(a)}
                            onKeyDown={(evento) => {
                              if (evento.key === 'Enter' || evento.key === ' ') {
                                evento.preventDefault()
                                alternarDetalle(a)
                              }
                            }}
                            tabIndex={0}
                            aria-expanded={Boolean(detalle && detalle.alerta.alt_cod === a.alt_cod)}
                          >
                            <td className="t-marca">{formatearFecha(a.alt_fec, true)}</td>
                            <td>
                              {a.alt_titulo}
                              {a.alt_tipo && <small> · {TIPO_ALERTA[a.alt_tipo] || a.alt_tipo}</small>}
                            </td>
                            <td><span className={`rol-pill ${a.alt_sev}`}>{etiquetaSeveridad(a.alt_sev)}</span></td>
                            <td className="t-diagnostico">
                              {a.alt_tipo === 'anomalia_ml'
                                ? 'Cambio sostenido en el comportamiento del servidor.'
                                : a.alt_diag || 'Sin diagnóstico'}
                            </td>
                          </tr>
                        </Fragment>
                      ))}
                      {visibles.length === 0 && (
                        <tr>
                          <td colSpan="4" className="t-diagnostico">{error || 'Sin alertas registradas'}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </article>

              <article className="card tendencia-card">
                <div className="card-head">
                  <h3 className="card-title">Severidad por hora · hoy</h3>
                </div>
                <TendenciaChart dias={tendenciaHoy.dias} tendencia={tendenciaHoy} />
                <div className="tendencia-leyenda">
                  <span className="leyenda-item criticas">Críticas</span>
                  <span className="leyenda-item advertencia">Advertencia</span>
                  <span className="leyenda-item informacion">Información</span>
                </div>
              </article>
            </div>
            {detalle && (
              <div className="detalle-modal-fondo" onClick={() => setDetalle(null)}>
                <section
                  className="detalle-modal"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="detalle-modal-titulo"
                  onClick={(evento) => evento.stopPropagation()}
                >
                  <header className="detalle-modal-cabecera">
                    <div>
                      <h2 id="detalle-modal-titulo">{detalle.alerta.alt_titulo}</h2>
                      <p>{formatearFecha(detalle.alerta.alt_fec, true)} · {etiquetaSeveridad(detalle.alerta.alt_sev)}</p>
                    </div>
                    <button type="button" className="detalle-modal-cerrar" onClick={() => setDetalle(null)}>
                      Cerrar
                    </button>
                  </header>
                  <div className="detalle-modal-contenido">
                    {detalleCargando && <p className="detalle-vacio">Preparando el informe…</p>}
                    {!detalleCargando && detalleError && (
                      <p className="detalle-vacio error">{detalleError}</p>
                    )}
                    {!detalleCargando && !detalleError && (
                      <DetalleAlerta alerta={detalle.alerta} informe={detalle.informe} />
                    )}
                  </div>
                </section>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

export default Alertas