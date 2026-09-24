import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import api from '../services/api.js'
import { useDashboardAnomaliasResumen, useDashboardHeatmap } from '../hooks/useDashboardData.js'
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
      {dias.map((d, i) => (
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

function Alertas() {
  const { user, accessToken } = useAuth()
  const [alertas, setAlertas] = useState([])
  const [resumen, setResumen] = useState([])
  const [tendencia, setTendencia] = useState({ dias: [], criticas: [], advertencia: [], informacion: [] })
  const [error, setError] = useState('')
  const { datos: heatmapDatos } = useDashboardHeatmap(60000)
  const { hora_actual_cant } = useDashboardAnomaliasResumen(60000)

  useEffect(() => {
    let activo = true
    api.get('/alertas', { token: accessToken })
      .then((data) => {
        if (!activo) return
        const ordenadas = (data || []).slice().sort((a, b) => new Date(b.alt_fec) - new Date(a.alt_fec))
        setAlertas(ordenadas)

        const limite = Date.now() - 24 * 3600 * 1000
        const veinticuatro = ordenadas.filter((a) => new Date(a.alt_fec).getTime() >= limite)

        setResumen([
          { id: 'criticas', label: 'Críticas', valor: veinticuatro.filter((a) => a.alt_sev === 'critica').length, tone: 'criticas' },
          { id: 'advertencia', label: 'Advertencia', valor: veinticuatro.filter((a) => a.alt_sev === 'alta' || a.alt_sev === 'media').length, tone: 'advertencia' },
          { id: 'informacion', label: 'Información', valor: veinticuatro.filter((a) => a.alt_sev === 'baja').length, tone: 'informacion' },
        ])

        const diasArr = []
        for (let i = 6; i >= 0; i--) {
          const d = new Date()
          d.setDate(d.getDate() - i)
          diasArr.push(d)
        }
        const clave = (f) => {
          const d = new Date(f)
          return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
        }
        const claves = diasArr.map(clave)
        const contar = (fn) => claves.map((k) => ordenadas.filter((a) => clave(a.alt_fec) === k && fn(a.alt_sev)).length)

        setTendencia({
          dias: diasArr.map((d, i) => (i === 6 ? 'Hoy' : d.toLocaleDateString('es', { weekday: 'short' }))),
          criticas: contar((s) => s === 'critica'),
          advertencia: contar((s) => s === 'alta' || s === 'media'),
          informacion: contar((s) => s === 'baja'),
        })
      })
      .catch((err) => {
        if (activo) setError(err.message || 'No se pudieron cargar las alertas.')
      })
    return () => { activo = false }
  }, [accessToken])

  const porHora = useMemo(() => {
    const arr = Array.from({ length: 24 }, () => 0)
    if (heatmapDatos && heatmapDatos.length > 0) {
      for (const d of heatmapDatos) {
        if (d.hora >= 0 && d.hora < 24) arr[d.hora] += d.cantidad || 0
      }
    }
    return arr
  }, [heatmapDatos])

  const nombre = user?.usu_nom || 'Nombre Usuario'
  const cargo = user?.usu_rol || 'Cargo'
  const visibles = alertas.slice(0, 12)

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={nombre} cargo={cargo} />
        <main className="layout-content">
          <div className="alertas">
            <article className="card">
              <div className="resumen-title">Resumen de alertas (24 horas)</div>

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
                      <tr key={a.alt_cod}>
                        <td className="t-marca">{formatearFecha(a.alt_fec, true)}</td>
                        <td>
                          {a.alt_titulo}
                          {a.alt_tipo && <small> · {TIPO_ALERTA[a.alt_tipo] || a.alt_tipo}</small>}
                        </td>
                        <td><span className={`rol-pill ${a.alt_sev}`}>{a.alt_sev}</span></td>
                        <td className="t-diagnostico">{a.alt_diag || 'Sin diagnóstico'}</td>
                      </tr>
                    ))}
                    {visibles.length === 0 && (
                      <tr>
                        <td colSpan="4" className="t-diagnostico">{error || 'Sin alertas registradas'}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </article>

              <article className="card tendencia-card">
                <div className="card-head">
                  <h3 className="card-title">Tendencia de severidad</h3>
                </div>
                <TendenciaChart dias={tendencia.dias} tendencia={tendencia} />
                <div className="tendencia-leyenda">
                  <span className="leyenda-item criticas">Críticas</span>
                  <span className="leyenda-item advertencia">Advertencia</span>
                  <span className="leyenda-item informacion">Información</span>
                </div>
              </article>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Alertas