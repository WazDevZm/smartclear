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
    <div className="grid min-h-screen bg-cream lg:grid-cols-2">
      <div className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md animate-fadeup">
          <div className="mb-10"><Link to="/"><CoBrand /></Link></div>
          <form onSubmit={submit} className="space-y-5">
            <div>
              <h1 className="font-display text-3xl font-bold text-slate-900">Welcome back</h1>
              <p className="mt-2 text-slate-600">Sign in to check IDs and review cases.</p>
            </div>
            <div className="space-y-1.5"><label className="label">Username</label>
              <input className="input py-3" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" /></div>
            <div className="space-y-1.5"><label className="label">Password</label>
              <input className="input py-3" type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></div>
            {err && <div className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{err}</div>}
            <button className="btn-primary w-full py-3.5 text-base" disabled={busy}>{busy ? <Spinner /> : <>Sign in <ArrowRight size={18} /></>}</button>
            <div className="flex items-start gap-2 rounded-xl bg-white p-3.5 text-sm text-slate-600 ring-1 ring-slate-200">
              <Lock size={16} className="mt-0.5 shrink-0 text-zra-sky" />
              <span>Demo accounts: <b className="text-slate-900">officer</b> or <b className="text-slate-900">supervisor</b>, password <b className="text-slate-900">futureminds</b>.</span>
            </div>
            <Link to="/" className="block text-center text-sm text-slate-500 hover:text-zra-navy">← Back to home</Link>
          </form>
        </div>
      </div>
      <div className="relative hidden p-4 lg:block">
        <img src="/images/colleagues-laptop.jpg" alt="Two colleagues working together at a laptop" className="h-full w-full rounded-[2rem] object-cover" />
        <div className="absolute inset-x-12 bottom-12 rounded-2xl bg-white/90 p-6 shadow-soft backdrop-blur">
          <div className="font-display text-xl font-bold text-slate-900">Helping you help taxpayers.</div>
          <p className="mt-1 text-sm text-slate-600">SmartClear reads the card and points out anything unusual. You make the call.</p>
        </div>
      </div>
    </div>
  )
}
