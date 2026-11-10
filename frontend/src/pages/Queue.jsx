import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../api'
import { BandBadge, OutcomeIcon, PageHeader, Spinner, StatusBadge, outcomeText } from '../components/ui'

const Pill = ({ active, onClick, children }) => (
  <button onClick={onClick} className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${active ? 'bg-white text-ink-950' : 'bg-white/[0.04] text-slate-400 hover:text-white'}`}>{children}</button>
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
  return (
    <div>
      <PageHeader title="Review queue" subtitle="Every submitted NRC, ordered so the riskiest cases come first" />
      <div className="card mb-5 flex flex-wrap items-center gap-3 p-3">
        <div className="relative min-w-[240px] flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input className="input pl-9" placeholder="Search name, NRC, TPIN or case ref…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {[['', 'All risk'], ['high', 'High risk'], ['review', 'Review'], ['clear', 'Clear']].map(([v, l]) =>
            <Pill key={l} active={band === v} onClick={() => set('band', v)}>{l}</Pill>)}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {[['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['escalated', 'Escalated'], ['', 'Any status']].map(([v, l]) =>
            <Pill key={l} active={status === v} onClick={() => set('status', v)}>{l}</Pill>)}
        </div>
      </div>
      {!rows ? <Spinner /> : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead><tr className="border-b border-white/[0.06] text-left">
              {['Case', 'Name on NRC', 'NRC number', 'Date of birth', 'Record check', 'Flags', 'Risk', 'Status'].map((h) =>
                <th key={h} className="label px-5 py-3.5 font-semibold">{h}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-white/[0.05]">
              {rows.map((c) => (
                <tr key={c.id} className="group cursor-pointer transition hover:bg-white/[0.03]" onClick={() => (window.location.href = `/app/cases/${c.id}`)}>
                  <td className="px-5 py-3.5"><Link to={`/app/cases/${c.id}`} className="font-mono text-xs text-clear-300">{c.ref}</Link></td>
                  <td className="px-5 py-3.5 font-medium text-white">{c.full_name || <span className="italic text-slate-500">unreadable</span>}</td>
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-300">{c.nrc_number || '—'}</td>
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-300">{c.date_of_birth || '—'}</td>
                  <td className="px-5 py-3.5"><span className="flex items-center gap-1.5 text-xs text-slate-300"><OutcomeIcon outcome={c.verification === 'review' ? 'partial' : c.verification} size={14} />{outcomeText[c.verification]}</span></td>
                  <td className="px-5 py-3.5 text-xs text-slate-400">{c.n_flags}</td>
                  <td className="px-5 py-3.5"><BandBadge band={c.risk_band} score={c.risk_score} /></td>
                  <td className="px-5 py-3.5"><StatusBadge status={c.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <div className="p-10 text-center text-sm text-slate-500">No cases match these filters.</div>}
        </div>
      )}
    </div>
  )
}
