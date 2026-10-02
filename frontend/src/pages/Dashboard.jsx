import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import { useSystemMetrics } from '../hooks/useSystemMetrics.js'
import { useTelemetria } from '../hooks/useTelemetria.js'
import { useAuth } from '../context/AuthContext.jsx'
import {
  useDashboardHeatmap,
  useDashboardDisponibilidad,
  useDashboardTransacciones,
  useDashboardAnomaliasResumen,
} from '../hooks/useDashboardData.js'
import '../css/Layout.css'
import '../css/Dashboard.css'

const DISP_CHART_W = 520
const DISP_CHART_H = 130
const DISP_PAD_L = 8
const DISP_PAD_R = 12
const DISP_PAD_T = 10
const DISP_PAD_B = 26
const DISP_PLOT_W = DISP_CHART_W - DISP_PAD_L - DISP_PAD_R
const DISP_PLOT_H = DISP_CHART_H - DISP_PAD_T - DISP_PAD_B

const DISP_MIN = 0
const DISP_MAX = 100

function barChartData(data, min, max) {
  const n = Math.max(data.length, 2)
  return data.map((v, i) => {
    if (!Number.isFinite(v)) return null
    return {
      x: DISP_PAD_L + (i * DISP_PLOT_W) / (n - 1),
      y: DISP_PAD_T + (1 - (Math.min(Math.max(v, min), max) - min) / (max - min)) * DISP_PLOT_H,
    }
  })
}

function BarChart({ data, etiquetas }) {
  // Con datos reales la disponibilidad varia (no siempre 99.8-100), asi que
  // el eje arranca en 0. Antes el rango fijo 99.8..100.01 aplastaba cualquier
  // valor distinto de 100 contra el borde.
  if (!data || data.length === 0) {
    return (
      <svg className="dash-disp-chart" viewBox={`0 0 ${DISP_CHART_W} ${DISP_CHART_H}`} role="img">
        <text x={DISP_CHART_W / 2} y={DISP_CHART_H / 2} textAnchor="middle" fontSize="12" fill="#8a94a0">
          Sin ventanas evaluadas
        </text>
      </svg>
    )
  }
  const pts = barChartData(data, DISP_MIN, DISP_MAX)
  if (!pts.some(Boolean)) {
    return (
      <svg className="dash-disp-chart" viewBox={`0 0 ${DISP_CHART_W} ${DISP_CHART_H}`} role="img">
        <text x={DISP_CHART_W / 2} y={DISP_CHART_H / 2} textAnchor="middle" fontSize="12" fill="#8a94a0">
          Sin ventanas evaluadas
        </text>
      </svg>
    )
  }
  const noms = etiquetas && etiquetas.length === data.length
    ? etiquetas
    : data.map((_, i) => `${i + 1}`)
  return (
    <svg className="dash-disp-chart" viewBox={`0 0 ${DISP_CHART_W} ${DISP_CHART_H}`} role="img">
      <line x1={DISP_PAD_L} y1={DISP_CHART_H - DISP_PAD_B} x2={DISP_CHART_W - DISP_PAD_R} y2={DISP_CHART_H - DISP_PAD_B} stroke="rgba(19,41,61,0.12)" />
      {pts.map((p, i) => p && pts[i + 1] && (
        <line key={`line-${i}`} x1={p.x} y1={p.y} x2={pts[i + 1].x} y2={pts[i + 1].y} stroke="#0269a1" strokeWidth="2.5" />
      ))}
      {pts.map((p, i) => p && (
        <circle key={noms[i]} cx={p.x} cy={p.y} r="4.5" fill="#0269a1" stroke="#ffffff" strokeWidth="2">
          <title>{`${data[i]}%`}</title>
        </circle>
      ))}
      {noms.map((nombre, i) => (
        <text key={nombre} x={DISP_PAD_L + (i * DISP_PLOT_W) / Math.max(data.length - 1, 1)} y={DISP_CHART_H - 8} textAnchor="middle" fontSize="12" fill="#6b7683" fontWeight="500">
          {nombre}
        </text>
      ))}
    </svg>
  )
}

const BARS_W = 340
const BARS_H = 130
const BARS_PAD_L = 8
const BARS_PAD_R = 12
const BARS_PAD_T = 10
const BARS_PAD_B = 26
const BARS_PLOT_W = BARS_W - BARS_PAD_L - BARS_PAD_R
const BARS_PLOT_H = BARS_H - BARS_PAD_T - BARS_PAD_B
const BAR_W = 26

