import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertOctagon, AlertTriangle, ArrowLeft, Check, Clock, Eye, EyeOff, Fingerprint, Info, MessageSquare, Send,
  ShieldAlert, X,
} from 'lucide-react'
import { api, imageUrl } from '../api'
import { BandBadge, OutcomeIcon, Spinner, StatusBadge, outcomeText, pct } from '../components/ui'

const FIELD_LABELS = {
  nrc_number: 'NRC number', full_name: 'Full name', date_of_birth: 'Date of birth', card_number: 'Card no.', sex: 'Sex',
  place_of_birth_village: 'Place of birth', place_of_birth_district: 'Birth district', parent_place_of_birth: "Parent's place of birth",
  village: 'Village', district: 'District', chief: 'Chief', registration_date: 'Registration date', special_marks: 'Special marks',
}
const sevStyle = {
  high: ['border-rose-400/30 bg-rose-500/[0.07]', 'text-rose-300', AlertOctagon],
  medium: ['border-amber-400/30 bg-amber-400/[0.06]', 'text-amber-300', AlertTriangle],
  low: ['border-sky-400/20 bg-sky-400/[0.05]', 'text-sky-300', Info],
}

function DocViewer({ c, active, setActive, overlay }) {
  const r = c.result
  const [w, h] = r.image_size
  const fields = r.extraction.fields
  const flagged = new Set(r.flags.map((f) => f.field))
  const ver = r.verification.checks || {}
  const color = (k) => {
    const t = r.tamper[k]?.probability
    if ((t ?? 0) >= 0.5 || ver[k]?.outcome === 'mismatch' || (flagged.has(k) && k !== 'registration_date')) return '#fb7185'
    if (ver[k]?.outcome === 'partial') return '#fbbf24'
    if (ver[k]?.outcome === 'match') return '#34d399'
    return '#38bdf8'
  }
  const boxes = Object.entries(fields).filter(([, f]) => f.bbox)
  // erased key fields have no OCR box: show the forensic region instead
  for (const k of ['nrc_number', 'full_name', 'date_of_birth']) {
    if (!fields[k]?.bbox && r.forensic_boxes?.[k]) boxes.push([k, { bbox: r.forensic_boxes[k], missing: true }])
  }
  // crop the view to the cards (scans carry wide page margins)
  const xs = boxes.flatMap(([, f]) => [f.bbox[0], f.bbox[2]])
  const cx0 = Math.max(0, Math.min(...xs) - 45)
  const cx1 = Math.min(w, Math.max(...xs) + 45)
  return (
    <div className="overflow-hidden rounded-xl bg-[#e8e8e4]">
      <svg viewBox={`${cx0} 0 ${cx1 - cx0} ${h}`} className="block w-full">
        <image href={imageUrl(c.id)} x="0" y="0" width={w} height={h} />
        {overlay && boxes.map(([k, f]) => {
          const [x0, y0, x1, y1] = f.bbox
          const col = f.missing ? '#fb7185' : color(k)
          const on = active === k
          return (
            <rect key={k} onMouseEnter={() => setActive(k)} onMouseLeave={() => setActive(null)} className="cursor-pointer"
              x={x0 - 3} y={y0 - 2} width={x1 - x0 + 6} height={y1 - y0 + 4} rx="3"
              fill={col} fillOpacity={on ? 0.28 : 0.1} stroke={col} strokeWidth={on ? 2 : 1.1}
              strokeDasharray={f.missing ? '4 3' : undefined} />
          )
        })}
      </svg>
    </div>
  )
}

function Decision({ c, onDone }) {
  const [note, setNote] = useState(c.decision_note || '')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  async function act(action) {
    setBusy(action); setErr('')
    try { onDone(await api(`/cases/${c.id}/review`, { method: 'POST', json: { action, note } })) }
    catch (e) { setErr(e.message) } finally { setBusy('') }
  }
  const B = ({ a, cls, Icon, children }) => (
    <button onClick={() => act(a)} disabled={!!busy} className={`btn ${cls}`}>{busy === a ? <Spinner className="h-4 w-4" /> : <Icon size={15} />}{children}</button>
  )
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="font-semibold text-white">Officer decision</div>
        <StatusBadge status={c.status} />
      </div>
      {c.decided_by && <div className="mt-1 text-xs text-slate-500">Last action by {c.decided_by}</div>}
      <textarea className="input mt-4 h-20 resize-none" placeholder="Notes (required to reject or escalate)…" value={note} onChange={(e) => setNote(e.target.value)} />
      {err && <div className="mt-2 text-xs text-rose-300">{err}</div>}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <B a="approve" cls="bg-emerald-500/90 text-ink-950 hover:bg-emerald-400" Icon={Check}>Approve</B>
        <B a="reject" cls="bg-rose-500/90 text-white hover:bg-rose-500" Icon={X}>Reject</B>
        <B a="escalate" cls="border border-violet-400/30 bg-violet-400/10 text-violet-200 hover:bg-violet-400/20" Icon={Send}>Escalate</B>
        <B a="request_info" cls="border border-white/10 bg-white/[0.04] text-slate-200 hover:bg-white/[0.08]" Icon={MessageSquare}>Request info</B>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">SmartClear recommends, the officer decides. Records are never changed automatically.</p>
    </div>
  )
}

