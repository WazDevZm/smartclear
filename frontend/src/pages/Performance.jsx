import { useEffect, useState } from 'react'
import { api } from '../api'
import { PageHeader, Spinner, Stat, pct } from '../components/ui'

const Bar = ({ label, value, sub }) => (
  <div>
    <div className="flex justify-between text-xs"><span className="text-slate-300">{label}</span><span className="font-mono text-slate-400">{pct(value)}</span></div>
    <div className="mt-1.5 h-2 rounded-full bg-white/5"><div className="h-full rounded-full bg-gradient-to-r from-zra-sky to-clear-400" style={{ width: `${value * 100}%` }} /></div>
    {sub && <div className="mt-1 text-[11px] text-slate-500">{sub}</div>}
  </div>
)

export default function Performance() {
  const [d, setD] = useState(null)
  useEffect(() => { api('/evaluation').then(setD) }, [])
  if (!d) return <Spinner />
  const e = d.evaluation, t = d.tamper_metrics
  if (!e) return <div className="text-slate-400">Run <code>scripts/evaluate.py</code> to generate the evaluation report.</div>
  const ff = e.fraud_flagging
  const conf = e.verification.confusion
  const outs = ['match', 'review', 'mismatch']
  return (
    <div>
      <PageHeader title="Model performance" subtitle={`Measured against the brief’s three success measures on ${e.dataset.documents} synthetic NRCs (${e.dataset.fraudulent} labelled fraudulent)`} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Extraction accuracy" value={pct(e.extraction.key_fields_accuracy)} sub="NRC no., name, DOB vs manual reading" />
        <Stat label="Verification accuracy" value={pct(e.verification.accuracy)} sub="vs expected record outcome" accent="from-sky-400 to-indigo-400" />
        <Stat label="Fraud recall" value={pct(ff.recall)} sub={`${ff.tp} of ${ff.tp + ff.fn} fraudulent NRCs flagged`} accent="from-rose-400 to-orange-400" />
        <Stat label="Flag precision" value={pct(ff.precision)} sub={`${ff.fp} false alarm${ff.fp === 1 ? '' : 's'}`} accent="from-emerald-400 to-teal-400" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <div className="font-semibold text-white">1 · Extraction accuracy by field</div>
          <div className="mt-5 space-y-4">
            {Object.entries(e.extraction.per_field).map(([k, v]) => <Bar key={k} label={k.replace(/_/g, ' ')} value={v.accuracy} />)}
          </div>
          <div className="mt-6 rounded-xl bg-white/[0.03] p-4 text-xs text-slate-400">
            Robustness: <b className="text-white">{pct(e.robustness.key_field_accuracy)}</b> key-field accuracy on {e.robustness.n_docs} perturbed scans ({e.robustness.perturbation}).
            Erased fields correctly reported unreadable: <b className="text-white">{e.extraction.erased_fields_correctly_reported_unreadable.correct}/{e.extraction.erased_fields_correctly_reported_unreadable.total}</b>.
          </div>
        </div>
        <div className="space-y-6">
          <div className="card p-6">
            <div className="font-semibold text-white">2 · Verification confusion matrix</div>
            <table className="mt-5 w-full text-center text-sm">
              <thead><tr><th className="label pb-2 text-left">Expected ↓ / Got →</th>{outs.map((o) => <th key={o} className="label pb-2">{o}</th>)}</tr></thead>
              <tbody>{outs.map((r) => (
                <tr key={r}><td className="py-1.5 text-left text-xs text-slate-400">{r}</td>
                  {outs.map((c) => { const n = conf[r]?.[c] || 0; return (
                    <td key={c} className="p-1"><div className={`rounded-lg py-2 font-mono ${n ? (r === c ? 'bg-emerald-400/15 text-emerald-200' : 'bg-rose-500/15 text-rose-200') : 'bg-white/[0.02] text-slate-600'}`}>{n}</div></td>) })}
                </tr>))}</tbody>
            </table>
          </div>
          <div className="card p-6">
            <div className="font-semibold text-white">3 · Fraud flagging by type</div>
            <div className="mt-5 space-y-4">
              {Object.entries(ff.by_fraud_type).map(([k, v]) => <Bar key={k} label={`${k.replace(/_/g, ' ')} (${v.caught}/${v.total})`} value={v.caught / v.total} />)}
            </div>
            {t && <div className="mt-6 rounded-xl bg-white/[0.03] p-4 text-xs leading-relaxed text-slate-400">
              Tamper model (random forest on {t.n_synthetic_samples_final.toLocaleString()} synthetic forgeries + real samples), 5-fold document-grouped CV on real held-out fields:
              ROC-AUC <b className="text-white">{t.cv_synthetic_plus_real.roc_auc}</b>, recall <b className="text-white">{pct(t.cv_synthetic_plus_real['recall@0.5'])}</b>, precision <b className="text-white">{pct(t.cv_synthetic_plus_real['precision@0.5'])}</b>.
              Trained on synthetic forgeries only: recall <b className="text-white">{pct(t.cv_synthetic_only['recall@0.5'])}</b>.
            </div>}
          </div>
        </div>
      </div>
      {t && <div className="card mt-6 p-6">
        <div className="font-semibold text-white">What the tamper model looks at</div>
        <div className="mt-5 grid gap-x-8 gap-y-3 sm:grid-cols-2">
          {t.feature_importance.map(([n, v]) => <Bar key={n} label={n.replace(/_/g, ' ')} value={v / t.feature_importance[0][1]} />)}
        </div>
      </div>}
    </div>
  )
}
