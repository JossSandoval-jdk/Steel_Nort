import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import CorrelacionRaiz from '../components/CorrelacionRaiz.jsx'
import HistoriaSesion from '../components/HistoriaSesion.jsx'
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import api from '../services/api.js'
import '../css/Layout.css'
import '../css/Alertas.css'
import AnomaliasTable from '../components/AnomaliasTable.jsx'

const anomalias24h = [0.06, 0.09, 0.07, 0.11, 0.14, 0.1, 0.13, 0.17, 0.12, 0.15, 0.19, 0.16, 0.12, 0.14, 0.18, 0.2, 0.16, 0.15, 0.13, 0.17, 0.14, 0.18, 0.15, 0.13]

function IconAlerta() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

function IconEye() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function IconDownload() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function MiniChart({ data }) {
  const W = 120
  const H = 48
  const max = Math.max(...data)
  const min = Math.min(...data)
  const span = max - min || 1
  const step = W / (data.length - 1)
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

function TendenciaChart() {
  const W = 440
  const H = 170
  const PAD_L = 30
  const PAD_R = 10
  const PAD_T = 12
  const PAD_B = 24
  const PLOT_W = W - PAD_L - PAD_R
  const PLOT_H = H - PAD_T - PAD_B
  const n = dias.length
  const maxY = 8
  const baseY = H - PAD_B

  const seriePoints = (arr) =>
    arr
      .map((v, i) => {
        const x = PAD_L + (i * PLOT_W) / (n - 1)
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
              {lv}
            </text>
          </g>
        )
      })}
      {dias.map((d, i) => (
        <text key={d} x={PAD_L + (i * PLOT_W) / (n - 1)} y={H - 8} textAnchor="middle" fontSize="11" fill="#8a94a0">
          {d}
        </text>
      ))}
      {SERIES.map(({ key }) => (
        <polygon
          key={`area-${key}`}
          points={`${PAD_L},${baseY} ${seriePoints(tendencia[key])} ${W - PAD_R},${baseY}`}
          fill={`url(#grad-tend-${key})`}
        />
      ))}
      {SERIES.map(({ key, stroke }) => (
        <polyline
          key={key}
          points={seriePoints(tendencia[key])}
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

const resumen = [
  { id: 'criticas', label: 'Críticas', valor: '3', tone: 'criticas' },
  { id: 'advertencia', label: 'Advertencia', valor: '7', tone: 'advertencia' },
  { id: 'informacion', label: 'Información', valor: '12', tone: 'informacion' },
]

const alertasRecientes = [
  { tiempo: '16:04', tipo: 'Pico de CPU', severidad: 'critica', diagnostico: 'Nodo SCADA-02 · Umbral superado por 6 min' },
  { tiempo: '14:37', tipo: 'Acceso fallido', severidad: 'alta', diagnostico: 'Múltiples intentos · usuario svc_backup' },
  { tiempo: '11:20', tipo: 'Latencia BD', severidad: 'media', diagnostico: 'Base de datos · promedio 480 ms' },
  { tiempo: '08:45', tipo: 'Certificado TLS', severidad: 'baja', diagnostico: 'Caducidad · expira en 15 días' },
]

const tendencia = {
  criticas: [1, 0, 2, 1, 0, 1, 2, 1],
  advertencia: [2, 3, 1, 2, 4, 2, 3, 3],
  informacion: [4, 3, 5, 4, 6, 5, 7, 6],
}

const dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom', 'Hoy']

function Alertas() {
  const { user, accessToken } = useAuth()
  const [alertas, setAlertas] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let activo = true
    api.get('/alertas', { token: accessToken })
      .then((data) => {
        if (activo) setAlertas(data)
      })
      .catch((err) => {
        if (activo) setError(err.message || 'No se pudieron cargar las alertas.')
      })
    return () => { activo = false }
  }, [accessToken])

  const visibles = alertas.length ? alertas : alertasRecientes
  const nombre = user?.usu_nom || 'Nombre Usuario'
  const cargo = user?.usu_rol || 'Cargo'

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
                      <span className="resumen-num">0.15</span>
                      <span className="resumen-desc">/min</span>
                    </div>
                    <span className="resumen-icono anomalias">
                      <IconAlerta />
                    </span>
                  </div>
                </div>

                <div className="resumen-celda grafico">
                  <MiniChart data={anomalias24h} />
                </div>
              </div>
            </article>

            <div className="alertas-secundario">
              <article className="card alerts-tabla-card">
                <div className="card-head">
                  <h3 className="card-title">Anomalías detectadas</h3>
                </div>
                <AnomaliasTable />
              </article>

              <article className="card tendencia-card">
                <div className="card-head">
                  <h3 className="card-title">Tendencia de severidad</h3>
                </div>
                <TendenciaChart />
                <div className="tendencia-leyenda">
                  <span className="leyenda-item criticas">Críticas</span>
                  <span className="leyenda-item advertencia">Advertencia</span>
                  <span className="leyenda-item informacion">Información</span>
                </div>
              </article>
            </div>

            <div className="alertas-raiz-row">
              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Análisis de correlación y causa raíz</h3>
                </div>
                <CorrelacionRaiz />
              </article>

              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Historia de eventos de la sesión</h3>
                </div>
                <HistoriaSesion />
              </article>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Alertas
