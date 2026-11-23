import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, CircleHelp, ShieldAlert, ShieldCheck, ShieldQuestion, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

export const bandMeta = {
  clear: { label: 'Looks good', cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', dot: 'bg-emerald-400', Icon: ShieldCheck },
  review: { label: 'Double-check', cls: 'bg-amber-50 text-amber-700 ring-amber-200', dot: 'bg-amber-400', Icon: ShieldQuestion },
  high: { label: 'Needs attention', cls: 'bg-rose-50 text-rose-700 ring-rose-200', dot: 'bg-rose-400', Icon: ShieldAlert },
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
  pending: ['Waiting for review', 'bg-sky-50 text-sky-700 ring-sky-200'],
  approved: ['Approved', 'bg-emerald-50 text-emerald-700 ring-emerald-200'],
  rejected: ['Rejected', 'bg-rose-50 text-rose-700 ring-rose-200'],
  escalated: ['Escalated', 'bg-violet-50 text-violet-700 ring-violet-200'],
  info_requested: ['Info requested', 'bg-amber-50 text-amber-700 ring-amber-200'],
}
export function StatusBadge({ status }) {
  const [l, c] = statusMeta[status] || [status, 'bg-slate-100 text-slate-700 ring-slate-200']
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${c}`}>{l}</span>
}

export function OutcomeIcon({ outcome, size = 16 }) {
  if (outcome === 'match') return <CheckCircle2 size={size} className="text-emerald-400" />
  if (outcome === 'mismatch') return <XCircle size={size} className="text-rose-400" />
  if (outcome === 'partial') return <AlertTriangle size={size} className="text-amber-400" />
  return <CircleHelp size={size} className="text-slate-600" />
}

export const outcomeText = { match: 'Match', mismatch: 'Mismatch', partial: 'Partial', unreadable: 'Unreadable',
  no_record: 'No record', review: 'Needs review' }

export function Stat({ label, value, sub, accent = 'from-zra-sky to-clear-400', Icon, to }) {
  const body = (
    <>
      <div className={`absolute -right-8 -top-8 h-24 w-24 rounded-full bg-gradient-to-br ${accent} opacity-10 blur-2xl`} />
      <div className="flex items-center justify-between">
        <div className="label">{label}</div>
        {Icon && <Icon size={16} className="text-slate-500 transition group-hover:text-zra-navy" />}
      </div>
      <div className="mt-3 font-display text-3xl font-bold text-slate-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
      {to && <ChevronRight size={18} className="absolute bottom-4 right-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-zra-navy" />}
    </>
  )
  return to
    ? <Link to={to} className="card group relative block overflow-hidden p-5 transition hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-soft focus:outline-none focus-visible:ring-4 focus-visible:ring-sky-200">{body}</Link>
    : <div className="card relative overflow-hidden p-5">{body}</div>
}

export function Spinner({ className = '' }) {
  return <div className={`h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-clear-400 ${className}`} />
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1.5 text-base text-slate-600">{subtitle}</p>}
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
  const idle = `${btn} text-slate-600 hover:bg-slate-100 hover:text-slate-900`
  const active = `${btn} bg-sky-100 text-zra-navy ring-1 ring-sky-200`
  const arrow = 'inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-30'
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-3">
      <div className="flex items-center gap-3 text-xs text-slate-500">
        <span>Showing <span className="font-semibold text-slate-700">{rangeStart}–{rangeEnd}</span> of <span className="font-semibold text-slate-700">{total}</span></span>
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
          ? <span key={`e${i}`} className="px-1 text-xs text-slate-400">…</span>
          : <button key={n} className={n === page ? active : idle} onClick={() => setPage(n)} aria-current={n === page ? 'page' : undefined}>{n}</button>)}
        <button className={arrow} onClick={() => setPage(page + 1)} disabled={page >= pageCount} aria-label="Next page"><ChevronRight size={16} /></button>
      </div>
    </div>
  )
}
