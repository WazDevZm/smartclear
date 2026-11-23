import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CheckCircle2, FileText, Files, Layers, Loader2, ScanLine, ShieldAlert, Trash2, XCircle,
} from 'lucide-react'
import { api, waitForJob } from '../api'
import { PageHeader } from '../components/ui'

const bandCls = {
  high: 'bg-rose-100 text-rose-700 ring-rose-200',
  review: 'bg-amber-100 text-amber-700 ring-amber-200',
  clear: 'bg-emerald-100 text-emerald-700 ring-emerald-200',
}

/** Batch verification: drop up to 50 scans; SmartClear processes each like a normal case. */
export default function Batch() {
  const [files, setFiles] = useState([])
  const [tpin, setTpin] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState(null)
  const [progress, setProgress] = useState(0)
  const [doneCount, setDoneCount] = useState(0)
  const [err, setErr] = useState('')
  const input = useRef()

  function addFiles(list) {
    const incoming = [...list].filter(f => /\.(pdf|jpe?g|png|tif?f)$/i.test(f.name) || f.type.startsWith('image/') || f.type === 'application/pdf')
    setFiles(prev => [...prev, ...incoming].slice(0, 50))
    setResults(null)
  }
  const totals = results ? {
    ok: results.filter(r => r.id).length,
    high: results.filter(r => r.risk_band === 'high').length,
    review: results.filter(r => r.risk_band === 'review').length,
  } : null

  async function submit() {
    if (!files.length || busy) return
    setBusy(true); setErr(''); setResults(null); setProgress(0); setDoneCount(0)
    // Queued on the server (one case per document) and polled for real per-document progress.
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    if (tpin) fd.append('tpin', tpin)
    fd.append('background', 'true')
    try {
      const job = await api('/batches', { method: 'POST', body: fd })
      const done = await waitForJob(job.id, (j) => { setProgress(Math.round((j.done / Math.max(1, j.total)) * 100)); setDoneCount(j.done) })
      setProgress(100)
      setResults(done.results)
      setFiles([])
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Check many IDs" subtitle="Add up to 50 NRC scans at once. Each one is checked and added to your review list." />

      {/* Drop zone */}
      <div onClick={() => input.current.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}
        className="card flex cursor-pointer flex-col items-center justify-center border-2 border-dashed border-slate-200 px-6 py-12 text-center transition hover:border-sky-200 hover:bg-sky-50">
        <input ref={input} type="file" multiple accept=".pdf,image/*" className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-50 to-sky-100 text-zra-navy ring-1 ring-slate-200">
          <Layers size={26} />
        </div>
        <div className="mt-4 font-semibold text-slate-900">Drag your scans here, or click to choose</div>
        <div className="mt-1 text-sm text-slate-500">PDF, JPG or PNG · up to 50 at a time</div>
      </div>

      {/* Selected files */}
      {files.length > 0 && !busy && !results && (
        <div className="card mt-5 p-4">
          <div className="flex items-center justify-between gap-3 px-1 pb-2">
            <div className="text-sm font-semibold text-slate-900">{files.length} document{files.length === 1 ? '' : 's'} ready</div>
            <button onClick={() => setFiles([])} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900"><Trash2 size={13} /> Clear all</button>
          </div>
          <div className="max-h-56 divide-y divide-slate-100 overflow-y-auto">
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-3 px-1 py-2 text-xs">
                <FileText size={15} className="shrink-0 text-slate-500" />
                <span className="min-w-0 flex-1 truncate text-slate-700">{f.name}</span>
                <span className="font-mono text-slate-400">{(f.size / 1024).toFixed(0)} KB</span>
                <button onClick={() => setFiles(files.filter((_, j) => j !== i))} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-900"><XCircle size={15} /></button>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3 border-t border-slate-200 pt-4">
            <input className="input flex-1" placeholder="TPIN applied to all documents (optional)" value={tpin} onChange={(e) => setTpin(e.target.value)} />
            <button className="btn-primary" onClick={submit}><ScanLine size={16} /> Check all</button>
          </div>
        </div>
      )}

      {/* Progress */}
      {busy && (
        <div className="card mt-5 p-6 text-center">
          <Loader2 size={28} className="mx-auto animate-spin text-zra-sky" />
          <div className="mt-3 font-semibold text-slate-900">Checked {doneCount} of {files.length} document{files.length === 1 ? '' : 's'}…</div>
          <div className="mx-auto mt-4 h-2 max-w-md overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-gradient-to-r from-zra-sky to-clear-400 transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-2 text-xs text-slate-500">Each card is read and checked, just like a single upload. Large scans can take a little while.</div>
        </div>
      )}
      {err && <div className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{err}</div>}

      {/* Results */}
      {results && (
        <div className="mt-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card p-5"><div className="flex items-center gap-2 text-xs text-slate-500"><CheckCircle2 size={13} className="text-emerald-400" />Processed</div><div className="mt-1 font-display text-2xl font-bold text-slate-900">{totals.ok}</div></div>
            <div className="card p-5"><div className="flex items-center gap-2 text-xs text-slate-500"><ShieldAlert size={13} className="text-rose-400" />Need attention</div><div className="mt-1 font-display text-2xl font-bold text-rose-700">{totals.high}</div></div>
            <div className="card p-5"><div className="flex items-center gap-2 text-xs text-slate-500"><Files size={13} className="text-amber-400" />Double-check</div><div className="mt-1 font-display text-2xl font-bold text-amber-700">{totals.review}</div></div>
          </div>
          <div className="card mt-4 overflow-hidden">
            <div className="border-b border-slate-200 px-5 py-3.5 text-sm font-semibold text-slate-900">Results</div>
            <div className="divide-y divide-slate-100">
              {results.map((r, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-3 text-xs">
                  {r.id
                    ? <Link to={`/app/cases/${r.id}`} className="flex min-w-0 flex-1 items-center gap-3 hover:opacity-80">
                        <span className="font-mono text-slate-500">{r.ref}</span>
                        <span className="min-w-0 flex-1 truncate text-slate-700">{r.full_name || 'Name unreadable'}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${bandCls[r.risk_band] || bandCls.review}`}>{r.risk_band}</span>
                        <span className="w-24 text-right font-mono text-[10px] uppercase text-slate-500">{r.verification === 'no_record' ? 'no record' : r.verification}</span>
                      </Link>
                    : <div className="flex min-w-0 flex-1 items-center gap-3"><XCircle size={15} className="shrink-0 text-rose-400" /><span className="truncate text-rose-700">{r.filename} — {r.error}</span></div>}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-4 text-center"><Link to="/app/queue" className="btn-primary">Go to cases to review <ScanLine size={16} /></Link></div>
        </div>
      )}
    </div>
  )
}
