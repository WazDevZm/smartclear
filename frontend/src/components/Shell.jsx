import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Activity, BarChart3, Database, Layers, LayoutDashboard, ListChecks, LogOut, Menu, ScrollText, Upload, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, session, setSession } from '../api'
import { Logo } from './Logo'

const nav = [
  ['/app', 'Dashboard', LayoutDashboard, true],
  ['/app/verify', 'New verification', Upload],
  ['/app/batch', 'Batch verify', Layers],
  ['/app/queue', 'Review queue', ListChecks],
  ['/app/records', 'Taxpayer records', Database],
  ['/app/performance', 'Model performance', BarChart3],
  ['/app/audit', 'Audit trail', ScrollText],
]

export default function Shell() {
  const user = session()?.user
  const navigate = useNavigate()
  const [pending, setPending] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  useEffect(() => {
    api('/stats').then((s) => setPending(s.status?.pending ?? null)).catch(() => setPending(null))
  }, [location.pathname])
  useEffect(() => { setMenuOpen(false) }, [location.pathname])
  return (
    <div className="flex min-h-screen bg-ink-950">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-white/[0.06] bg-ink-900/60 p-4 lg:flex">
        <div className="px-2 py-2"><Logo size={32} showTag /></div>
        <nav className="mt-8 flex-1 space-y-1">
          {nav.map(([to, label, Icon, end]) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                isActive ? 'bg-gradient-to-r from-zra-sky/15 to-clear-400/10 text-white ring-1 ring-white/10'
                  : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'}`}>
              <Icon size={17} /> <span className="flex-1">{label}</span>
              {label === 'Review queue' && pending ? <span className="rounded-full bg-zra-sky/20 px-2 py-0.5 font-mono text-[10px] font-bold text-clear-300 ring-1 ring-clear-400/20">{pending}</span> : null}
            </NavLink>
          ))}
        </nav>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-zra-navy to-zra-sky text-sm font-bold text-white">
              {user?.name?.split(' ').map((s) => s[0]).join('')}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-white">{user?.name}</div>
              <div className="truncate text-xs text-slate-500">{user?.role} · {user?.unit}</div>
            </div>
            <button title="Sign out" onClick={() => { setSession(null); navigate('/login') }}
              className="rounded-lg p-1.5 text-slate-500 hover:bg-white/5 hover:text-white"><LogOut size={16} /></button>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-center gap-2 rounded-xl bg-white px-2 py-2">
          <img src="/zra-logo.png" alt="Zambia Revenue Authority" className="h-14" />
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <div className="sticky top-0 z-20 border-b border-white/[0.06] bg-ink-950/85 backdrop-blur lg:hidden">
          <div className="flex items-center justify-between px-4 py-3">
            <Logo size={28} />
            <button onClick={() => setMenuOpen((v) => !v)} className="rounded-lg p-2 text-slate-300 hover:bg-white/5 hover:text-white" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}>
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
          {menuOpen && (
            <div className="border-t border-white/[0.06] bg-ink-900/95 px-4 py-3 backdrop-blur">
              <nav className="grid gap-1 sm:grid-cols-2">
                {nav.map(([to, label, Icon, end]) => (
                  <NavLink key={to} to={to} end={end}
                    className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition ${
                      isActive ? 'bg-gradient-to-r from-zra-sky/15 to-clear-400/10 text-white ring-1 ring-white/10'
                        : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'}`}>
                    <Icon size={17} /> <span className="flex-1">{label}</span>
                    {label === 'Review queue' && pending ? <span className="rounded-full bg-zra-sky/20 px-2 py-0.5 font-mono text-[10px] font-bold text-clear-300 ring-1 ring-clear-400/20">{pending}</span> : null}
                  </NavLink>
                ))}
              </nav>
              <button onClick={() => { setSession(null); navigate('/login') }}
                className="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium text-slate-400 transition hover:bg-white/[0.04] hover:text-slate-200">
                <LogOut size={17} /> Sign out ({user?.name})
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 border-b border-white/[0.04] bg-amber-400/[0.04] px-6 py-1.5 text-[11px] text-amber-200/70">
          <Activity size={12} /> Pilot sandbox · synthetic data only · flags support officer judgement and are not fraud determinations
        </div>
        <main className="mx-auto max-w-[1400px] px-4 py-8 sm:px-8"><Outlet /></main>
      </div>
    </div>
  )
}
