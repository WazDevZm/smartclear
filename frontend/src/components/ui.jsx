import { AlertTriangle, CheckCircle2, CircleHelp, ShieldAlert, ShieldCheck, ShieldQuestion, XCircle } from 'lucide-react'

export const bandMeta = {
  clear: { label: 'Clear', cls: 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/25', dot: 'bg-emerald-400', Icon: ShieldCheck },
  review: { label: 'Review', cls: 'bg-amber-400/10 text-amber-300 ring-amber-400/25', dot: 'bg-amber-400', Icon: ShieldQuestion },
  high: { label: 'High risk', cls: 'bg-rose-500/10 text-rose-300 ring-rose-400/25', dot: 'bg-rose-400', Icon: ShieldAlert },
}

export function BandBadge({ band, score }) {
  const m = bandMeta[band] || bandMeta.review
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${m.cls}`}>
      <m.Icon size={13} /> {m.label}{score !== undefined && <span className="opacity-70">· {Math.round(score)}</span>}
    </span>
  )
}

const statusMeta = {
  pending: ['Pending review', 'bg-sky-400/10 text-sky-300 ring-sky-400/25'],
  approved: ['Approved', 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/25'],
  rejected: ['Rejected', 'bg-rose-500/10 text-rose-300 ring-rose-400/25'],
  escalated: ['Escalated', 'bg-violet-400/10 text-violet-300 ring-violet-400/25'],
  info_requested: ['Info requested', 'bg-amber-400/10 text-amber-300 ring-amber-400/25'],
}
export function StatusBadge({ status }) {
  const [l, c] = statusMeta[status] || [status, 'bg-white/5 text-slate-300 ring-white/10']
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${c}`}>{l}</span>
}

export function OutcomeIcon({ outcome, size = 16 }) {
  if (outcome === 'match') return <CheckCircle2 size={size} className="text-emerald-400" />
  if (outcome === 'mismatch') return <XCircle size={size} className="text-rose-400" />
  if (outcome === 'partial') return <AlertTriangle size={size} className="text-amber-400" />
  return <CircleHelp size={size} className="text-slate-400" />
}

export const outcomeText = { match: 'Match', mismatch: 'Mismatch', partial: 'Partial', unreadable: 'Unreadable',
  no_record: 'No record', review: 'Needs review' }

export function Stat({ label, value, sub, accent = 'from-zra-sky to-clear-400', Icon }) {
  return (
    <div className="card relative overflow-hidden p-5">
      <div className={`absolute -right-8 -top-8 h-24 w-24 rounded-full bg-gradient-to-br ${accent} opacity-10 blur-2xl`} />
      <div className="flex items-center justify-between">
        <div className="label">{label}</div>
        {Icon && <Icon size={16} className="text-slate-500" />}
      </div>
      <div className="mt-3 font-display text-3xl font-bold text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  )
}

export function Spinner({ className = '' }) {
  return <div className={`h-5 w-5 animate-spin rounded-full border-2 border-white/20 border-t-clear-400 ${className}`} />
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  )
}

export const pct = (v, d = 1) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(d)}%`)
