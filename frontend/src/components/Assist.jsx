import { useEffect, useState } from 'react'
import {
  AlertTriangle, BadgeCheck, Building2, CircleHelp, Landmark, MessageCircleQuestion, RefreshCw, Sparkles, UserCheck,
  XCircle,
} from 'lucide-react'
import { api } from '../api'

export const actionMeta = {
  approve: { label: 'Approve', cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  request_info: { label: 'Ask for more information', cls: 'bg-amber-50 text-amber-700 ring-amber-200' },
  escalate: { label: 'Escalate to a supervisor', cls: 'bg-violet-50 text-violet-700 ring-violet-200' },
  reject: { label: 'Reject', cls: 'bg-rose-50 text-rose-700 ring-rose-200' },
}

/** AI assistant: plain-language explanation + suggested next step. The officer still decides. */
export function AiAssistant({ caseId, initial, onLoaded }) {
  const [ai, setAi] = useState(initial || null)
  const [busy, setBusy] = useState(!initial)
  const [err, setErr] = useState('')

  async function load(refresh = false) {
    setBusy(true); setErr('')
    try {
      const res = await api(`/cases/${caseId}/explain${refresh ? '?refresh=true' : ''}`, { method: 'POST' })
      setAi(res); onLoaded?.(res)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  useEffect(() => { if (!initial) load() }, [caseId]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="card mb-6 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-sky-50 to-white px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-zra-navy text-white"><Sparkles size={17} /></span>
          <div>
            <div className="font-semibold text-slate-900">SmartClear assistant</div>
            <div className="text-xs text-slate-500">Explains the results and suggests a next step. You make the decision.</div>
          </div>
        </div>
        {ai && !busy && (
          <button onClick={() => load(true)} className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900">
            <RefreshCw size={13} /> Explain again
          </button>
        )}
      </div>

      {busy ? (
        <div className="space-y-3 p-5">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-zra-sky" />
            Reading the results and writing an explanation… (can take up to a minute)
          </div>
          {[80, 95, 60].map((w) => <div key={w} className="h-3 animate-pulse rounded bg-slate-100" style={{ width: `${w}%` }} />)}
        </div>
      ) : err ? (
        <div className="flex items-center justify-between gap-3 p-5 text-sm text-rose-700">
          <span>Couldn’t get an explanation: {err}</span>
          <button onClick={() => load()} className="btn-ghost py-1.5 text-xs">Try again</button>
        </div>
      ) : ai && (
        <div className="grid gap-6 p-5 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <h3 className="font-display text-lg font-bold text-slate-900">{ai.headline}</h3>
            <p className="mt-2 leading-relaxed text-slate-600">{ai.explanation}</p>
            {ai.reasons?.length > 0 && (
              <ul className="mt-4 space-y-2.5">
                {ai.reasons.map((r, i) => (
                  <li key={i} className="flex gap-2.5 text-sm">
                    <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
                    <span><b className="font-semibold text-slate-800">{r.issue}.</b> <span className="text-slate-600">{r.meaning}</span></span>
                  </li>
                ))}
              </ul>
            )}
            {ai.questions_for_taxpayer?.length > 0 && (
              <div className="mt-5 rounded-xl bg-slate-50 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-500"><MessageCircleQuestion size={14} /> You could ask the taxpayer</div>
                <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                  {ai.questions_for_taxpayer.map((q) => <li key={q}>“{q}”</li>)}
                </ul>
              </div>
            )}
          </div>
          <div className="rounded-2xl border border-slate-200 p-4">
            <div className="text-xs font-semibold text-slate-500">Suggested next step</div>
            <div className={`mt-2 inline-flex rounded-full px-3 py-1.5 text-sm font-semibold ring-1 ${actionMeta[ai.suggested_action]?.cls}`}>
              {actionMeta[ai.suggested_action]?.label}
            </div>
            <ol className="mt-4 space-y-2 text-sm text-slate-700">
              {ai.next_steps.map((s, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zra-navy/10 text-[11px] font-bold text-zra-navy">{i + 1}</span>{s}
                </li>
              ))}
            </ol>
            <div className="mt-4 flex items-start gap-2 rounded-xl bg-sky-50 p-3 text-xs text-slate-600">
              <UserCheck size={15} className="mt-0.5 shrink-0 text-zra-navy" />
              <span>This is a suggestion. You make and record the final decision below.</span>
            </div>
            <div className="mt-3 text-[11px] leading-relaxed text-slate-400">
              {ai.source === 'ai' ? <>Written by AI ({ai.model}) · confidence {ai.confidence}</> : <>Written by SmartClear’s built-in rules (AI service unavailable)</>}
              {ai.source === 'ai' && !ai.agrees_with_rules && <> · the built-in rules would suggest “{actionMeta[ai.rule_based_action]?.label}”</>}
              <br />{ai.data_shared}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const regOutcome = {
  match: ['Matches the national register', 'text-emerald-700', BadgeCheck],
  partial: ['Partly matches the register', 'text-amber-700', AlertTriangle],
  mismatch: ['Doesn’t match the register', 'text-rose-700', XCircle],
  not_found: ['Not found in the register', 'text-rose-700', XCircle],
  status_alert: ['Card status alert', 'text-rose-700', AlertTriangle],
  unavailable: ['Register not reached', 'text-slate-600', CircleHelp],
}
const LABELS = { nrc_number: 'NRC number', full_name: 'Full name', date_of_birth: 'Date of birth', sex: 'Sex', card_number: 'Card number', district: 'District' }
const chk = { match: 'text-emerald-600', mismatch: 'text-rose-600', partial: 'text-amber-600', not_supplied: 'text-slate-400' }

/** Result of sending the extracted data to the Ministry of Home Affairs ground-truth registry. */
export function RegistryCard({ c, onUpdated }) {
  const reg = c.result.registry
  const [busy, setBusy] = useState(false)
  async function recheck() {
    setBusy(true)
    try { onUpdated(await api(`/cases/${c.id}/registry-check`, { method: 'POST' })) } finally { setBusy(false) }
  }
  const [label, color, Icon] = regOutcome[reg?.outcome] || ['Not checked yet', 'text-slate-600', CircleHelp]
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5">
        <div className="flex items-center gap-2 font-semibold text-slate-900"><Landmark size={16} className="text-zra-navy" /> National register (MoHA)</div>
        <button onClick={recheck} disabled={busy} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 disabled:opacity-50">
          <RefreshCw size={13} className={busy ? 'animate-spin' : ''} /> Check again
        </button>
      </div>
      <div className="px-5 py-4">
        <div className={`flex items-center gap-2 text-sm font-semibold ${color}`}><Icon size={16} /> {label}</div>
        {reg?.message && <p className="mt-1 text-xs text-slate-500">{reg.message}</p>}
        {reg?.status && reg.status !== 'active' && <p className="mt-2 rounded-lg bg-rose-50 p-2.5 text-xs text-rose-700">{reg.status_message} {reg.status_note}</p>}
        {reg?.checks && Object.keys(reg.checks).length > 0 && (
          <table className="mt-3 w-full text-xs">
            <thead><tr className="text-left text-[10px] uppercase tracking-wider text-slate-400"><th className="pb-1.5 font-semibold">Field</th><th className="pb-1.5 font-semibold">On the card</th><th className="pb-1.5 font-semibold">In the register</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(reg.checks).map(([k, v]) => (
                <tr key={k}>
                  <td className={`py-1.5 pr-2 font-medium ${chk[v.outcome] || 'text-slate-600'}`}>{LABELS[k] || k}</td>
                  <td className="py-1.5 pr-2 font-mono text-slate-700">{v.submitted || '—'}</td>
                  <td className="py-1.5 font-mono text-slate-700">{v.registry || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-400">
          <Building2 size={12} /> {reg?.request_id || '—'} · {reg?.transport} · {reg?.latency_ms} ms · sandbox register, synthetic data
        </div>
      </div>
    </div>
  )
}
