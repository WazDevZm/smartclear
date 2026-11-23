import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../api'
import { BandBadge, OutcomeIcon, PageHeader, Pagination, Spinner, StatusBadge, outcomeText, usePagination } from '../components/ui'

const Pill = ({ active, onClick, children }) => (
  <button onClick={onClick} className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${active ? 'bg-zra-navy text-white' : 'bg-slate-100 text-slate-600 hover:text-slate-900'}`}>{children}</button>
)

export default function Queue() {
  const [params, setParams] = useSearchParams()
  const band = params.get('band') || ''
  const status = params.get('status') ?? 'pending'
  const [q, setQ] = useState('')
  const [rows, setRows] = useState(null)
  useEffect(() => {
    const p = new URLSearchParams()
    if (band) p.set('band', band)
    if (status) p.set('status', status)
    if (q) p.set('q', q)
    const t = setTimeout(() => api(`/cases?${p}`).then(setRows), 200)
    return () => clearTimeout(t)
  }, [band, status, q])
  const set = (k, v) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.set(k, ''); setParams(n) }
  const pg = usePagination(rows)
  return (
    <div>
      <PageHeader title="Cases to review" subtitle="ID cards waiting for an officer, with the most important ones at the top" />
      <div className="card mb-5 flex flex-wrap items-center gap-3 p-3">
        <div className="relative min-w-[240px] flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input className="input pl-9" placeholder="Search by name, NRC number or TPIN…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {[['', 'All'], ['high', 'Needs attention'], ['review', 'Double-check'], ['clear', 'Looks good']].map(([v, l]) =>
            <Pill key={l} active={band === v} onClick={() => set('band', v)}>{l}</Pill>)}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {[['pending', 'Waiting'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['escalated', 'Escalated'], ['', 'Any']].map(([v, l]) =>
            <Pill key={l} active={status === v} onClick={() => set('status', v)}>{l}</Pill>)}
        </div>
      </div>
      {!rows ? <Spinner /> : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead><tr className="border-b border-slate-200 text-left">
              {['Case', 'Name on card', 'NRC number', 'Date of birth', 'Matches form?', 'Warnings', 'Attention', 'Status'].map((h) =>
                <th key={h} className="label px-5 py-3.5 font-semibold">{h}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {pg.slice.map((c) => (
                <tr key={c.id} className="group cursor-pointer transition hover:bg-slate-50" onClick={() => (window.location.href = `/app/cases/${c.id}`)}>
                  <td className="px-5 py-3.5"><Link to={`/app/cases/${c.id}`} className="font-mono text-xs text-zra-navy">{c.ref}</Link></td>
                  <td className="px-5 py-3.5 font-medium text-slate-900">{c.full_name || <span className="italic text-slate-500">unreadable</span>}</td>
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-700">{c.nrc_number || '—'}</td>
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-700">{c.date_of_birth || '—'}</td>
                  <td className="px-5 py-3.5"><span className="flex items-center gap-1.5 text-xs text-slate-700"><OutcomeIcon outcome={c.verification === 'review' ? 'partial' : c.verification} size={14} />{outcomeText[c.verification]}</span></td>
                  <td className="px-5 py-3.5 text-xs text-slate-600">{c.n_flags}</td>
                  <td className="px-5 py-3.5"><BandBadge band={c.risk_band} score={c.risk_score} /></td>
                  <td className="px-5 py-3.5"><StatusBadge status={c.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <div className="p-10 text-center text-sm text-slate-500">No cases match these filters.</div>}
          <Pagination {...pg} />
        </div>
      )}
    </div>
  )
}
