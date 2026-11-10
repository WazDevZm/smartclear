import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Lock } from 'lucide-react'
import { api, setSession } from '../api'
import { CoBrand } from '../components/Logo'
import { Spinner } from '../components/ui'

export default function Login() {
  const [username, setU] = useState('officer')
  const [password, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const s = await api('/login', { method: 'POST', json: { username, password } })
      setSession(s)
      navigate('/app')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      <div className="grid-bg pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute left-1/2 top-1/3 h-[480px] w-[720px] -translate-x-1/2 rounded-full bg-zra-navy/40 blur-[120px]" />
      <div className="relative w-full max-w-md animate-fadeup">
        <div className="mb-8 flex justify-center"><Link to="/"><CoBrand /></Link></div>
        <form onSubmit={submit} className="card space-y-5 p-8">
          <div>
            <h1 className="font-display text-2xl font-bold text-white">Officer sign in</h1>
            <p className="mt-1 text-sm text-slate-400">Access the SmartClear verification console.</p>
          </div>
          <div className="space-y-1.5"><label className="label">Username</label>
            <input className="input" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" /></div>
          <div className="space-y-1.5"><label className="label">Password</label>
            <input className="input" type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></div>
          {err && <div className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-300 ring-1 ring-rose-400/20">{err}</div>}
          <button className="btn-primary w-full py-3" disabled={busy}>{busy ? <Spinner /> : <>Sign in <ArrowRight size={16} /></>}</button>
          <div className="flex items-start gap-2 rounded-lg bg-white/[0.03] p-3 text-xs text-slate-400">
            <Lock size={14} className="mt-0.5 shrink-0 text-clear-400" />
            <span>Pilot demo accounts: <b className="text-slate-200">officer</b> or <b className="text-slate-200">supervisor</b>, password <b className="text-slate-200">smartclear</b>.
              Production would use ZRA single sign-on.</span>
          </div>
        </form>
      </div>
    </div>
  )
}
