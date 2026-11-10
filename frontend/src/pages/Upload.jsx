import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, FileUp, GitCompareArrows, ScanLine, ShieldAlert, Sparkles } from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/ui'

const stages = [
  [ScanLine, 'Reading document'], [Sparkles, 'Extracting fields with AI/OCR'],
  [GitCompareArrows, 'Verifying against captured record'], [ShieldAlert, 'Running anomaly & tamper checks'],
]

export default function Upload() {
  const [file, setFile] = useState(null)
  const [tpin, setTpin] = useState('')
  const [records, setRecords] = useState([])
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState(0)
  const [err, setErr] = useState('')
  const [drag, setDrag] = useState(false)
  const input = useRef()
  const navigate = useNavigate()
  useEffect(() => { api('/taxpayers').then(setRecords) }, [])
  useEffect(() => {
    if (!busy) return
    const t = setInterval(() => setStage((s) => Math.min(s + 1, stages.length - 1)), 650)
    return () => clearInterval(t)
  }, [busy])

  async function submit() {
    if (!file) return
    setBusy(true); setStage(0); setErr('')
    const fd = new FormData()
    fd.append('file', file)
    if (tpin) fd.append('tpin', tpin)
    try {
      const c = await api('/cases', { method: 'POST', body: fd })
      navigate(`/app/cases/${c.id}`)
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="New verification" subtitle="Upload the scanned NRC presented at registration" />
      <div className="card p-6 sm:p-8">
        <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); setFile(e.dataTransfer.files[0]) }}
          onClick={() => input.current.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition ${
            drag ? 'border-clear-400 bg-clear-400/5' : 'border-white/10 hover:border-white/20 hover:bg-white/[0.02]'}`}>
          <input ref={input} type="file" accept=".pdf,image/*" className="hidden" onChange={(e) => setFile(e.target.files[0])} />
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-zra-sky/20 to-clear-400/20 text-clear-300 ring-1 ring-white/10">
            {file ? <CheckCircle2 size={26} /> : <FileUp size={26} />}
          </div>
          <div className="mt-4 font-semibold text-white">{file ? file.name : 'Drop the scanned NRC here'}</div>
          <div className="mt-1 text-sm text-slate-500">{file ? `${(file.size / 1024).toFixed(0)} KB · click to change` : 'PDF, JPG or PNG, up to 15 MB'}</div>
        </div>

        <div className="mt-6 space-y-1.5">
          <label className="label">Captured taxpayer record (optional)</label>
          <select className="input" value={tpin} onChange={(e) => setTpin(e.target.value)}>
            <option value="">Auto-match by extracted NRC number</option>
            {records.map((r) => <option key={r.tpin} value={r.tpin}>{r.tpin} · {r.full_name} · {r.nrc_number}</option>)}
          </select>
          <p className="text-xs text-slate-500">The details the taxpayer captured in ZRA’s system. SmartClear compares the card against them.</p>
        </div>

        {err && <div className="mt-5 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300 ring-1 ring-rose-400/20">{err}</div>}

        {busy ? (
          <div className="mt-8 space-y-3">
            {stages.map(([Icon, label], i) => (
              <div key={label} className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm transition ${i <= stage ? 'bg-white/[0.04] text-white' : 'text-slate-600'}`}>
                {i < stage ? <CheckCircle2 size={17} className="text-emerald-400" /> :
                  i === stage ? <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-clear-400" /> : <Icon size={17} />}
                {label}
              </div>
            ))}
          </div>
        ) : (
          <button className="btn-primary mt-8 w-full py-3" disabled={!file} onClick={submit}><ScanLine size={17} /> Run SmartClear</button>
        )}
      </div>
    </div>
  )
}