export default function CaseDetail() {
  const { id } = useParams()
  const [c, setC] = useState(null)
  const [active, setActive] = useState(null)
  const [overlay, setOverlay] = useState(true)
  useEffect(() => { api(`/cases/${id}`).then(setC) }, [id])
  if (!c) return <Spinner />
  const r = c.result
  const f = r.extraction.fields
  const ver = r.verification
  const hi = (k) => (active === k ? 'bg-white/[0.06]' : '')
  return (
    <div>
      <Link to="/app/queue" className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"><ArrowLeft size={15} /> Review queue</Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-white">{f.full_name.value || 'Unreadable name'}</h1>
            <BandBadge band={r.risk.band} score={r.risk.score} />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-400">
            <span className="font-mono">{c.ref}</span><span>{c.filename}</span>
            {c.tpin && <span>TPIN <span className="font-mono text-slate-300">{c.tpin}</span></span>}
            <span className="flex items-center gap-1"><Clock size={13} /> {(r.timing_ms.total / 1000).toFixed(2)}s</span>
          </div>
        </div>
      </div>

      <div className={`mb-6 flex items-start gap-3 rounded-2xl border p-4 ${r.risk.band === 'high' ? sevStyle.high[0] : r.risk.band === 'review' ? sevStyle.medium[0] : 'border-emerald-400/25 bg-emerald-400/[0.06]'}`}>
        <ShieldAlert size={20} className={r.risk.band === 'high' ? 'text-rose-300' : r.risk.band === 'review' ? 'text-amber-300' : 'text-emerald-300'} />
        <div>
          <div className="font-semibold text-white">{r.risk.recommendation}</div>
          <div className="mt-0.5 text-sm text-slate-400">{ver.summary} {r.flags.length ? `${r.flags.length} flag${r.flags.length > 1 ? 's' : ''} raised.` : 'No anomalies detected.'}</div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <div className="space-y-6">
          <div className="card p-4">
            <div className="mb-3 flex items-center justify-between px-1">
              <div className="label">{r.preprocessing?.card_cropped ? 'Cropped card preview' : 'Grayscale document preview'}</div>
              <button onClick={() => setOverlay(!overlay)} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white">
                {overlay ? <EyeOff size={14} /> : <Eye size={14} />} {overlay ? 'Hide' : 'Show'} evidence
              </button>
            </div>
            <DocViewer c={c} active={active} setActive={setActive} overlay={overlay} />
            <div className="mt-3 flex flex-wrap gap-4 px-1 text-[11px] text-slate-500">
              {[['#34d399', 'Matches record'], ['#fbbf24', 'Needs confirmation'], ['#fb7185', 'Mismatch / suspected alteration'], ['#38bdf8', 'Extracted']].map(([col, l]) =>
                <span key={l} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: col }} />{l}</span>)}
            </div>
            {r.preprocessing && <div className="mt-2 px-1 text-[11px] text-slate-500">
              Pages: {r.preprocessing.pages?.map((page) =>
                `${page.index + 1} ${page.side}${page.rotation_degrees ? ` rotated ${page.rotation_degrees}°` : ''}`
              ).join(' · ') || r.preprocessing.page_count}
              {r.preprocessing.cropped_page_count > 0 && ` · ${r.preprocessing.cropped_page_count} card crop${r.preprocessing.cropped_page_count === 1 ? '' : 's'}`}
              {' · grayscale OCR'}
            </div>}
            {r.extraction.warnings?.length > 0 && <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/[0.05] p-3 text-xs text-amber-200">
              {r.extraction.warnings.map((warning) => <div key={warning}>{warning}</div>)}
            </div>}
          </div>

          <div className="card p-5">
            <div className="label mb-3">All extracted fields</div>
            <div className="grid gap-x-6 sm:grid-cols-2">
              {Object.entries(FIELD_LABELS).map(([k, l]) => (
                <div key={k} onMouseEnter={() => setActive(k)} onMouseLeave={() => setActive(null)}
                  className={`flex items-center justify-between gap-3 rounded-lg px-2 py-2 transition ${hi(k)}`}>
                  <span className="text-xs text-slate-500">{l}</span>
                  <span className="flex flex-col items-end text-right">
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-200">{f[k]?.value || <span className="text-slate-600">—</span>}</span>
                      {f[k]?.value && <span className={`font-mono text-[10px] ${f[k].confidence < 0.8 ? 'text-amber-400' : 'text-slate-600'}`}>{Math.round(f[k].confidence * 100)}%</span>}
                    </span>
                    {f[k]?.corrected_from && <span className="font-mono text-[10px] text-sky-400"
                      title="Matched to the verified district list; check against the image">
                      read as {f[k].corrected_from} · {Math.round(f[k].match_score)}% list match</span>}
                    {f[k]?.suggestion && <span className="font-mono text-[10px] text-amber-400"
                      title="Close to a district in the verified list, but not close enough to correct automatically">
                      possible: {f[k].suggestion} ({Math.round(f[k].match_score)}%)</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5">
              <div className="font-semibold text-white">Record verification</div>
              <span className="flex items-center gap-1.5 text-xs text-slate-300"><OutcomeIcon outcome={ver.overall === 'review' ? 'partial' : ver.overall} size={14} />{outcomeText[ver.overall]}</span>
            </div>
            {ver.checks && Object.keys(ver.checks).length ? (
              <div className="divide-y divide-white/[0.05]">
                {['nrc_number', 'full_name', 'date_of_birth'].map((k) => {
                  const ch = ver.checks[k]
                  return (
                    <div key={k} onMouseEnter={() => setActive(k)} onMouseLeave={() => setActive(null)} className={`px-5 py-3.5 transition ${hi(k)}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-400">{FIELD_LABELS[k]}</span>
                        <span className="flex items-center gap-1.5 text-xs"><OutcomeIcon outcome={ch.outcome} size={14} />{outcomeText[ch.outcome]}{ch.score !== undefined && k === 'full_name' && <span className="text-slate-500">· {ch.score}</span>}</span>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-3 font-mono text-xs">
                        <div><div className="mb-0.5 font-sans text-[10px] uppercase tracking-wider text-slate-600">On card</div><div className="text-slate-200">{ch.extracted || '—'}</div></div>
                        <div><div className="mb-0.5 font-sans text-[10px] uppercase tracking-wider text-slate-600">Captured record</div><div className="text-slate-200">{ch.record || '—'}</div></div>
                      </div>
                      {ch.outcome !== 'match' && <div className="mt-1.5 text-xs text-slate-500">{ch.detail}</div>}
                    </div>
                  )
                })}
              </div>
            ) : <div className="px-5 py-6 text-sm text-slate-500">{ver.summary}</div>}
          </div>

          <div className="card p-5">
            <div className="mb-3 flex items-center justify-between"><div className="font-semibold text-white">Flags</div><span className="text-xs text-slate-500">{r.flags.length}</span></div>
            <div className="space-y-2.5">
              {r.flags.map((fl, i) => {
                const [box, txt, Icon] = sevStyle[fl.severity]
                return (
                  <div key={i} onMouseEnter={() => setActive(fl.field)} onMouseLeave={() => setActive(null)} className={`rounded-xl border p-3.5 ${box}`}>
                    <div className={`flex items-center gap-2 text-sm font-semibold ${txt}`}><Icon size={15} /> {fl.title}
                      <span className="ml-auto rounded-full bg-black/20 px-2 py-0.5 text-[10px] uppercase tracking-wider">{fl.severity}</span></div>
                    <p className="mt-1.5 text-xs leading-relaxed text-slate-300">{fl.message}</p>
                  </div>
                )
              })}
              {!r.flags.length && <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/[0.05] p-3.5 text-sm text-emerald-200">No anomalies detected by rules or the tamper model.</div>}
            </div>
          </div>

          <div className="card p-5">
            <div className="mb-4 flex items-center gap-2 font-semibold text-white"><Fingerprint size={16} className="text-clear-400" /> Tamper analysis</div>
            <div className="space-y-4">
              {['nrc_number', 'full_name', 'date_of_birth'].map((k) => {
                const t = r.tamper[k]
                const p = t?.probability ?? 0
                const col = p >= 0.75 ? 'from-rose-500 to-rose-400' : p >= 0.5 ? 'from-amber-500 to-amber-300' : 'from-emerald-500 to-clear-400'
                return (
                  <div key={k} onMouseEnter={() => setActive(k)} onMouseLeave={() => setActive(null)}>
                    <div className="flex justify-between text-xs"><span className="text-slate-400">{FIELD_LABELS[k]}</span><span className="font-mono text-slate-300">{pct(t?.probability, 0)}</span></div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/5"><div className={`h-full rounded-full bg-gradient-to-r ${col}`} style={{ width: `${Math.max(2, p * 100)}%` }} /></div>
                    {t?.reasons?.length > 0 && <div className="mt-1.5 text-[11px] text-slate-500">{t.reasons.join(' · ')}</div>}
                  </div>
                )
              })}
            </div>
          </div>

          <Decision c={c} onDone={setC} />

          <div className="card p-5">
            <div className="label mb-3">Audit trail</div>
            <div className="space-y-2.5">
              {c.audit.slice(0, 8).map((a, i) => (
                <div key={i} className="flex items-start gap-3 text-xs">
                  <div className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-clear-400" />
                  <div className="flex-1"><span className="text-slate-300">{a.action.replace('review:', '').replace(/_/g, ' ')}</span> <span className="text-slate-500">by {a.actor}</span></div>
                  <div className="font-mono text-slate-600">{new Date(a.ts).toLocaleString()}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
