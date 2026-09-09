import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { useSystemMetrics } from '../hooks/useSystemMetrics.js'
import '../css/Layout.css'
import '../css/Inicio.css'

const anomaliasData = [1, 0, 2, 1, 0, 1, 3, 2, 4, 3, 5, 4, 2, 6, 3, 4, 12, 5, 3, 4, 2, 3, 1, 2]

const CHART_W = 640
const CHART_H = 250
const PAD_L = 42
const PAD_R = 16
const PAD_T = 14
const PAD_B = 30
const PLOT_W = CHART_W - PAD_L - PAD_R
const PLOT_H = CHART_H - PAD_T - PAD_B

const HOUR_TICKS = [
  [0, '00:00'],
  [6, '06:00'],
  [12, '12:00'],
  [18, '18:00'],
  [23, '23:00'],
]

function IconCpu() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <line x1="9" y1="1" x2="9" y2="4" />
      <line x1="15" y1="1" x2="15" y2="4" />
      <line x1="9" y1="20" x2="9" y2="23" />
      <line x1="15" y1="20" x2="15" y2="23" />
      <line x1="20" y1="9" x2="23" y2="9" />
      <line x1="20" y1="14" x2="23" y2="14" />
      <line x1="1" y1="9" x2="4" y2="9" />
      <line x1="1" y1="14" x2="4" y2="14" />
    </svg>
  )
}

function IconMemoria() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="12" x2="2" y2="12" />
      <path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
      <line x1="6" y1="16" x2="6.01" y2="16" />
      <line x1="10" y1="16" x2="10.01" y2="16" />
    </svg>
  )
}

function IconAnomalia() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

function IconSesiones() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

