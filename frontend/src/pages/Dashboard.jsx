import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, FileStack, Gauge, ShieldAlert, ShieldCheck, Timer, Upload } from 'lucide-react'
import { api } from '../api'
import { BandBadge, PageHeader, Spinner, Stat, StatusBadge, bandMeta } from '../components/ui'

export default function Dashboard() {
  const [s, setS] = useState(null)
  const [cases, setCases] = useState([])
  useEffect(() => {
    api('/stats').then(setS)
    api('/cases?status=pending').then((c) => setCases(c.slice(0, 8)))
  }, [])
  if (!s) return <Spinner />
  const total = s.total || 1
  const maxFlag = Math.max(1, ...s.top_flags.map(([, n]) => n))
  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Registration verification at a glance">
        <Link to="/app/verify" className="btn-primary"><Upload size={16} /> Verify a document</Link>
      </PageHeader>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Documents processed" value={s.total} sub={`${s.taxpayers} captured records`} Icon={FileStack} />
        <Stat label="Awaiting review" value={s.status.pending || 0} sub="sorted by risk" Icon={Gauge} accent="from-sky-400 to-indigo-400" />
        <Stat label="High risk" value={s.bands.high || 0} sub={`${Math.round(((s.bands.high || 0) / total) * 100)}% of documents`} Icon={ShieldAlert} accent="from-rose-400 to-orange-400" />
        <Stat label="Avg. processing" value={`${(s.avg_processing_ms / 1000).toFixed(1)}s`} sub="per document, CPU" Icon={Timer} accent="from-emerald-400 to-teal-400" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_1.6fr]">
        <div className="card p-6">
          <div className="label">Risk distribution</div>
          <div className="mt-5 flex h-3 overflow-hidden rounded-full bg-white/5">
            {['clear', 'review', 'high'].map((b) => (
              <div key={b} className={bandMeta[b].dot} style={{ width: `${((s.bands[b] || 0) / total) * 100}%` }} />
            ))}
          </div>
          <div className="mt-5 space-y-3">
            {['clear', 'review', 'high'].map((b) => (
              <Link key={b} to={`/app/queue?band=${b}`} className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-white/[0.03]">
                <span className="flex items-center gap-2 text-sm text-slate-300"><span className={`h-2.5 w-2.5 rounded-full ${bandMeta[b].dot}`} />{bandMeta[b].label}</span>
                <span className="font-mono text-sm text-slate-400">{s.bands[b] || 0}</span>
              </Link>
            ))}
          </div>
          <div className="label mt-8">Most common flags</div>
          <div className="mt-4 space-y-3">
            {s.top_flags.map(([t, n]) => (
              <div key={t}>
                <div className="flex justify-between text-xs"><span className="text-slate-300">{t}</span><span className="font-mono text-slate-500">{n}</span></div>
                <div className="mt-1.5 h-1.5 rounded-full bg-white/5"><div className="h-full rounded-full bg-gradient-to-r from-zra-sky to-clear-400" style={{ width: `${(n / maxFlag) * 100}%` }} /></div>
              </div>
            ))}
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
            <div><div className="font-semibold text-white">Priority queue</div><div className="text-xs text-slate-500">Pending cases, highest risk first</div></div>
            <Link to="/app/queue" className="flex items-center gap-1 text-sm text-clear-300 hover:text-clear-400">View all <ArrowRight size={14} /></Link>
          </div>
          <div className="divide-y divide-white/[0.05]">
            {cases.map((c) => (
              <Link key={c.id} to={`/app/cases/${c.id}`} className="flex items-center gap-4 px-6 py-3.5 transition hover:bg-white/[0.03]">
                <div className="w-20 font-mono text-xs text-slate-500">{c.ref}</div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-white">{c.full_name || <span className="italic text-slate-500">Name unreadable</span>}</div>
                  <div className="font-mono text-xs text-slate-500">{c.nrc_number || 'NRC unreadable'}</div>
                </div>
                <div className="hidden text-xs text-slate-500 sm:block">{c.n_flags} flag{c.n_flags === 1 ? '' : 's'}</div>
                <BandBadge band={c.risk_band} score={c.risk_score} />
              </Link>
            ))}
            {!cases.length && <div className="flex items-center gap-2 px-6 py-10 text-sm text-slate-500"><ShieldCheck size={16} /> Queue is clear.</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
