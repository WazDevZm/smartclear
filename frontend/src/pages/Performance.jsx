import { useEffect, useState } from 'react'
import { api } from '../api'
import { PageHeader, Spinner, Stat, pct } from '../components/ui'

const Bar = ({ label, value, sub }) => (
  <div>
    <div className="flex justify-between text-xs"><span className="text-slate-700">{label}</span><span className="font-mono text-slate-600">{pct(value)}</span></div>
    <div className="mt-1.5 h-2 rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-zra-sky to-clear-400" style={{ width: `${value * 100}%` }} /></div>
    {sub && <div className="mt-1 text-[11px] text-slate-500">{sub}</div>}
  </div>
)

export default function Performance() {
  const [d, setD] = useState(null)
  useEffect(() => { api('/evaluation').then(setD) }, [])
  if (!d) return <Spinner />
  const e = d.evaluation, t = d.tamper_metrics, g = d.registry_evaluation
  if (!e) return <div className="text-slate-600">Run <code>scripts/evaluate.py</code> to generate the evaluation report.</div>
  const ff = e.fraud_flagging
  const conf = e.verification.confusion
  const outs = ['match', 'review', 'mismatch']
  return (
    <div>
      <PageHeader title="How accurate it is" subtitle={`Tested on ${e.dataset.documents} practice cards, ${e.dataset.fraudulent} of which were deliberately faked`} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Cards read correctly" value={pct(e.extraction.key_fields_accuracy)} sub="NRC no., name, DOB vs manual reading" />
        <Stat label="Correct match results" value={pct(e.verification.accuracy)} sub="vs expected record outcome" accent="from-sky-400 to-indigo-400" />
        <Stat label="Fake cards spotted" value={pct(ff.recall)} sub={`${ff.tp} of ${ff.tp + ff.fn} fraudulent NRCs flagged`} accent="from-rose-400 to-orange-400" />
        <Stat label="Warnings that were right" value={pct(ff.precision)} sub={`${ff.fp} false alarm${ff.fp === 1 ? '' : 's'}`} accent="from-emerald-400 to-teal-400" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <div className="font-semibold text-slate-900">1 · Extraction accuracy by field</div>
          <div className="mt-5 space-y-4">
            {Object.entries(e.extraction.per_field).map(([k, v]) => <Bar key={k} label={k.replace(/_/g, ' ')} value={v.accuracy} />)}
          </div>
          <div className="mt-6 rounded-xl bg-slate-50 p-4 text-xs text-slate-600">
            Robustness: <b className="text-slate-900">{pct(e.robustness.key_field_accuracy)}</b> key-field accuracy on {e.robustness.n_docs} perturbed scans ({e.robustness.perturbation}).
            Erased fields correctly reported unreadable: <b className="text-slate-900">{e.extraction.erased_fields_correctly_reported_unreadable.correct}/{e.extraction.erased_fields_correctly_reported_unreadable.total}</b>.
          </div>
        </div>
        <div className="space-y-6">
          <div className="card p-6">
            <div className="font-semibold text-slate-900">2 · Verification confusion matrix</div>
            <table className="mt-5 w-full text-center text-sm">
              <thead><tr><th className="label pb-2 text-left">Expected ↓ / Got →</th>{outs.map((o) => <th key={o} className="label pb-2">{o}</th>)}</tr></thead>
              <tbody>{outs.map((r) => (
                <tr key={r}><td className="py-1.5 text-left text-xs text-slate-600">{r}</td>
                  {outs.map((c) => { const n = conf[r]?.[c] || 0; return (
                    <td key={c} className="p-1"><div className={`rounded-lg py-2 font-mono ${n ? (r === c ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700') : 'bg-slate-50 text-slate-400'}`}>{n}</div></td>) })}
                </tr>))}</tbody>
            </table>
          </div>
          <div className="card p-6">
            <div className="font-semibold text-slate-900">3 · Fraud flagging by type</div>
            <div className="mt-5 space-y-4">
              {Object.entries(ff.by_fraud_type).map(([k, v]) => <Bar key={k} label={`${k.replace(/_/g, ' ')} (${v.caught}/${v.total})`} value={v.caught / v.total} />)}
            </div>
            {t && <div className="mt-6 rounded-xl bg-slate-50 p-4 text-xs leading-relaxed text-slate-600">
              Tamper model (random forest on {t.n_synthetic_samples_final.toLocaleString()} synthetic forgeries + real samples), 5-fold document-grouped CV on real held-out fields:
              ROC-AUC <b className="text-slate-900">{t.cv_synthetic_plus_real.roc_auc}</b>, recall <b className="text-slate-900">{pct(t.cv_synthetic_plus_real['recall@0.5'])}</b>, precision <b className="text-slate-900">{pct(t.cv_synthetic_plus_real['precision@0.5'])}</b>.
              Trained on synthetic forgeries only: recall <b className="text-slate-900">{pct(t.cv_synthetic_only['recall@0.5'])}</b>.
            </div>}
          </div>
        </div>
      </div>
      {g && <div className="card mt-6 p-6">
        <div className="font-semibold text-slate-900">4 · Check against the national register (Ministry of Home Affairs)</div>
        <p className="mt-1 text-sm text-slate-500">Each card’s details are sent to the sandbox national register. This measures that check on its own, before the other rules are added.</p>
        <div className="mt-5 grid gap-4 sm:grid-cols-4">
          {[['Fake cards caught', pct(g.recall), `${g.tp} of ${g.tp + g.fn}`], ['Warnings that were right', pct(g.precision), `${g.fp} false alarm${g.fp === 1 ? '' : 's'}`],
            ['Genuine cards cleared', pct(g.tn / Math.max(1, g.tn + g.fp)), `${g.tn} of ${g.tn + g.fp}`], ['Time per lookup', `${g.latency_ms.median} ms`, 'median']].map(([a, b, c]) => (
            <div key={a} className="rounded-xl bg-slate-50 p-4"><div className="font-display text-2xl font-bold text-slate-900">{b}</div><div className="mt-1 text-xs font-medium text-slate-700">{a}</div><div className="text-[11px] text-slate-500">{c}</div></div>))}
        </div>
        <div className="mt-5 grid gap-x-8 gap-y-4 sm:grid-cols-3">
          {Object.entries(g.by_fraud_type).map(([k, v]) => <Bar key={k} label={`${k.replace(/_/g, ' ')} (${v.caught}/${v.total})`} value={v.caught / v.total} />)}
        </div>
        <p className="mt-4 text-[11px] text-slate-500">{g.note}</p>
      </div>}
      {t && <div className="card mt-6 p-6">
        <div className="font-semibold text-slate-900">What the tamper model looks at</div>
        <div className="mt-5 grid gap-x-8 gap-y-3 sm:grid-cols-2">
          {t.feature_importance.map(([n, v]) => <Bar key={n} label={n.replace(/_/g, ' ')} value={v / t.feature_importance[0][1]} />)}
        </div>
      </div>}
    </div>
  )
}
