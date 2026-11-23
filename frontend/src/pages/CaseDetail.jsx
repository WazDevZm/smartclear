import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertOctagon, AlertTriangle, ArrowLeft, Check, Clock, Eye, EyeOff, Fingerprint, Info, MessageSquare, Send,
  ShieldAlert, X,
} from 'lucide-react'
import { api, imageUrl } from '../api'
import { AiAssistant, RegistryCard, actionMeta } from '../components/Assist'
import { BandBadge, OutcomeIcon, Spinner, StatusBadge, outcomeText, pct } from '../components/ui'

const FIELD_LABELS = {
  nrc_number: 'NRC number', full_name: 'Full name', date_of_birth: 'Date of birth', card_number: 'Card no.', sex: 'Sex',
  place_of_birth_village: 'Place of birth', place_of_birth_district: 'Birth district', parent_place_of_birth: "Parent's place of birth",
  village: 'Village', district: 'District', chief: 'Chief', registration_date: 'Registration date', special_marks: 'Special marks',
}
const sevStyle = {
  high: ['border-rose-200 bg-rose-50', 'text-rose-700', AlertOctagon],
  medium: ['border-amber-200 bg-amber-50', 'text-amber-700', AlertTriangle],
  low: ['border-sky-200 bg-sky-50', 'text-sky-700', Info],
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

function Decision({ c, onDone, suggestion }) {
  const [note, setNote] = useState(c.decision_note || '')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  async function act(action) {
    setBusy(action); setErr('')
    try { onDone(await api(`/cases/${c.id}/review`, { method: 'POST', json: { action, note } })) }
    catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  // Counter-officer keyboard shortcuts: 1 approve · 2 reject · 3 escalate · 4 request info.
  // Ignored while typing in a field; reject/escalate still demand a note.
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return
      const map = { 1: 'approve', 2: 'reject', 3: 'escalate', 4: 'request_info' }
      if (map[e.key]) { e.preventDefault(); act(map[e.key]) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.id, note])
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="font-semibold text-slate-900">Your decision</div>
        <StatusBadge status={c.status} />
      </div>
      {c.decided_by && <div className="mt-1 text-xs text-slate-500">Last action by {c.decided_by}</div>}
      {suggestion && <div className="mt-3 rounded-xl bg-sky-50 px-3 py-2 text-xs text-slate-600">
        The assistant suggests: <b className="text-zra-navy">{actionMeta[suggestion]?.label}</b>. The choice is yours.</div>}
      <textarea className="input mt-4 h-20 resize-none" placeholder="Add a note (needed to reject or escalate)…" value={note} onChange={(e) => setNote(e.target.value)} />
      {err && <div className="mt-2 text-xs text-rose-700">{err}</div>}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button onClick={() => act('approve')} disabled={!!busy} data-suggested={suggestion === 'approve' || undefined} title="Approve (key 1)" className="btn data-[suggested]:ring-4 data-[suggested]:ring-sky-300 bg-emerald-600 text-white hover:bg-emerald-700">{busy === 'approve' ? <Spinner className="h-4 w-4" /> : <Check size={15} />}Approve <kbd className="ml-1 rounded bg-black/10 px-1.5 py-0.5 font-mono text-[10px]">1</kbd></button>
        <button onClick={() => act('reject')} disabled={!!busy} data-suggested={suggestion === 'reject' || undefined} title="Reject (key 2)" className="btn data-[suggested]:ring-4 data-[suggested]:ring-sky-300 bg-rose-600 text-white hover:bg-rose-700">{busy === 'reject' ? <Spinner className="h-4 w-4" /> : <X size={15} />}Reject <kbd className="ml-1 rounded bg-black/10 px-1.5 py-0.5 font-mono text-[10px]">2</kbd></button>
        <button onClick={() => act('escalate')} disabled={!!busy} data-suggested={suggestion === 'escalate' || undefined} title="Escalate (key 3)" className="btn data-[suggested]:ring-4 data-[suggested]:ring-sky-300 border border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100">{busy === 'escalate' ? <Spinner className="h-4 w-4" /> : <Send size={15} />}Escalate <kbd className="ml-1 rounded bg-black/10 px-1.5 py-0.5 font-mono text-[10px]">3</kbd></button>
        <button onClick={() => act('request_info')} disabled={!!busy} data-suggested={suggestion === 'request_info' || undefined} title="Request info (key 4)" className="btn data-[suggested]:ring-4 data-[suggested]:ring-sky-300 border border-slate-200 bg-slate-100 text-slate-800 hover:bg-slate-100">{busy === 'request_info' ? <Spinner className="h-4 w-4" /> : <MessageSquare size={15} />}Request info <kbd className="ml-1 rounded bg-black/10 px-1.5 py-0.5 font-mono text-[10px]">4</kbd></button>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">Keyboard: <span className="font-mono text-slate-600">1</span> approve · <span className="font-mono text-slate-600">2</span> reject · <span className="font-mono text-slate-600">3</span> escalate · <span className="font-mono text-slate-600">4</span> request info. Rejecting or escalating still requires a note. SmartClear recommends, the officer decides.</p>
    </div>
  )
}

