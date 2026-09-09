import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import '../css/Layout.css'
import '../css/Dashboard.css'

const disponibilidadData = [99.98, 99.95, 100, 99.97, 99.99, 99.96, 100]

const DISP_CHART_W = 520
const DISP_CHART_H = 130
const DISP_PAD_L = 8
const DISP_PAD_R = 12
const DISP_PAD_T = 10
const DISP_PAD_B = 26
const DISP_PLOT_W = DISP_CHART_W - DISP_PAD_L - DISP_PAD_R
const DISP_PLOT_H = DISP_CHART_H - DISP_PAD_T - DISP_PAD_B

const DISP_MIN = 99.8
const DISP_MAX = 100.01

function barChartData(data, min, max) {
  return data.map((v, i) => ({
    x: DISP_PAD_L + (i * DISP_PLOT_W) / (data.length - 1),
    y: DISP_PAD_T + (1 - (v - min) / (max - min)) * DISP_PLOT_H,
  }))
}

function BarChart({ data }) {
  const pts = barChartData(data, DISP_MIN, DISP_MAX)
  const ptsStr = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const last = pts[pts.length - 1]
  const dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
  return (
    <svg className="dash-disp-chart" viewBox={`0 0 ${DISP_CHART_W} ${DISP_CHART_H}`} role="img">
      <defs>
        <linearGradient id="grad-disp" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0269a1" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#0269a1" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`${DISP_PAD_L},${DISP_CHART_H - DISP_PAD_B} ${ptsStr} ${DISP_CHART_W - DISP_PAD_R},${DISP_CHART_H - DISP_PAD_B}`} fill="url(#grad-disp)" />
      <polyline points={ptsStr} fill="none" stroke="#0269a1" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last.x} cy={last.y} r="4.5" fill="#0269a1" stroke="#ffffff" strokeWidth="2" />
      {dias.map((d, i) => (
        <text key={d} x={pts[i].x} y={DISP_CHART_H - 8} textAnchor="middle" fontSize="12" fill="#6b7683" fontWeight="500">
          {d}
        </text>
      ))}
    </svg>
  )
}

const rendimientoData = [380, 420, 400, 460, 440, 410, 430]

const BARS_W = 340
const BARS_H = 130
const BARS_PAD_L = 8
const BARS_PAD_R = 12
const BARS_PAD_T = 10
const BARS_PAD_B = 26
const BARS_PLOT_W = BARS_W - BARS_PAD_L - BARS_PAD_R
const BARS_PLOT_H = BARS_H - BARS_PAD_T - BARS_PAD_B
const BAR_W = 26
const BAR_MAX = 500

