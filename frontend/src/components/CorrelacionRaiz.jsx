import '../css/CorrelacionRaiz.css'

const CAUSA_RAIZ = {
  label: 'Pico de CPU · Nodo SCADA-02',
  tone: 'root',
  children: [
    {
      label: 'Lectura pesada en BD',
      tone: 'warn',
      children: [
        { label: 'Query sin índice', tone: 'leaf' },
        { label: 'Histórico 24 h', tone: 'leaf' },
      ],
    },
    {
      label: 'Cola de workers saturada',
      tone: 'warn',
      children: [
        { label: 'Recompute del modelo', tone: 'leaf' },
        { label: 'Export masivo', tone: 'leaf' },
      ],
    },
  ],
}

const NODE_W = 200
const NODE_H = 48
const CX = [50, 350, 670]
const CY0 = 255
const CY1 = [148, 362]
const CY2 = [95, 200, 305, 410]

const NODE_STYLE = {
  root: { fill: '#fdecec', stroke: '#dc2626', text: '#dc2626' },
  warn: { fill: '#fef4e6', stroke: '#d97706', text: '#b45309' },
  leaf: { fill: '#e8f3fa', stroke: '#0269a1', text: '#0269a1' },
}

function TreeNode({ cx, cy, tone, label }) {
  const style = NODE_STYLE[tone]
  return (
    <g>
      <rect
        x={cx}
        y={cy - NODE_H / 2}
        width={NODE_W}
        height={NODE_H}
        rx={9}
        fill={style.fill}
        stroke={style.stroke}
        strokeWidth="1.5"
      />
      <text
        x={cx + NODE_W / 2}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="14"
        fontWeight="700"
        fill={style.text}
      >
        {label}
      </text>
    </g>
  )
}

function Branch({ parentRight, parentCy, childLeftX, childCys }) {
  const bx = (parentRight + childLeftX) / 2
  return (
    <g stroke="rgba(19,41,61,0.35)" strokeWidth="1.5" fill="none">
      <line x1={parentRight} y1={parentCy} x2={bx} y2={parentCy} />
      <line x1={bx} y1={Math.min(...childCys)} x2={bx} y2={Math.max(...childCys)} />
      {childCys.map((cy) => (
        <line key={cy} x1={bx} y1={cy} x2={childLeftX} y2={cy} />
      ))}
    </g>
  )
}

function CorrelacionRaiz() {
  return (
    <svg
      className="causa-svg"
      viewBox="0 0 900 460"
      role="img"
      aria-label="Análisis de correlación y causa raíz"
    >
      <Branch parentRight={CX[0] + NODE_W} parentCy={CY0} childLeftX={CX[1]} childCys={CY1} />
      {CY1.map((cy, i) => (
        <Branch
          key={cy}
          parentRight={CX[1] + NODE_W}
          parentCy={cy}
          childLeftX={CX[2]}
          childCys={[CY2[i * 2], CY2[i * 2 + 1]]}
        />
      ))}

      <TreeNode cx={CX[0]} cy={CY0} tone={CAUSA_RAIZ.tone} label={CAUSA_RAIZ.label} />
      {CAUSA_RAIZ.children.map((n, i) => (
        <TreeNode key={n.label} cx={CX[1]} cy={CY1[i]} tone={n.tone} label={n.label} />
      ))}
      {CAUSA_RAIZ.children.flatMap((n) => n.children).map((n, i) => (
        <TreeNode key={n.label} cx={CX[2]} cy={CY2[i]} tone={n.tone} label={n.label} />
      ))}
    </svg>
  )
}

export default CorrelacionRaiz