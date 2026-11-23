import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, CheckCircle2, Landmark, ClipboardCheck, FileStack, Gauge, ShieldAlert, ShieldCheck,
  Sparkles, Timer, Upload, Zap,
} from 'lucide-react'
import { api, session } from '../api'
import { AreaChart, BarRow, DonutChart } from '../components/charts'
import { BandBadge, Stat, bandMeta } from '../components/ui'

const outcomeMeta = [
  ['match', 'All details match', '#34d399'],
  ['review', 'Needs a second look', '#fbbf24'],
  ['mismatch', 'Details don’t match', '#fb7185'],
  ['no_record', 'No form on file', '#64748b'],
]
const registryMeta = [
  ['match', 'Matches the register', '#10b981'],
  ['partial', 'Partly matches', '#f59e0b'],
  ['mismatch', 'Doesn’t match', '#f43f5e'],
  ['not_found', 'Not in the register', '#be123c'],
  ['status_alert', 'Lost / revoked / deceased', '#7c3aed'],
  ['unavailable', 'Register not reached', '#94a3b8'],
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
  if (!s) return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map(i => <div key={i} className="card h-28 animate-pulse bg-slate-50" />)}</div>

  const total = s.total || 1
  const oc = s.outcome_counts || {}
  const weekly = s.weekly || []
  const weekDocs = weekly.slice(-7).reduce((a, d) => a + d.count, 0)
  const maxFlag = Math.max(1, ...s.top_flags.map(([, n]) => n))
  const maxDecision = Math.max(1, ...decisionMeta.map(([k]) => s.status[k] || 0))
  const decided = decisionMeta.reduce((a, [k]) => a + (s.status[k] || 0), 0)
  const firstName = session()?.user?.name?.split(' ')[0] || 'there'
  const approvalRate = decided ? Math.round(((s.status.approved || 0) / decided) * 100) : 0

  return (
    <div>
      <div className="relative mb-6 overflow-hidden rounded-3xl bg-zra-navy text-white shadow-soft">
        <img src="/images/counter-help.jpg" alt="" className="absolute inset-y-0 right-0 hidden h-full w-1/2 object-cover md:block" />
        <div className="absolute inset-y-0 right-0 hidden w-1/2 bg-gradient-to-r from-zra-navy via-zra-navy/40 to-transparent md:block" />
        <div className="relative max-w-xl p-7 sm:p-9">
          <div className="text-sm font-medium text-white/70">Good day, {firstName} 👋</div>
          <h1 className="mt-2 font-display text-3xl font-bold leading-tight">
            {s.status.pending ? <>You have {s.status.pending} card{s.status.pending === 1 ? '' : 's'} waiting for review.</> : <>You’re all caught up.</>}
          </h1>
          <p className="mt-2 text-white/75">Check a new ID, or pick up where you left off.</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/app/verify" className="btn bg-white text-zra-navy hover:bg-slate-100"><Upload size={16} /> Check an ID</Link>
            <Link to="/app/queue" className="btn border border-white/30 text-white hover:bg-white/10"><ArrowRight size={16} /> Cases to review</Link>
            <Link to="/app/batch" className="btn border border-white/30 text-white hover:bg-white/10"><Zap size={16} /> Check many IDs</Link>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat to="/app/queue?status=" label="IDs checked" value={s.total} sub={`${weekDocs} in the last 7 days · ${s.taxpayers} taxpayer forms on file`} Icon={FileStack} />
        <Stat to="/app/queue?status=pending" label="Waiting for you" value={s.status.pending || 0} sub="most important first" Icon={Gauge} accent="from-sky-400 to-indigo-400" />
        <Stat to="/app/queue?band=high&status=" label="Need attention" value={s.bands.high || 0} sub={`${Math.round(((s.bands.high || 0) / total) * 100)}% of all documents`} Icon={ShieldAlert} accent="from-rose-400 to-orange-400" />
        <Stat to="/app/performance" label="Average check time" value={`${(s.avg_processing_ms / 1000).toFixed(1)}s`} sub="per ID card" Icon={Timer} accent="from-emerald-400 to-teal-400" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* Verification outcomes donut */}
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">Check results</div>
            <ClipboardCheck size={16} className="text-slate-400" />
          </div>
          <div className="mt-4 flex flex-col items-center gap-5">
            <DonutChart
              segments={outcomeMeta.map(([key, label, color]) => [key, label, color]).map(([key, label, color]) => ({ label, value: oc[key] || 0, color }))}
              centerTop={`${Math.round((((oc.match || 0)) / total) * 100)}%`}
              centerBottom="all match"
            />
            <ul className="w-full space-y-2.5">
              {outcomeMeta.map(([key, label, color]) => (
                <li key={key} className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-2 text-slate-600"><span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />{label}</span>
                  <span className="font-mono text-xs text-slate-700">{oc[key] || 0} <span className="text-slate-400">· {Math.round(((oc[key] || 0) / total) * 100)}%</span></span>
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
            <Sparkles size={13} className="shrink-0 text-zra-navy" /> Includes every card checked so far, including sample data.
          </div>
        </div>

        {/* Risk distribution */}
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">How many need attention</div>
            <ShieldCheck size={16} className="text-slate-400" />
          </div>
          <div className="mt-5 space-y-4">
            {['high', 'review', 'clear'].map((b) => (
              <Link key={b} to={`/app/queue?band=${b}`} className="group block">
                <div className="flex items-baseline justify-between text-xs">
                  <span className="flex items-center gap-2 text-slate-700 group-hover:text-slate-900"><span className={`h-2.5 w-2.5 rounded-full ${bandMeta[b].dot}`} />{bandMeta[b].label}</span>
                  <span className="font-mono text-slate-600">{s.bands[b] || 0} <span className="text-slate-400">· {Math.round(((s.bands[b] || 0) / total) * 100)}%</span></span>
                </div>
                <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${bandMeta[b].dot} transition-all duration-700`} style={{ width: `${(((s.bands[b] || 0) / total) * 100)}%` }} />
                </div>
              </Link>
            ))}
          </div>
          <div className="mt-5 border-t border-slate-200 pt-4">
            <div className="label">Decisions made by officers</div>
            <div className="mt-3 space-y-2.5">
              {decisionMeta.map(([k, label, color]) => (
                <BarRow key={k} label={label} value={s.status[k] || 0} max={maxDecision} color={color} />
              ))}
            </div>
            {decided > 0 && <div className="mt-3 text-right text-[11px] text-slate-500">Approval rate <b className="text-slate-700">{approvalRate}%</b></div>}
          </div>
        </div>

        {/* 14-day throughput */}
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">IDs checked · last 14 days</div>
            <span className="rounded-full bg-sky-50 px-2 py-0.5 font-mono text-[10px] font-bold text-zra-navy">{weekDocs} this week</span>
          </div>
          <div className="mt-4"><AreaChart data={weekly.map(d => ({ ...d, label: d.day }))} /></div>
          <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-200 pt-4 text-center">
            <div><div className="font-display text-xl font-bold text-slate-900">{(weekDocs / 7).toFixed(1)}</div><div className="text-[11px] text-slate-500">cards per day</div></div>
            <div><div className="font-display text-xl font-bold text-slate-900">{Math.round(total * ((s.avg_processing_ms || 0) / 1000) / 60)}</div><div className="text-[11px] text-slate-500">minutes of checking in total</div></div>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        {/* Priority queue */}
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
            <div><div className="font-semibold text-slate-900">Next up for review</div><div className="text-xs text-slate-500">Most important first</div></div>
            <Link to="/app/queue" className="flex items-center gap-1 text-sm text-zra-navy hover:text-zra-sky">See all <ArrowRight size={14} /></Link>
          </div>
          <div className="divide-y divide-slate-100">
            {cases.map((c) => (
              <Link key={c.id} to={`/app/cases/${c.id}`} className="flex items-center gap-4 px-6 py-3.5 transition hover:bg-slate-50">
                <div className="w-20 font-mono text-xs text-slate-500">{c.ref}</div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-slate-900">{c.full_name || <span className="italic text-slate-500">Name unreadable</span>}</div>
                  <div className="font-mono text-xs text-slate-500">{c.nrc_number || 'NRC unreadable'}</div>
                </div>
                <div className="hidden text-xs text-slate-500 sm:block">{c.n_flags} warning{c.n_flags === 1 ? '' : 's'}</div>
                <BandBadge band={c.risk_band} score={c.risk_score} />
              </Link>
            ))}
            {!cases.length && <div className="flex items-center gap-2 px-6 py-10 text-sm text-slate-500"><CheckCircle2 size={16} className="text-emerald-400" /> All caught up. Nothing waiting.</div>}
          </div>
        </div>

        {/* Top flags */}
        <div className="space-y-6">
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">National register (MoHA) checks</div>
            <Landmark size={16} className="text-slate-400" />
          </div>
          <div className="mt-4 space-y-3">
            {registryMeta.map(([k, label, color]) => (
              <BarRow key={k} label={label} value={(s.registry_counts || {})[k] || 0} max={total} color={color} />
            ))}
          </div>
          <div className="mt-4 text-[11px] leading-relaxed text-slate-500">
            Every card is sent to the Ministry of Home Affairs register (sandbox) to confirm the person exists and the details are theirs.
          </div>
        </div>
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div className="label">Most common warnings</div>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-600" title="Total warnings raised">{s.flag_total ?? 0} total</span>
          </div>
          <div className="mt-4 space-y-3.5">
            {s.top_flags.map(([t, n]) => <BarRow key={t} label={t} value={n} max={maxFlag} color="linear-gradient(90deg,#1BA3E0,#2DD4BF)" right={n} />)}
            {!s.top_flags.length && <div className="py-6 text-center text-xs text-slate-400">No warnings yet.</div>}
          </div>
          <div className="mt-5 border-t border-slate-200 pt-4 text-[11px] leading-relaxed text-slate-500">
            Warnings are just hints. An officer always makes the final decision, and SmartClear never changes a record on its own.
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}