function BarraChart({ data, etiquetas }) {
  const safe = data.length >= 1 ? data : [0]
  const n = safe.length
  const step = BARS_PLOT_W / n
  const top = Math.max(1, ...safe.filter(Number.isFinite))
  const nombres = etiquetas && etiquetas.length === n ? etiquetas : safe.map((_, i) => `#${i + 1}`)
  return (
    <svg className="dash-bar-chart" viewBox={`0 0 ${BARS_W} ${BARS_H}`} role="img">
      <line x1={BARS_PAD_L} y1={BARS_H - BARS_PAD_B} x2={BARS_W - BARS_PAD_R} y2={BARS_H - BARS_PAD_B} stroke="rgba(19,41,61,0.12)" />
      {safe.map((v, i) => {
        const bw = Math.min(BAR_W, step * 0.6)
        const x = BARS_PAD_L + i * step + (step - bw) / 2
        const valido = Number.isFinite(v)
        const h = valido ? Math.max((v / top) * BARS_PLOT_H, v > 0 ? 2 : 0) : 0
        const y = BARS_H - BARS_PAD_B - h
        return (
          <g key={`${i}-${nombres[i]}`}>
            {valido && <rect x={x} y={y} width={bw} height={h} rx="5" fill="#0269a1" />}
            <title>{valido ? `${Number(v).toFixed(2)} tx/s` : 'Sin datos'}</title>
            <text x={x + bw / 2} y={BARS_H - 8} textAnchor="middle" fontSize="12" fill="#6b7683" fontWeight="500">
              {nombres[i]}
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

function recPts(data) {
  if (!data || data.length === 0) {
    return [{ x: REC_PAD_L + REC_PLOT_W, y: REC_H - REC_PAD_B }]
  }
  if (data.length === 1) {
    return [{
      x: REC_PAD_L + REC_PLOT_W,
      y: REC_PAD_T + (1 - Number(data[0] || 0) / 100) * REC_PLOT_H,
    }]
  }
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
    </g>
  )
}

function RecursoChart({ series }) {
  // El eje X del grid marca 00:00..23:00, pero la serie son las ultimas N
  // muestras en tiempo real (cada 3s), no 24 horas. Se relabelean las marcas
  // como "hace N muestras" para no mentir sobre el eje.
  const total = Math.max(...series.map((s) => s.data.length), 1)
  const marcas = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (total - 1)))
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
      {marcas.map((idx, i) => (
        <text
          key={i}
          x={REC_PAD_L + (idx * REC_PLOT_W) / Math.max(total - 1, 1)}
          y={REC_H - 7}
          textAnchor={i === 0 ? 'start' : i === marcas.length - 1 ? 'end' : 'middle'}
          fontSize="8"
          fill="#8a94a0"
        >
          {`#${idx + 1}`}
        </text>
      ))}
    </svg>
  )
}

const NIVELES_HEATMAP = [
  { nivel: 'Normal', sev: 'normal', color: '#16a34a' },
  { nivel: 'Alerta baja', sev: 'alerta_baja', color: '#eab308' },
  { nivel: 'Alerta alta', sev: 'alerta_alta', color: '#dc2626' },
]

const GRID_COLS = 24

function MapaAnomalias({ datos }) {
  const grid = Array.from({ length: 3 }).map(() => Array(GRID_COLS).fill(0))
  if (datos && datos.length > 0) {
    for (const d of datos) {
      const sevIdx = NIVELES_HEATMAP.findIndex((n) => n.sev === d.severidad)
      if (sevIdx >= 0 && d.hora >= 0 && d.hora < GRID_COLS) {
        grid[sevIdx][d.hora] = d.cantidad
      }
    }
  }

  const maxCant = Math.max(1, ...grid.flat())

  const filasCuadros = NIVELES_HEATMAP.map((a, row) => (
    <div key={a.sev} className="dash-mapa-fila">
      <span className="dash-mapa-etiqueta">{a.nivel}</span>
      <div className="dash-mapa-cuadros">
        {grid[row].map((cant, c) => (
          <span
            key={c}
            className="dash-mapa-cuadro"
            style={{
              background: cant > 0 ? a.color : '#e5e7eb',
              opacity: cant > 0 ? 0.5 + (cant / maxCant) * 0.5 : 1,
            }}
            title={`${c}:00 - ${cant} anomalías`}
          />
        ))}
      </div>
    </div>
  ))

  const leyenda = (
    <div className="dash-mapa-leyenda">
      {NIVELES_HEATMAP.map((a) => (
        <span key={a.sev} className="dash-mapa-ley-item">
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
    </div>
  )
}

function Dashboard() {
  const { actual } = useSystemMetrics(3000, 80)
  const { muestras, ultimaMuestra, serie } = useTelemetria(80)
  const { datos: heatmapDatos } = useDashboardHeatmap(60000)
  const { dias: dispDias, promedio: dispPromedio, etiquetas: dispEtiquetas, conDatos: dispConDatos } = useDashboardDisponibilidad(300000, 1)
  const { dias: transaccionesDias, promedio: transaccionesPromedio, etiquetas: transaccionesEtiquetas, conDatos: transaccionesConDatos } = useDashboardTransacciones(300000, 1)
  const { hora_actual_cant, alertas_activas } = useDashboardAnomaliasResumen(30000)
  const { user } = useAuth()

  

  // Nodo real: el primero con muestras en el buffer; fallback al nombre por defecto.
  const nodosTele = Object.keys(muestras)
  const nodo = nodosTele.length > 0 ? nodosTele[0] : 'Servidor Negocio'
  const muestra = ultimaMuestra(nodo) || {}
  const serieNodo = serie(nodo, 80)

  const leerCpu = (m) => Number(m?.cpu_usr ?? 0) + Number(m?.cpu_sys ?? 0)
  const cpuActual = serieNodo.length > 0
    ? leerCpu(serieNodo[serieNodo.length - 1]?.muestra)
    : actual?.cpu ?? 0
  const memActual = actual?.mem ?? 0

  const cpuData = serieNodo.length > 0
    ? serieNodo.map((m) => Number(leerCpu(m?.muestra)))
    : []
  const memData = serieNodo.length > 0
    ? serieNodo.map((m) => Number(m?.muestra?.memory_percent ?? 0))
    : []

  // Leemos las sesiones directamente desde el hook unificado actual, con respaldo al buffer
  const activas = actual?.active_sessions ?? Number(muestra.active_sessions ?? muestra.active_requests ?? 0)
  const inactivas = actual?.idle_sessions ?? Number(muestra.idle_sessions ?? muestra.long_queries ?? 0)

  const transaccionesActuales = serieNodo.length
    ? Number(serieNodo[serieNodo.length - 1]?.muestra?.transactions_per_sec ?? 0)
    : null

  const tasaAnomalias = (hora_actual_cant || 0) > 0
    ? `${hora_actual_cant}/h`
    : '0/h'

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout-main">
        <Topbar nombre={user ? user.usu_nom : 'Nombre Usuario'} cargo={user ? user.usu_rol : 'Cargo'} />
        <main className="layout-content">
          <div className="dashboard">
            <div className="dash-top-row">
              <article className="card dash-disponibilidad">
                <div className="dash-disp-top">
                  <div className="dash-disp-text">
                    <h3 className="card-title">
                      Disponibilidad estimada{' '}
                      <span className="dash-disp-sub">(ventanas normales, hoy)</span>
                    </h3>
                    <span className="dash-disp-value">
                      {dispConDatos ? dispPromedio : '—'}{dispConDatos && <small>%</small>}
                    </span>
                  </div>
                  <BarChart data={dispDias} etiquetas={dispEtiquetas} />
                </div>
              </article>

              <article className="card dash-anomalias-rate">
                <div className="dash-anom-top">
                  <div className="dash-anom-text">
                    <h3 className="card-title">
                      Tasa de anomalías{' '}
                      <span className="dash-anom-sub">(Hora actual)</span>
                    </h3>
                    <span className="dash-anom-value">{tasaAnomalias}</span>
                    <span className="dash-anom-sub">{alertas_activas} alertas activas</span>
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
                      Transacciones SQL <span className="dash-disp-sub">(hoy)</span>
                    </h3>
                    <span className="dash-rend-value">
                      {transaccionesActuales === null ? '—' : transaccionesActuales.toFixed(2)}
                      {transaccionesActuales !== null && <small> tx/s</small>}
                    </span>
                    <span className="dash-disp-sub">
                      {transaccionesConDatos
                        ? `Promedio de hoy: ${transaccionesPromedio.toFixed(2)} tx/s`
                        : 'Sin muestras de hoy todavía'}
                    </span>
                  </div>
                  {transaccionesDias.length === 7 ? (
                    <BarraChart
                      data={transaccionesDias}
                      etiquetas={transaccionesEtiquetas}
                    />
                  ) : <p className="dash-chart-empty">Cargando...</p>}
                </div>
              </article>

              <article className="card dash-sesiones">
                <div className="dash-anom-top">
                  <div className="dash-anom-text">
                    <h3 className="card-title">Estado de sesiones transaccionales</h3>
                    <div className="dash-ses-value">
                      <span className="dash-ses-activas">{activas}</span>
                      <span className="dash-ses-sep">/</span>
                      <span className="dash-ses-inactivas">{inactivas}</span>
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
                    <span className="dash-ley-item"><span className="dash-ley-sq" style={{ background: '#0269a1' }} />CPU · {cpuActual}%</span>
                    <span className="dash-ley-item"><span className="dash-ley-sq" style={{ background: '#d97706' }} />Memoria · {memActual}%</span>
                  </div>
                </div>
                <RecursoChart
                  series={[
                    { label: 'CPU', color: '#0269a1', data: cpuData.length > 0 ? cpuData : [0] },
                    { label: 'Memoria', color: '#d97706', data: memData.length > 0 ? memData : [0], dashed: true },
                  ]}
                />
              </article>

              <article className="card dash-mapa-anom">
                <h3 className="card-title">
                  Mapa de anomalías temporales{' '}
                  <span className="dash-disp-sub">(hoy)</span>
                </h3>
                <MapaAnomalias datos={heatmapDatos} />
              </article>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Dashboard