// Formatea un timestamp ISO a HH:MM:SS local.
function fmtHora(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// Formatea un timestamp ISO a HH:MM (para marcas del eje X).
function fmtHoraMinuto(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}`
}

// Construye los puntos del grafico a partir de un array de valores 0..max.
function buildPoints(data, max) {
  if (!data || data.length < 2) return [[]]
  return [data.map((v, i) => ({
    x: PAD_L + (i * PLOT_W) / (data.length - 1),
    y: PAD_T + (1 - v / max) * PLOT_H,
  }))]
}

const fmtPoint = (p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`

// Eje Y simple de fondo.
function PintarEjes({ max }) {
  const levels = [0, max / 2, max]
  return (
    <g>
      {levels.map((lv) => {
        const y = PAD_T + (1 - lv / max) * PLOT_H
        return (
          <g key={lv}>
            <line x1={PAD_L} y1={y} x2={CHART_W - PAD_R} y2={y} stroke="rgba(19,41,61,0.08)" strokeDasharray="4 4" />
            <text x={PAD_L - 8} y={y + 4} textAnchor="end" fontSize="11" fill="#8a94a0">
              {Math.round(lv)}
            </text>
          </g>
        )
      })}
    </g>
  )
}

// Grafico de linea unico para las series en vivo.
function LineChart({ id, data, labels, max = 100, estado }) {
  const [pts] = buildPoints(data, max)
  if (!pts.length) {
    return (
      <div className="chart-empty">
        {estado || 'Esperando datos del sistema…'}
      </div>
    )
  }
  const ptsStr = pts.map(fmtPoint).join(' ')
  const last = pts[pts.length - 1]
  // Ticks de hora: toma hasta 4 marcas distribuidas en el historial.
  const tickIdxs = []
  for (let i = 0; i < 5; i += 1) {
    const idx = Math.round((i * (data.length - 1)) / 4)
    if (!tickIdxs.includes(idx)) tickIdxs.push(idx)
  }
  return (
    <svg className="chart-svg" viewBox={`0 0 ${CHART_W} ${CHART_H}`} role="img">
      <defs>
        <linearGradient id={`grad-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0269a1" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#0269a1" stopOpacity="0" />
        </linearGradient>
      </defs>
      <PintarEjes max={max} />
      {tickIdxs.map((idx) => (
        <text
          key={idx}
          x={PAD_L + (idx * PLOT_W) / (data.length - 1)}
          y={CHART_H - 8}
          textAnchor="middle"
          fontSize="11"
          fill="#8a94a0"
        >
          {labels[idx] != null ? labels[idx] : ''}
        </text>
      ))}
      <polygon points={`${PAD_L},${CHART_H - PAD_B} ${ptsStr} ${CHART_W - PAD_R},${CHART_H - PAD_B}`} fill={`url(#grad-${id})`} />
      <polyline points={ptsStr} fill="none" stroke="#0269a1" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last.x} cy={last.y} r="4.5" fill="#0269a1" stroke="#ffffff" strokeWidth="2" />
    </svg>
  )
}

function AnomalyChart({ data }) {
  const max = Math.max(...data) + 2
  const pts = buildPoints(data, max)[0]
  const peakIdx = data.indexOf(Math.max(...data))
  const ptsStr = pts.map(fmtPoint).join(' ')

  const beforeStr = pts.slice(0, peakIdx + 1).map(fmtPoint).join(' ')
  const peakStr = pts.slice(Math.max(peakIdx - 1, 0), Math.min(peakIdx + 2, pts.length)).map(fmtPoint).join(' ')
  const afterStr = pts.slice(peakIdx + 1).map(fmtPoint).join(' ')

  const peak = pts[peakIdx]
  const labelX = Math.min(Math.max(peak.x, PAD_L + 34), CHART_W - PAD_R - 40)
  const hora = `${String(peakIdx).padStart(2, '0')}:00`

  return (
    <svg className="chart-svg" viewBox={`0 0 ${CHART_W} ${CHART_H}`} role="img">
      <defs>
        <linearGradient id="grad-anomalias" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0269a1" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#0269a1" stopOpacity="0" />
        </linearGradient>
      </defs>
      <PintarEjes max={max} />
      {HOUR_TICKS.map(([i, label]) => {
        const idx = Math.round((i * (data.length - 1)) / 23)
        return (
          <text key={label} x={PAD_L + (idx * PLOT_W) / (data.length - 1)} y={CHART_H - 8} textAnchor="middle" fontSize="11" fill="#8a94a0">
            {label}
          </text>
        )
      })}
      <polygon points={`${PAD_L},${CHART_H - PAD_B} ${ptsStr} ${CHART_W - PAD_R},${CHART_H - PAD_B}`} fill="url(#grad-anomalias)" />
      <polyline points={beforeStr} fill="none" stroke="#0269a1" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {afterStr && (
        <polyline points={`${fmtPoint(pts[peakIdx])} ${afterStr}`} fill="none" stroke="#0269a1" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      )}
      <polyline points={peakStr} fill="none" stroke="#dc2626" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      <line x1={peak.x} y1={peak.y + 6} x2={peak.x} y2={CHART_H - PAD_B} stroke="#dc2626" strokeDasharray="4 4" strokeWidth="1.5" />
      <circle cx={peak.x} cy={peak.y} r="6" fill="#dc2626" stroke="#ffffff" strokeWidth="2.5" />
      <text x={labelX} y={peak.y - 14} textAnchor="middle" fontSize="13" fontWeight="700" fill="#dc2626">
        {`${data[peakIdx]} picos · ${hora}`}
      </text>
    </svg>
  )
}

const alertas = [
  { severidad: 'critica', titulo: 'Pico anómalo de CPU en nodo SCADA-02', meta: 'Crítica · Umbral superado por 6 min', hora: '16:04' },
  { severidad: 'alta', titulo: 'Múltiples intentos de acceso fallidos', meta: 'Alta · usuario svc_backup', hora: '14:37' },
  { severidad: 'media', titulo: 'Latencia elevada en base de datos', meta: 'Media · promedio 480 ms', hora: '11:20' },
  { severidad: 'baja', titulo: 'Certificado TLS próximo a vencer', meta: 'Baja · expira en 15 días', hora: '08:45' },
]

const estados = [
  { nombre: 'Servidor principal', desc: 'Uptime 99.98% · 42 días', estado: 'Operativo', tone: 'ok' },
  { nombre: 'Base de datos PostgreSQL', desc: '128 conexiones activas', estado: 'Operativo', tone: 'ok' },
  { nombre: 'Servicio SCADA', desc: 'Respuesta lenta últimos 20 min', estado: 'Degradado', tone: 'warn' },
  { nombre: 'Respaldos automáticos', desc: 'Último respaldo: hoy 02:00', estado: 'Programado', tone: 'info' },
]

function Inicio() {
  const { actual, historico, error } = useSystemMetrics(3000, 80)
  const user = useAuth().user

  // Series listas para los graficos.
  const cpuSerie = historico.map((h) => h.cpuTotal)
  const memSerie = historico.map((h) => h.memPercent)
  const labels = historico.map((h) => fmtHoraMinuto(h.ts))

  // Promedios mostrados en las insignias.
  const cpuProm = cpuSerie.length ? Math.round(cpuSerie.reduce((a, b) => a + b, 0) / cpuSerie.length) : 0
  const memProm = memSerie.length ? Math.round(memSerie.reduce((a, b) => a + b, 0) / memSerie.length) : 0
  const ultimaTs = historico.length ? fmtHora(historico[historico.length - 1].ts) : '—'

  const stats = [
    {
      id: 'cpu',
      label: 'CPU',
      value: actual ? String(actual.cpu) : '—',
      unit: '%',
      trend: actual ? `Última lectura ${ultimaTs}` : 'Conectando…',
      icon: IconCpu,
      tone: 'blue',
    },
    {
      id: 'memoria',
      label: 'Memoria',
      value: actual ? String(actual.mem) : '—',
      unit: '%',
      trend: actual ? `${Math.round(actual.memUsed)} / ${Math.round(actual.memTotal)} MB` : 'Conectando…',
      icon: IconMemoria,
      tone: 'green',
    },
    { id: 'anomalias', label: 'Anomalías detectadas', value: '14', unit: 'hoy', trend: '+3 respecto a ayer', icon: IconAnomalia, tone: 'red' },
    { id: 'sesiones', label: 'Sesiones activas', value: '8', unit: '', trend: '2 administradores', icon: IconSesiones, tone: 'cyan' },
  ]

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={user ? user.usu_nom : 'Nombre Usuario'} cargo={user ? user.usu_rol : 'Cargo'} />
        <main className="layout-content">
          <div className="inicio">
            {error && <div className="metrics-error">No se pudo conectar con las métricas del sistema: {error}</div>}

            <section className="stats-row">
              {stats.map(({ id, label, value, unit, trend, icon: Icon, tone }) => (
                <article key={id} className="card stat-card">
                  <div className="stat-head">
                    <span className="stat-label">{label}</span>
                    <span className={`stat-icon ${tone}`}>
                      <Icon />
                    </span>
                  </div>
                  <span className="stat-value">
                    {value}
                    {unit && <small>{unit}</small>}
                  </span>
                  <span className="stat-trend">{trend}</span>
                </article>
              ))}
            </section>

            <section className="charts-row">
              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Uso de CPU</h3>
                  <span className="chart-badge blue">Promedio {cpuProm}%</span>
                </div>
                <LineChart
                  id="cpu"
                  data={cpuSerie}
                  labels={labels}
                  max={100}
                  estado="Esperando datos de CPU…"
                />
              </article>

              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Uso de memoria</h3>
                  <span className="chart-badge blue">Promedio {memProm}%</span>
                </div>
                <LineChart
                  id="memoria"
                  data={memSerie}
                  labels={labels}
                  max={100}
                  estado="Esperando datos de memoria…"
                />
              </article>
            </section>

            <section className="bottom-row">
              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Anomalías</h3>
                  <span className="chart-badge red">Total hoy: 14</span>
                </div>
                <AnomalyChart data={anomaliasData} />
              </article>

              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Alertas recientes</h3>
                </div>
                <ul className="alert-list">
                  {alertas.map((a) => (
                    <li key={a.hora} className="alert-item">
                      <span className={`alert-dot ${a.severidad}`} />
                      <div className="alert-body">
                        <span className="alert-title">{a.titulo}</span>
                        <span className="alert-meta">{a.meta}</span>
                      </div>
                      <span className="alert-time">{a.hora}</span>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="card">
                <div className="card-head">
                  <h3 className="card-title">Estado del sistema</h3>
                </div>
                <ul className="status-list">
                  {estados.map((e) => (
                    <li key={e.nombre} className="status-item">
                      <div className="alert-body">
                        <span className="status-name">{e.nombre}</span>
                        <span className="status-desc">{e.desc}</span>
                      </div>
                      <span className={`pill ${e.tone}`}>{e.estado}</span>
                    </li>
                  ))}
                </ul>
              </article>
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Inicio