function BarraChart({ data }) {
  const n = data.length
  const step = BARS_PLOT_W / n
  const dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
  return (
    <svg className="dash-bar-chart" viewBox={`0 0 ${BARS_W} ${BARS_H}`} role="img">
      {data.map((v, i) => {
        const bw = Math.min(BAR_W, step * 0.6)
        const x = BARS_PAD_L + i * step + (step - bw) / 2
        const h = (v / BAR_MAX) * BARS_PLOT_H
        const y = BARS_H - BARS_PAD_B - h
        return (
          <g key={dias[i]}>
            <rect x={x} y={y} width={bw} height={h} rx="5" fill="#0269a1" />
            <text x={x + bw / 2} y={BARS_H - 8} textAnchor="middle" fontSize="12" fill="#6b7683" fontWeight="500">
              {dias[i]}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function IconInfo() {
  return (
    <svg viewBox="0 0 24 24" fill="none" width="28" height="28">
      <circle cx="12" cy="12" r="11" stroke="#0269a1" strokeWidth="2" fill="none" />
      <line x1="12" y1="11" x2="12" y2="17" stroke="#0269a1" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="8" r="1.2" fill="#0269a1" />
    </svg>
  )
}

const REC_W = 420
const REC_H = 160
const REC_PAD_L = 36
const REC_PAD_R = 12
const REC_PAD_T = 10
const REC_PAD_B = 26
const REC_PLOT_W = REC_W - REC_PAD_L - REC_PAD_R
const REC_PLOT_H = REC_H - REC_PAD_T - REC_PAD_B

const cpuPercentData = [42, 45, 40, 47, 52, 49, 55, 53, 60, 57, 62, 58]
const memPercentData = [58, 60, 59, 63, 62, 66, 64, 68, 67, 71, 69, 73]

const REC_HORAS = [
  [0, '00:00'],
  [4, '04:00'],
  [8, '08:00'],
  [12, '12:00'],
  [16, '16:00'],
  [20, '20:00'],
  [23, '23:00'],
]

function recPts(data) {
  return data.map((v, i) => ({
    x: REC_PAD_L + (i * REC_PLOT_W) / (data.length - 1),
    y: REC_PAD_T + (1 - v / 100) * REC_PLOT_H,
  }))
}

function recGrid() {
  const max = 100
  const levels = [0, 20, 40, 60, 80, 100]
  return (
    <g>
      {levels.map((lv) => {
        const y = REC_PAD_T + (1 - lv / max) * REC_PLOT_H
        return (
          <g key={lv}>
            <line x1={REC_PAD_L} y1={y} x2={REC_W - REC_PAD_R} y2={y} stroke="rgba(19,41,61,0.08)" strokeDasharray="4 4" />
            <text x={REC_PAD_L - 6} y={y + 3} textAnchor="end" fontSize="8" fill="#8a94a0">
              {lv}
            </text>
          </g>
        )
      })}
      {REC_HORAS.map(([i, label]) => (
        <text key={label} x={REC_PAD_L + (i * REC_PLOT_W) / 23} y={REC_H - 7} textAnchor="middle" fontSize="8" fill="#8a94a0">
          {label}
        </text>
      ))}
    </g>
  )
}

function RecursoChart({ series }) {
  return (
    <svg className="dash-rec-chart" viewBox={`0 0 ${REC_W} ${REC_H}`} role="img">
      <defs>
        <linearGradient id="grad-cpu" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0269a1" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#0269a1" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="grad-mem" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#d97706" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#d97706" stopOpacity="0" />
        </linearGradient>
      </defs>
      {recGrid()}
      {series.map((s) => {
        const pts = recPts(s.data)
        const ptsStr = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
        const last = pts[pts.length - 1]
        const gradId = s.label === 'CPU' ? 'grad-cpu' : 'grad-mem'
        return (
          <g key={s.label}>
            <polygon
              points={`${REC_PAD_L},${REC_H - REC_PAD_B} ${ptsStr} ${REC_W - REC_PAD_R},${REC_H - REC_PAD_B}`}
              fill={`url(#${gradId})`}
            />
            <polyline
              points={ptsStr}
              fill="none"
              stroke={s.color}
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeDasharray={s.dashed ? '6 5' : undefined}
            />
            <circle cx={last.x} cy={last.y} r="4.5" fill={s.color} stroke="#ffffff" strokeWidth="2" />
          </g>
        )
      })}
    </svg>
  )
}

const anomaliasTemporales = [
  { nivel: 'Normal', color: '#16a34a' },
  { nivel: 'Alerta baja', color: '#eab308' },
  { nivel: 'Alerta alta', color: '#dc2626' },
]

const GRID_COLS = 30

function MapaAnomalias() {
  const generateRow = (row, baseColor) =>
    Array.from({ length: GRID_COLS }).map((_, c) => {
      if (row === 0 && c % 11 === 3) return '#eab308'
      if (row === 0 && c % 17 === 9) return '#dc2626'
      if (row === 1 && c % 9 === 2) return '#f97316'
      if (row === 1 && c % 13 === 5) return '#16a34a'
      if (row === 1 && c % 13 === 6) return '#dc2626'
      if (row === 2 && c % 7 === 3) return '#f97316'
      if (row === 2 && c % 9 === 1) return '#eab308'
      if (row === 2 && c % 11 === 8) return '#16a34a'
      return baseColor
    })

  const filasCuadros = anomaliasTemporales.map((a, row) => (
    <div key={a.nivel} className="dash-mapa-fila">
      <span className="dash-mapa-etiqueta">{a.nivel}</span>
      <div className="dash-mapa-cuadros">
        {generateRow(row, a.color).map((color, c) => (
          <span key={c} className="dash-mapa-cuadro" style={{ background: color }} />
        ))}
      </div>
    </div>
  ))

  const leyenda = (
    <div className="dash-mapa-leyenda">
      {anomaliasTemporales.map((a) => (
        <span key={a.nivel} className="dash-mapa-ley-item">
          <span className="dash-mapa-chip" style={{ background: a.color }} />
          {a.nivel}
        </span>
      ))}
    </div>
  )

  return (
    <div className="dash-mapa">
      {leyenda}
      {filasCuadros}
      {leyenda}
    </div>
  )
}

function Dashboard() {
  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre="Nombre Usuario" cargo="Cargo" />
        <main className="layout-content">
          <div className="dashboard">
            <div className="dash-top-row">
              <article className="card dash-disponibilidad">
                <div className="dash-disp-top">
                  <div className="dash-disp-text">
                    <h3 className="card-title">
                      Disponibilidad del sistema{' '}
                      <span className="dash-disp-sub">(Últimos 7 días)</span>
                    </h3>
                    <span className="dash-disp-value">99.97<small>%</small></span>
                  </div>
                  <BarChart data={disponibilidadData} />
                </div>
              </article>

              <article className="card dash-anomalias-rate">
                <div className="dash-anom-top">
                  <div className="dash-anom-text">
                    <h3 className="card-title">
                      Tasa de anomalías{' '}
                      <span className="dash-anom-sub">(Hora actual)</span>
                    </h3>
                    <span className="dash-anom-value">0.12<small>/min</small></span>
                  </div>
                  <span className="dash-anom-icon">
                    <IconInfo />
                  </span>
                </div>
              </article>
            </div>

            <div className="dash-top-row">
              <article className="card dash-rendimiento">
                <div className="dash-disp-top">
                  <div className="dash-disp-text">
                    <h3 className="card-title">
                      Rendimiento por consultas{' '}
                      <span className="dash-disp-sub">(Promedio)</span>
                    </h3>
                    <span className="dash-rend-value">420<small>ms</small></span>
                  </div>
                  <BarraChart data={rendimientoData} />
                </div>
              </article>

              <article className="card dash-sesiones">
                <div className="dash-anom-top">
                  <div className="dash-anom-text">
                    <h3 className="card-title">Estado de sesiones transaccionales</h3>
                    <div className="dash-ses-value">
                      <span className="dash-ses-activas">250</span>
                      <span className="dash-ses-sep">/</span>
                      <span className="dash-ses-inactivas">15</span>
                      <span className="dash-ses-label">activas / inactivas</span>
                    </div>
                  </div>
                </div>
              </article>
            </div>

            <div className="dash-top-row">
              <article className="card dash-recursos">
                <h3 className="card-title">Uso de recursos detallado</h3>
                <div className="dash-rec-head">
                  <div className="dash-rec-leyenda">
                    <span className="dash-ley-item"><span className="dash-ley-sq" style={{ background: '#0269a1' }} />CPU · 62%</span>
                    <span className="dash-ley-item"><span className="dash-ley-sq" style={{ background: '#d97706' }} />Memoria · 71%</span>
                  </div>
                </div>
                <RecursoChart
                  series={[
                    { label: 'CPU', color: '#0269a1', data: cpuPercentData },
                    { label: 'Memoria', color: '#d97706', data: memPercentData, dashed: true },
                  ]}
                />
              </article>

              <article className="card dash-mapa-anom">
                <h3 className="card-title">
                  Mapa de anomalías temporales{' '}
                  <span className="dash-disp-sub">(Día)</span>
                </h3>
                <MapaAnomalias />
              </article>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Dashboard