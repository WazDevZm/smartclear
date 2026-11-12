import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, CircleHelp, ShieldAlert, ShieldCheck, ShieldQuestion, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

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

// ---- Pagination -------------------------------------------------------------
export const PAGE_SIZES = [10, 25, 50, 100]

export function usePagination(rows, defaultPerPage = 25) {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(defaultPerPage)
  const total = rows?.length ?? 0
  const pageCount = Math.max(1, Math.ceil(total / perPage))
  useEffect(() => { setPage(1) }, [rows, perPage])
  const p = Math.min(page, pageCount)
  const start = (p - 1) * perPage
  const slice = rows ? rows.slice(start, start + perPage) : rows
  return { page: p, setPage, perPage, setPerPage, total, pageCount, slice,
           rangeStart: total ? start + 1 : 0, rangeEnd: Math.min(total, start + perPage) }
}

function pageNumbers(page, pageCount) {
  const want = new Set([1, pageCount, page - 1, page, page + 1])
  const pages = [...want].filter((n) => n >= 1 && n <= pageCount).sort((a, b) => a - b)
  const out = []
  let prev = 0
  for (const n of pages) {
    if (prev && n - prev > 1) out.push('…')
    out.push(n)
    prev = n
  }
  return out
}

export function Pagination({ page, pageCount, setPage, perPage, setPerPage, total, rangeStart, rangeEnd }) {
  if (total === 0) return null
  const btn = 'inline-flex h-8 min-w-8 items-center justify-center rounded-lg px-2 text-xs font-semibold transition'
  const idle = `${btn} text-slate-400 hover:bg-white/[0.06] hover:text-white`
  const active = `${btn} bg-clear-400/15 text-clear-300 ring-1 ring-clear-400/30`
  const arrow = 'inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-white/[0.06] hover:text-white disabled:cursor-not-allowed disabled:opacity-30'
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-5 py-3">
      <div className="flex items-center gap-3 text-xs text-slate-500">
        <span>Showing <span className="font-semibold text-slate-300">{rangeStart}–{rangeEnd}</span> of <span className="font-semibold text-slate-300">{total}</span></span>
        <label className="flex items-center gap-1.5">
          <span className="sr-only">Rows per page</span>
          <select className="select" value={perPage} onChange={(e) => setPerPage(Number(e.target.value))} aria-label="Rows per page">
            {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} / page</option>)}
          </select>
        </label>
      </div>
      <div className="flex items-center gap-1">
        <button className={arrow} onClick={() => setPage(page - 1)} disabled={page <= 1} aria-label="Previous page"><ChevronLeft size={16} /></button>
        {pageNumbers(page, pageCount).map((n, i) => n === '…'
          ? <span key={`e${i}`} className="px-1 text-xs text-slate-600">…</span>
          : <button key={n} className={n === page ? active : idle} onClick={() => setPage(n)} aria-current={n === page ? 'page' : undefined}>{n}</button>)}
        <button className={arrow} onClick={() => setPage(page + 1)} disabled={page >= pageCount} aria-label="Next page"><ChevronRight size={16} /></button>
      </div>
    </div>
  )
}
