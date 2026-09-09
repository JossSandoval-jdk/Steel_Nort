import '../css/HistoriaSesion.css'

const EVENTOS = [
  { min: 0, color: '#15803d', texto: 'Login correcto' },
  { min: 2, color: '#0269a1', texto: 'Consulta API al conciliador' },
  { min: 4, color: '#d97706', texto: 'Latencia > 400 ms' },
  { min: 5, color: '#dc2626', texto: 'Reintento fallido' },
  { min: 8, color: '#0269a1', texto: 'Lectura de contadores SCADA' },
  { min: 12, color: '#d97706', texto: 'Timeout parcial' },
  { min: 15, color: '#52606d', texto: 'Cierre de sesión' },
]

const LEYENDA = [
  { color: '#15803d', label: 'Login' },
  { color: '#0269a1', label: 'Lectura / API' },
  { color: '#d97706', label: 'Advertencia' },
  { color: '#dc2626', label: 'Error' },
  { color: '#52606d', label: 'Cierre' },
]

const W = 1100
const H = 270
const L = 60
const R = 60
const MIN_MAX = 15
const LINE_Y = 115
const PP_MIN = (W - L - R) / MIN_MAX

const xAt = (min) => L + min * PP_MIN
const fmtClock = (min) => `${String(min).padStart(2, '0')}:00`

function HistoriaSesion() {
  return (
    <>
      <svg className="sesion-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Historia de eventos de la sesión">
        <line x1={L} y1={LINE_Y} x2={W - R} y2={LINE_Y} stroke="#d7dde3" strokeWidth="4" strokeLinecap="round" />

        {Array.from({ length: MIN_MAX + 1 }, (_, min) => {
          const cx = xAt(min)
          return (
            <g key={min}>
              <line x1={cx} y1={LINE_Y - 6} x2={cx} y2={LINE_Y + 6} stroke="#9aa4ae" strokeWidth="2" />
              <text x={cx} y={LINE_Y + 26} textAnchor="middle" fontSize="11" fill="#8a94a0">
                {min}
              </text>
            </g>
          )
        })}

        {EVENTOS.map((e, i) => {
          const cx = xAt(e.min)
          const anchor = cx < 80 ? 'start' : cx > W - R - 90 ? 'end' : 'middle'
          const lx = anchor === 'start' ? cx + 18 : anchor === 'end' ? cx - 18 : cx
          const descY = i % 2 === 0 ? 196 : 238
          return (
            <g key={e.min}>
              <rect x={cx - 9} y={LINE_Y - 9} width="18" height="18" rx="4" fill={e.color} stroke="#ffffff" strokeWidth="3" />
              <text x={lx} y={LINE_Y - 24} textAnchor={anchor} fontSize="12" fontWeight="700" fill={e.color}>
                {fmtClock(e.min)}
              </text>
              <text x={lx} y={descY} textAnchor={anchor} fontSize="13" fontWeight="500" fill="#52606d">
                {e.texto}
              </text>
            </g>
          )
        })}
      </svg>

      <div className="sesion-leyenda">
        {LEYENDA.map((it) => (
          <span key={it.label} className="sesion-leyenda-item">
            <span className="sesion-leyenda-sq" style={{ background: it.color }} />
            {it.label}
          </span>
        ))}
      </div>
    </>
  )
}

export default HistoriaSesion