export default function CaseDetail() {
  const { id } = useParams()
  const [c, setC] = useState(null)
  const [active, setActive] = useState(null)
  const [overlay, setOverlay] = useState(true)
  const [suggestion, setSuggestion] = useState(null)
  useEffect(() => { setC(null); setSuggestion(null); api(`/cases/${id}`).then((d) => { setC(d); setSuggestion(d.result.ai?.suggested_action || null) }) }, [id])
  if (!c) return <Spinner />
  const r = c.result
  const f = r.extraction.fields
  const ver = r.verification
  const hi = (k) => (active === k ? 'bg-slate-100' : '')
  return (
    <div>
      <Link to="/app/queue" className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900"><ArrowLeft size={15} /> Cases to review</Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-slate-900">{f.full_name.value || 'Unreadable name'}</h1>
            <BandBadge band={r.risk.band} score={r.risk.score} />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
            <span className="font-mono">{c.ref}</span><span>{c.filename}</span>
            {c.tpin && <span>TPIN <span className="font-mono text-slate-700">{c.tpin}</span></span>}
            <span className="flex items-center gap-1"><Clock size={13} /> {(r.timing_ms.total / 1000).toFixed(2)}s</span>
          </div>
        </div>
      </div>

      <div className={`mb-6 flex items-start gap-3 rounded-2xl border p-4 ${r.risk.band === 'high' ? sevStyle.high[0] : r.risk.band === 'review' ? sevStyle.medium[0] : 'border-emerald-200 bg-emerald-50'}`}>
        <ShieldAlert size={20} className={r.risk.band === 'high' ? 'text-rose-700' : r.risk.band === 'review' ? 'text-amber-700' : 'text-emerald-700'} />
        <div>
          <div className="font-semibold text-slate-900">{r.risk.recommendation}</div>
          <div className="mt-0.5 text-sm text-slate-600">{ver.summary} {r.flags.length ? `${r.flags.length} flag${r.flags.length > 1 ? 's' : ''} raised.` : 'Nothing unusual found.'}</div>
        </div>
      </div>

      <AiAssistant key={`${c.id}-${c.result.registry?.request_id}`} caseId={c.id} initial={c.result.ai} onLoaded={(a) => setSuggestion(a.suggested_action)} />

      <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <div className="space-y-6">
          <div className="card p-4">
            <div className="mb-3 flex items-center justify-between px-1">
              <div className="label">The card</div>
              <button onClick={() => setOverlay(!overlay)} className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900">
                {overlay ? <EyeOff size={14} /> : <Eye size={14} />} {overlay ? 'Hide' : 'Show'} highlights
              </button>
            </div>
            <DocViewer c={c} active={active} setActive={setActive} overlay={overlay} />
            <div className="mt-3 flex flex-wrap gap-4 px-1 text-[11px] text-slate-500">
              {[['#34d399', 'Matches the form'], ['#fbbf24', 'Please confirm'], ['#fb7185', 'Doesn’t match or may be changed'], ['#38bdf8', 'Read from card']].map(([col, l]) =>
                <span key={l} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: col }} />{l}</span>)}
            </div>
            {r.preprocessing && <div className="mt-2 px-1 text-[11px] text-slate-500">
              Pages: {r.preprocessing.pages?.map((page) =>
                `${page.index + 1} ${page.side}${page.rotation_degrees ? ` rotated ${page.rotation_degrees}°` : ''}`
              ).join(' · ') || r.preprocessing.page_count}
              {r.preprocessing.cropped_page_count > 0 && ` · ${r.preprocessing.cropped_page_count} card crop${r.preprocessing.cropped_page_count === 1 ? '' : 's'}`}
              {' · grayscale OCR'}
            </div>}
            {r.extraction.warnings?.length > 0 && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
              {r.extraction.warnings.map((warning) => <div key={warning}>{warning}</div>)}
            </div>}
          </div>

          <div className="card p-5">
            <div className="label mb-3">Everything read from the card</div>
            <div className="grid gap-x-6 sm:grid-cols-2">
              {Object.entries(FIELD_LABELS).map(([k, l]) => (
                <div key={k} onMouseEnter={() => setActive(k)} onMouseLeave={() => setActive(null)}
                  className={`flex items-center justify-between gap-3 rounded-lg px-2 py-2 transition ${hi(k)}`}>
                  <span className="text-xs text-slate-500">{l}</span>
                  <span className="flex flex-col items-end text-right">
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-800">{f[k]?.value || <span className="text-slate-400">—</span>}</span>
                      {f[k]?.value && <span className={`font-mono text-[10px] ${f[k].confidence < 0.8 ? 'text-amber-400' : 'text-slate-400'}`}>{Math.round(f[k].confidence * 100)}%</span>}
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
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5">
              <div className="font-semibold text-slate-900">Card vs. taxpayer’s form</div>
              <span className="flex items-center gap-1.5 text-xs text-slate-700"><OutcomeIcon outcome={ver.overall === 'review' ? 'partial' : ver.overall} size={14} />{outcomeText[ver.overall]}</span>
            </div>
            {ver.checks && Object.keys(ver.checks).length ? (
              <div className="divide-y divide-slate-100">
                {['nrc_number', 'full_name', 'date_of_birth'].map((k) => {
                  const ch = ver.checks[k]
                  return (
                    <div key={k} onMouseEnter={() => setActive(k)} onMouseLeave={() => setActive(null)} className={`px-5 py-3.5 transition ${hi(k)}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-600">{FIELD_LABELS[k]}</span>
                        <span className="flex items-center gap-1.5 text-xs"><OutcomeIcon outcome={ch.outcome} size={14} />{outcomeText[ch.outcome]}{ch.score !== undefined && k === 'full_name' && <span className="text-slate-500">· {ch.score}</span>}</span>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-3 font-mono text-xs">
                        <div><div className="mb-0.5 font-sans text-[10px] uppercase tracking-wider text-slate-400">On the card</div><div className="text-slate-800">{ch.extracted || '—'}</div></div>
                        <div><div className="mb-0.5 font-sans text-[10px] uppercase tracking-wider text-slate-400">On the form</div><div className="text-slate-800">{ch.record || '—'}</div></div>
                      </div>
                      {ch.outcome !== 'match' && <div className="mt-1.5 text-xs text-slate-500">{ch.detail}</div>}
                    </div>
                  )
                })}
              </div>
            ) : <div className="px-5 py-6 text-sm text-slate-500">{ver.summary}</div>}
          </div>

          <RegistryCard c={c} onUpdated={(d) => { setC(d); setSuggestion(null) }} />

          <div className="card p-5">
            <div className="mb-3 flex items-center justify-between"><div className="font-semibold text-slate-900">Things to check</div><span className="text-xs text-slate-500">{r.flags.length}</span></div>
            <div className="space-y-2.5">
              {r.flags.map((fl, i) => {
                const [box, txt, Icon] = sevStyle[fl.severity]
                return (
                  <div key={i} onMouseEnter={() => setActive(fl.field)} onMouseLeave={() => setActive(null)} className={`rounded-xl border p-3.5 ${box}`}>
                    <div className={`flex items-center gap-2 text-sm font-semibold ${txt}`}><Icon size={15} /> {fl.title}
                      <span className="ml-auto rounded-full bg-black/10 px-2 py-0.5 text-[10px] uppercase tracking-wider">{fl.severity}</span></div>
                    <p className="mt-1.5 text-xs leading-relaxed text-slate-700">{fl.message}</p>
                  </div>
                )
              })}
              {!r.flags.length && <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-700">Nothing unusual found on this card.</div>}
            </div>
          </div>

          <div className="card p-5">
            <div className="mb-4 flex items-center gap-2 font-semibold text-slate-900"><Fingerprint size={16} className="text-zra-sky" /> Signs the card was changed</div>
            <div className="space-y-4">
              {['nrc_number', 'full_name', 'date_of_birth'].map((k) => {
                const t = r.tamper[k]
                const p = t?.probability ?? 0
                const col = p >= 0.75 ? 'from-rose-500 to-rose-400' : p >= 0.5 ? 'from-amber-500 to-amber-300' : 'from-emerald-500 to-clear-400'
                return (
                  <div key={k} onMouseEnter={() => setActive(k)} onMouseLeave={() => setActive(null)}>
                    <div className="flex justify-between text-xs"><span className="text-slate-600">{FIELD_LABELS[k]}</span><span className="font-mono text-slate-700">{pct(t?.probability, 0)}</span></div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full bg-gradient-to-r ${col}`} style={{ width: `${Math.max(2, p * 100)}%` }} /></div>
                    {t?.reasons?.length > 0 && <div className="mt-1.5 text-[11px] text-slate-500">{t.reasons.join(' · ')}</div>}
                  </div>
                )
              })}
            </div>
          </div>

          <Decision c={c} onDone={setC} suggestion={suggestion} />

          <div className="card p-5">
            <div className="label mb-3">History</div>
            <div className="space-y-2.5">
              {c.audit.slice(0, 8).map((a, i) => (
                <div key={i} className="flex items-start gap-3 text-xs">
                  <div className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-clear-400" />
                  <div className="flex-1"><span className="text-slate-700">{a.action.replace('review:', '').replace(/_/g, ' ')}</span> <span className="text-slate-500">by {a.actor}</span></div>
                  <div className="font-mono text-slate-400">{new Date(a.ts).toLocaleString()}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
