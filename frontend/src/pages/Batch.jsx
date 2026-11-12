import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CheckCircle2, FileText, Files, Layers, Loader2, ScanLine, ShieldAlert, Trash2, XCircle,
} from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/ui'

const bandCls = {
  high: 'bg-rose-500/15 text-rose-300 ring-rose-400/30',
  review: 'bg-amber-400/15 text-amber-300 ring-amber-400/30',
  clear: 'bg-emerald-400/15 text-emerald-300 ring-emerald-400/30',
}

/** Batch verification: drop up to 50 scans; SmartClear processes each like a normal case. */
export default function Batch() {
  const [files, setFiles] = useState([])
  const [tpin, setTpin] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState(null)
  const [progress, setProgress] = useState(0)
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
    setBusy(true); setErr(''); setResults(null); setProgress(0)
    // Chunk the upload so officers see progress; backend creates one case per document.
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    if (tpin) fd.append('tpin', tpin)
    setProgress(30)
    try {
      const res = await api('/batches', { method: 'POST', body: fd })
      setProgress(100)
      setResults(res.results)
      setFiles([])
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Batch verification" subtitle="Drop up to 50 scanned NRCs — each becomes a fully verified case in the queue" />

      {/* Drop zone */}
      <div onClick={() => input.current.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}
        className="card flex cursor-pointer flex-col items-center justify-center border-2 border-dashed border-white/10 px-6 py-12 text-center transition hover:border-clear-400/40 hover:bg-clear-400/[0.03]">
        <input ref={input} type="file" multiple accept=".pdf,image/*" className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-zra-sky/20 to-clear-400/20 text-clear-300 ring-1 ring-white/10">
          <Layers size={26} />
        </div>
        <div className="mt-4 font-semibold text-white">Drop a stack of scans here</div>
        <div className="mt-1 text-sm text-slate-500">PDF, JPG or PNG · up to 50 documents · one case each, risk-sorted into the queue</div>
      </div>

      {/* Selected files */}
      {files.length > 0 && !busy && !results && (
        <div className="card mt-5 p-4">
          <div className="flex items-center justify-between gap-3 px-1 pb-2">
            <div className="text-sm font-semibold text-white">{files.length} document{files.length === 1 ? '' : 's'} ready</div>
            <button onClick={() => setFiles([])} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-white"><Trash2 size={13} /> Clear all</button>
          </div>
          <div className="max-h-56 divide-y divide-white/[0.05] overflow-y-auto">
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-3 px-1 py-2 text-xs">
                <FileText size={15} className="shrink-0 text-slate-500" />
                <span className="min-w-0 flex-1 truncate text-slate-300">{f.name}</span>
                <span className="font-mono text-slate-600">{(f.size / 1024).toFixed(0)} KB</span>
                <button onClick={() => setFiles(files.filter((_, j) => j !== i))} className="rounded p-1 text-slate-600 hover:bg-white/5 hover:text-white"><XCircle size={15} /></button>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3 border-t border-white/[0.06] pt-4">
            <input className="input flex-1" placeholder="TPIN applied to all documents (optional)" value={tpin} onChange={(e) => setTpin(e.target.value)} />
            <button className="btn-primary" onClick={submit}><ScanLine size={16} /> Verify batch</button>
          </div>
        </div>
      )}

      {/* Progress */}
      {busy && (
        <div className="card mt-5 p-6 text-center">
          <Loader2 size={28} className="mx-auto animate-spin text-clear-400" />
          <div className="mt-3 font-semibold text-white">Verifying {files.length} document{files.length === 1 ? '' : 's'}…</div>
          <div className="mx-auto mt-4 h-2 max-w-md overflow-hidden rounded-full bg-white/5">
            <div className="h-full rounded-full bg-gradient-to-r from-zra-sky to-clear-400 transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-2 text-xs text-slate-500">Each document goes through extraction → verification → flags, exactly as a single upload. This can take a while on large scans.</div>
        </div>
      )}
      {err && <div className="mt-4 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300 ring-1 ring-rose-400/20">{err}</div>}

      {/* Results */}
      {results && (
        <div className="mt-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card p-5"><div className="flex items-center gap-2 text-xs text-slate-500"><CheckCircle2 size={13} className="text-emerald-400" />Processed</div><div className="mt-1 font-display text-2xl font-bold text-white">{totals.ok}</div></div>
            <div className="card p-5"><div className="flex items-center gap-2 text-xs text-slate-500"><ShieldAlert size={13} className="text-rose-400" />High risk</div><div className="mt-1 font-display text-2xl font-bold text-rose-300">{totals.high}</div></div>
            <div className="card p-5"><div className="flex items-center gap-2 text-xs text-slate-500"><Files size={13} className="text-amber-400" />Need review</div><div className="mt-1 font-display text-2xl font-bold text-amber-300">{totals.review}</div></div>
          </div>
          <div className="card mt-4 overflow-hidden">
            <div className="border-b border-white/[0.06] px-5 py-3.5 text-sm font-semibold text-white">Batch results</div>
            <div className="divide-y divide-white/[0.05]">
              {results.map((r, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-3 text-xs">
                  {r.id
                    ? <Link to={`/app/cases/${r.id}`} className="flex min-w-0 flex-1 items-center gap-3 hover:opacity-80">
                        <span className="font-mono text-slate-500">{r.ref}</span>
                        <span className="min-w-0 flex-1 truncate text-slate-300">{r.full_name || 'Name unreadable'}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${bandCls[r.risk_band] || bandCls.review}`}>{r.risk_band}</span>
                        <span className="w-24 text-right font-mono text-[10px] uppercase text-slate-500">{r.verification === 'no_record' ? 'no record' : r.verification}</span>
                      </Link>
                    : <div className="flex min-w-0 flex-1 items-center gap-3"><XCircle size={15} className="shrink-0 text-rose-400" /><span className="truncate text-rose-300">{r.filename} — {r.error}</span></div>}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-4 text-center"><Link to="/app/queue" className="btn-primary">Open in review queue <ScanLine size={16} /></Link></div>
        </div>
      )}
    </div>
  )
}
