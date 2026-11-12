import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, CheckCircle2, ClipboardCheck, FileStack, Gauge, ShieldAlert, ShieldCheck,
  Sparkles, Timer, Upload, Zap,
} from 'lucide-react'
import { api } from '../api'
import { AreaChart, BarRow, DonutChart } from '../components/charts'
import { BandBadge, PageHeader, Stat, bandMeta } from '../components/ui'

const outcomeMeta = [
  ['match', 'Matches', '#34d399'],
  ['review', 'Needs review', '#fbbf24'],
  ['mismatch', 'Mismatches', '#fb7185'],
  ['no_record', 'No record', '#64748b'],
]
const decisionMeta = [
  ['approved', 'Approved', '#34d399'],
  ['rejected', 'Rejected', '#fb7185'],
  ['escalated', 'Escalated', '#a78bfa'],
  ['info_requested', 'Info requested', '#fbbf24'],
]

export default function Dashboard() {
  const [s, setS] = useState(null)
  const [cases, setCases] = useState([])
  useEffect(() => {
    api('/stats').then(setS)
    api('/cases?status=pending').then((c) => setCases(c.slice(0, 8)))
  }, [])
  if (!s) return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map(i => <div key={i} className="card h-28 animate-pulse bg-white/[0.02]" />)}</div>

  const total = s.total || 1
  const oc = s.outcome_counts || {}
  const weekly = s.weekly || []
  const weekDocs = weekly.slice(-7).reduce((a, d) => a + d.count, 0)
  const maxFlag = Math.max(1, ...s.top_flags.map(([, n]) => n))
  const maxDecision = Math.max(1, ...decisionMeta.map(([k]) => s.status[k] || 0))
  const decided = decisionMeta.reduce((a, [k]) => a + (s.status[k] || 0), 0)
  const approvalRate = decided ? Math.round(((s.status.approved || 0) / decided) * 100) : 0

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Registration verification at a glance">
        <Link to="/app/batch" className="btn-ghost"><Zap size={16} /> Batch verify</Link>
        <Link to="/app/verify" className="btn-primary"><Upload size={16} /> Verify a document</Link>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Documents processed" value={s.total} sub={`${weekDocs} in the last 7 days · ${s.taxpayers} captured records`} Icon={FileStack} />
        <Stat label="Awaiting review" value={s.status.pending || 0} sub="sorted by risk — open the queue" Icon={Gauge} accent="from-sky-400 to-indigo-400" />
        <Stat label="High risk" value={s.bands.high || 0} sub={`${Math.round(((s.bands.high || 0) / total) * 100)}% of all documents`} Icon={ShieldAlert} accent="from-rose-400 to-orange-400" />
        <Stat label="Avg. processing" value={`${(s.avg_processing_ms / 1000).toFixed(1)}s`} sub="per document · re-verify on cached scan ~0.3s" Icon={Timer} accent="from-emerald-400 to-teal-400" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* Verification outcomes donut */}
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">Verification outcomes</div>
            <ClipboardCheck size={16} className="text-slate-600" />
          </div>
          <div className="mt-4 flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-6">
            <DonutChart
              segments={outcomeMeta.map(([key, label, color]) => [key, label, color]).map(([key, label, color]) => ({ label, value: oc[key] || 0, color }))}
              centerTop={`${Math.round((((oc.match || 0)) / total) * 100)}%`}
              centerBottom="match rate"
            />
            <ul className="flex-1 space-y-2.5">
              {outcomeMeta.map(([key, label, color]) => (
                <li key={key} className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-2 text-slate-400"><span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />{label}</span>
                  <span className="font-mono text-xs text-slate-300">{oc[key] || 0} <span className="text-slate-600">· {Math.round(((oc[key] || 0) / total) * 100)}%</span></span>
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-white/[0.03] px-3 py-2 text-[11px] leading-relaxed text-slate-500">
            <Sparkles size={13} className="shrink-0 text-clear-300" /> Counts every case ever processed, including historical seed data.
          </div>
        </div>

        {/* Risk distribution */}
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">Risk distribution</div>
            <ShieldCheck size={16} className="text-slate-600" />
          </div>
          <div className="mt-5 space-y-4">
            {['high', 'review', 'clear'].map((b) => (
              <Link key={b} to={`/app/queue?band=${b}`} className="group block">
                <div className="flex items-baseline justify-between text-xs">
                  <span className="flex items-center gap-2 text-slate-300 group-hover:text-white"><span className={`h-2.5 w-2.5 rounded-full ${bandMeta[b].dot}`} />{bandMeta[b].label}</span>
                  <span className="font-mono text-slate-400">{s.bands[b] || 0} <span className="text-slate-600">· {Math.round(((s.bands[b] || 0) / total) * 100)}%</span></span>
                </div>
                <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-white/[0.05]">
                  <div className={`h-full rounded-full ${bandMeta[b].dot} transition-all duration-700`} style={{ width: `${(((s.bands[b] || 0) / total) * 100)}%` }} />
                </div>
              </Link>
            ))}
          </div>
          <div className="mt-5 border-t border-white/[0.06] pt-4">
            <div className="label">Decisions made</div>
            <div className="mt-3 space-y-2.5">
              {decisionMeta.map(([k, label, color]) => (
                <BarRow key={k} label={label} value={s.status[k] || 0} max={maxDecision} color={color} />
              ))}
            </div>
            {decided > 0 && <div className="mt-3 text-right text-[11px] text-slate-500">Approval rate <b className="text-slate-300">{approvalRate}%</b></div>}
          </div>
        </div>

        {/* 14-day throughput */}
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">Volume · last 14 days</div>
            <span className="rounded-full bg-clear-400/10 px-2 py-0.5 font-mono text-[10px] font-bold text-clear-300">{weekDocs} this week</span>
          </div>
          <div className="mt-4"><AreaChart data={weekly.map(d => ({ ...d, label: d.day }))} /></div>
          <div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/[0.06] pt-4 text-center">
            <div><div className="font-display text-xl font-bold text-white">{(weekDocs / 7).toFixed(1)}</div><div className="text-[11px] text-slate-500">documents / day</div></div>
            <div><div className="font-display text-xl font-bold text-white">{Math.round(total * ((s.avg_processing_ms || 0) / 1000) / 60)}</div><div className="text-[11px] text-slate-500">machine-minutes spent on all verifications</div></div>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        {/* Priority queue */}
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
            {!cases.length && <div className="flex items-center gap-2 px-6 py-10 text-sm text-slate-500"><CheckCircle2 size={16} className="text-emerald-400" /> Queue is clear.</div>}
          </div>
        </div>

        {/* Top flags */}
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">Most common flags</div>
            <span className="rounded-full bg-white/[0.04] px-2 py-0.5 font-mono text-[10px] text-slate-400" title="Total flags ever raised">{s.flag_total ?? 0} total</span>
          </div>
          <div className="mt-4 space-y-3.5">
            {s.top_flags.map(([t, n]) => <BarRow key={t} label={t} value={n} max={maxFlag} color="linear-gradient(90deg,#1BA3E0,#2DD4BF)" right={n} />)}
            {!s.top_flags.length && <div className="py-6 text-center text-xs text-slate-600">No flags raised yet.</div>}
          </div>
          <div className="mt-5 border-t border-white/[0.06] pt-4 text-[11px] leading-relaxed text-slate-500">
            Flags are advisory. Every case ends with a human decision — SmartClear never changes a record on its own.
          </div>
        </div>
      </div>
    </div>
  )
}
