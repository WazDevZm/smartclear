/** Hand-rolled SVG charts — crisp on dark UI, zero dependencies. */

/** Donut chart: segments = [{ label, value, color }]. */
export function DonutChart({ segments, size = 164, thickness = 22, centerTop, centerBottom }) {
  const total = segments.reduce((a, s) => a + s.value, 0)
  const r = (size - thickness) / 2
  const circ = 2 * Math.PI * r
  let acc = 0
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label={segments.map(s => `${s.label}: ${s.value}`).join(', ')}>
      <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(15,23,42,0.09)" strokeWidth={thickness} fill="none" />
      {total > 0 && segments.filter(s => s.value > 0).map((s, i) => {
        const frac = s.value / total
        const dash = Math.max(frac * circ - 2.5, 0.75)
        const offset = -acc * circ
        acc += frac
        return (
          <circle key={i} cx={size / 2} cy={size / 2} r={r} stroke={s.color} strokeWidth={thickness} fill="none"
            strokeDasharray={`${dash} ${circ - dash}`} strokeDashoffset={offset} strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}>
            <title>{s.label}: {s.value}</title>
          </circle>
        )
      })}
      <text x={size / 2} y={size / 2 - 2} textAnchor="middle" dominantBaseline="middle" className="fill-slate-900 font-display font-bold" fontSize="26" fontWeight="800">{centerTop}</text>
      <text x={size / 2} y={size / 2 + 17} textAnchor="middle" dominantBaseline="middle" className="fill-slate-500" fontSize="10.5" fontWeight="600">{centerBottom}</text>
    </svg>
  )
}

/** Area + line chart for a daily series: data = [{ day, count }]. */
export function AreaChart({ data, height = 150, stroke = '#2DD4BF' }) {
  if (!data.length) return <div className="py-10 text-center text-xs text-slate-400">Not enough history yet</div>
  const W = 560, H = height, padL = 6, padR = 6, padT = 12, padB = 22
  if (data.length === 1) {
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Daily volume">
        <line x1={padL} x2={W - padR} y1={H / 2} y2={H / 2} stroke="rgba(15,23,42,0.14)" strokeDasharray="3 5" />
        <circle cx={W / 2} cy={H / 2} r="5" fill="#ffffff" stroke={stroke} strokeWidth="2.2"><title>{data[0].day}: {data[0].count}</title></circle>
        <text x={W / 2} y={H / 2 - 12} textAnchor="middle" fontSize="12" className="fill-slate-700" fontWeight="700">{data[0].count} docs on {data[0].day.slice(5)}</text>
        <text x={W / 2} y={H - 6} textAnchor="middle" fontSize="9" className="fill-slate-400" fontWeight="600">history builds up as real documents are processed</text>
      </svg>
    )
  }
  const max = Math.max(2, ...data.map(d => d.count))
  const x = (i) => padL + (i * (W - padL - padR)) / Math.max(1, data.length - 1)
  const y = (v) => padT + (1 - v / max) * (H - padT - padB)
  const pts = data.map((d, i) => [x(i), y(d.count)])
  const line = pts.map(([px, py], i) => `${i ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)}`).join(' ')
  const area = `${line} L${x(data.length - 1).toFixed(1)},${H - padB} L${x(0).toFixed(1)},${H - padB} Z`
  const gridVals = [0.33, 0.66, 1].map(f => Math.max(1, Math.round(max * f)))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Daily volume">
      <defs>
        <linearGradient id="volFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.32" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {gridVals.map((v, i) => (
        <g key={i}>
          <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke="rgba(15,23,42,0.08)" strokeDasharray="3 5" />
          <text x={W - padR} y={y(v) - 2.5} textAnchor="end" fontSize="9" className="fill-slate-400" fontWeight="600">{v}</text>
        </g>
      ))}
      <path d={area} fill="url(#volFill)" />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
      {pts.map(([px, py], i) => {
        const show = i === 0 || i === pts.length - 1 || i === Math.floor(pts.length / 2)
        return show ? <circle key={i} cx={px} cy={py} r="3" fill="#ffffff" stroke={stroke} strokeWidth="1.6"><title>{data[i].day}: {data[i].count}</title></circle> : null
      })}
      {[[0, 'start'], [Math.floor(data.length / 2), 'middle'], [data.length - 1, 'end']].map(([i, anchor], k) => (
        <text key={k} x={x(i)} y={H - 6} textAnchor={anchor} fontSize="9" className="fill-slate-400" fontWeight="600">{data[i].day.slice(5)}</text>
      ))}
    </svg>
  )
}

/** Horizontal bar row with a track — the dashboard workhorse. */
export function BarRow({ label, value, max, color = '#2DD4BF', right }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="truncate text-slate-700">{label}</span>
        <span className="shrink-0 font-mono text-slate-500">{right ?? value}</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}
