import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, BadgeCheck, Eye, FileScan, Fingerprint, GitCompareArrows, Lock, ScanLine, ShieldAlert,
  Sparkles, UserCheck, Zap,
} from 'lucide-react'
import { CoBrand, Logo, LogoMark } from '../components/Logo'

function HeroCard() {
  const rows = [
    ['NRC No.', '783849/52/1', 'match'],
    ['Full name', 'PRECIOUS MWEEMBA CHISENGA', 'match'],
    ['Date of birth', '08.04.2006', 'match'],
    ['District', 'KABWE ≠ MONZE (code 52)', 'flag'],
  ]
  return (
    <div className="relative mx-auto w-full max-w-[520px] animate-float">
      <div className="absolute -inset-6 rounded-[2rem] bg-gradient-to-br from-zra-sky/30 via-clear-400/20 to-transparent blur-3xl" />
      <div className="card relative overflow-hidden p-5 shadow-2xl shadow-black/50">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-400">
            <ScanLine size={14} className="text-clear-400" /> SC-0101 · nrc-syn-0101.pdf
          </div>
          <span className="rounded-full bg-rose-500/10 px-2.5 py-1 text-[11px] font-semibold text-rose-300 ring-1 ring-rose-400/25">
            High risk · 70
          </span>
        </div>
        {/* stylised NRC */}
        <div className="relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-[#f3ead9] to-[#e9dcc4] p-4 text-[#2a2a2a]">
          <div className="flex items-start justify-between">
            <div className="text-[9px] font-bold leading-tight tracking-wide">REPUBLIC OF ZAMBIA<br />
              <span className="text-[15px] font-black tracking-tight">NATIONAL REGISTRATION CARD</span></div>
            <div className="font-mono text-[13px] font-semibold">Z 88234889</div>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-y-2 font-mono text-[11px]">
            <div className="col-span-3"><span className="block text-[7px] font-sans font-bold text-[#777]">FULL NAME</span>
              <span className="rounded bg-emerald-500/20 px-1 ring-1 ring-emerald-600/40">PRECIOUS MWEEMBA CHISENGA</span></div>
            <div><span className="block text-[7px] font-sans font-bold text-[#777]">DATE OF BIRTH</span>
              <span className="rounded bg-emerald-500/20 px-1 ring-1 ring-emerald-600/40">08.04.06</span></div>
            <div><span className="block text-[7px] font-sans font-bold text-[#777]">PLACE OF BIRTH</span>NANSANGA D.MONZE</div>
            <div className="text-right"><span className="block text-[7px] font-sans font-bold text-[#777]">SEX</span>F</div>
            <div className="col-span-2"><span className="block text-[7px] font-sans font-bold text-[#777]">VILLAGE</span>NANSANGA</div>
            <div className="text-right"><span className="block text-[7px] font-sans font-bold text-[#777]">DISTRICT</span>
              <span className="rounded bg-rose-500/20 px-1 ring-1 ring-rose-600/50">KABWE</span></div>
          </div>
          <div className="pointer-events-none absolute inset-x-0 top-0 h-full">
            <div className="h-16 w-full animate-scan bg-gradient-to-b from-transparent via-cyan-400/30 to-transparent" />
          </div>
        </div>
        <div className="mt-4 space-y-2">
          {rows.map(([k, v, s], i) => (
            <div key={k} className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-xs animate-fadeup"
              style={{ animationDelay: `${0.3 + i * 0.15}s` }}>
              <span className="text-slate-500">{k}</span>
              <span className="flex items-center gap-2 font-mono text-slate-200">{v}
                {s === 'match' ? <BadgeCheck size={14} className="text-emerald-400" /> : <ShieldAlert size={14} className="text-rose-400" />}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const steps = [
  { Icon: FileScan, t: 'Scanned NRC', d: 'Officer uploads the PDF or image presented at registration.' },
  { Icon: Sparkles, t: 'AI/OCR extraction', d: 'Deep-learning OCR reads NRC number, name and date of birth in about a second, with confidence for every field.' },
  { Icon: GitCompareArrows, t: 'Record verification', d: 'Exact match on NRC and DOB, smart name matching that tolerates order, case and a missing middle name.' },
  { Icon: ShieldAlert, t: 'Anomaly & fraud flags', d: 'Explainable rules plus a trained tamper detector catch altered digits, swapped fonts and erasures.' },
  { Icon: UserCheck, t: 'Officer decision', d: 'Evidence on one screen. The officer approves, rejects or escalates, and every action is audited.' },
]

const features = [
  { Icon: Fingerprint, t: 'Field-level tamper detection', d: 'A model trained on synthetic forgeries spots correction patches, spliced digits, substituted surnames and blurred fields. It shows the reason, not just a score.' },
  { Icon: Eye, t: 'Explainable by design', d: 'Every flag says what was found and where: the NRC district code that doesn’t match, the age at registration, the character in a different ink.' },
  { Icon: Lock, t: 'Privacy-first', d: 'Developed entirely on synthetic NRCs. It runs on-premise in ZRA’s sandbox, with no cloud OCR and no data leaving the network.' },
  { Icon: Zap, t: 'Built for the counter', d: 'About a second per document on a laptop CPU. A risk-sorted queue puts the cases that matter first.' },
]

export default function Landing() {
  const [m, setM] = useState(null)
  useEffect(() => { fetch('/api/public/metrics').then((r) => r.json()).then(setM).catch(() => {}) }, [])
  const pct = (v) => (v === undefined ? '—' : `${Math.round(v * 1000) / 10}%`)
  return (
    <div className="relative min-h-screen overflow-hidden bg-ink-950">
      <div className="grid-bg pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[600px] w-[900px] -translate-x-1/2 rounded-full bg-zra-navy/40 blur-[140px]" />

      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-4 py-5 sm:px-6">
        <CoBrand size={34} />
        <nav className="hidden items-center gap-8 text-sm text-slate-400 md:flex">
          <a href="#how" className="hover:text-white">How it works</a>
          <a href="#features" className="hover:text-white">Capabilities</a>
          <a href="#results" className="hover:text-white">Results</a>
        </nav>
        <Link to="/login" className="btn-ghost">Officer sign in <ArrowRight size={15} /></Link>
      </header>

      <section className="relative z-10 mx-auto grid max-w-7xl items-center gap-14 px-4 pb-24 pt-12 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-20">
        <div className="animate-fadeup">
          <div className="inline-flex items-center gap-2 rounded-full border border-zra-gold/30 bg-zra-gold/10 px-3 py-1 text-xs font-semibold text-[#E5C77A]">
            <span className="h-1.5 w-1.5 rounded-full bg-zra-gold" /> Zambia Revenue Authority · AI Unit pilot
          </div>
          <p className="mt-4 font-display text-sm font-semibold italic tracking-wide text-[#E5C77A]">
            My Tax, Your Tax, Our Destiny
          </p>
          <h1 className="mt-4 font-display text-5xl font-extrabold leading-[1.05] tracking-tight text-white sm:text-6xl">
            Verify every NRC<br /><span className="grad-text">in seconds, not minutes.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-400">
            SmartClear reads scanned National Registration Cards, checks them against captured taxpayer records,
            and flags altered or inconsistent documents so registration officers can act at the counter.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/login" className="btn-primary px-6 py-3 text-[15px]">Open the officer console <ArrowRight size={16} /></Link>
            <a href="#how" className="btn-ghost px-6 py-3 text-[15px]">See how it works</a>
          </div>
          <div className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-white/[0.07] pt-8">
            <div><div className="font-display text-3xl font-bold text-white">{pct(m?.extraction_accuracy)}</div><div className="mt-1 text-xs text-slate-500">key-field extraction</div></div>
            <div><div className="font-display text-3xl font-bold text-white">{pct(m?.fraud_recall)}</div><div className="mt-1 text-xs text-slate-500">fraud cases flagged</div></div>
            <div><div className="font-display text-3xl font-bold text-white">~{m?.median_seconds ?? '1'}s</div><div className="mt-1 text-xs text-slate-500">per document</div></div>
          </div>
        </div>
        <HeroCard />
      </section>

      <section id="how" className="relative z-10 border-y border-white/[0.06] bg-ink-900/50 py-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="label text-clear-400">The workflow</div>
          <h2 className="mt-3 max-w-2xl font-display text-4xl font-bold tracking-tight text-white">Extract → Verify → Flag → Review</h2>
          <p className="mt-4 max-w-2xl text-slate-400">A human-in-the-loop pipeline. SmartClear supports the officer’s judgement and never replaces it: a flag means “look closer”, not “fraud”.</p>
          <div className="mt-14 grid gap-4 md:grid-cols-5">
            {steps.map(({ Icon, t, d }, i) => (
              <div key={t} className="card group relative p-5 transition hover:border-clear-400/30 hover:bg-white/[0.05]">
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-zra-sky/20 to-clear-400/20 text-clear-300 ring-1 ring-white/10">
                    <Icon size={19} />
                  </div>
                  <span className="font-mono text-xs text-slate-600">0{i + 1}</span>
                </div>
                <div className="font-semibold text-white">{t}</div>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="relative z-10 py-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="grid gap-12 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <div className="label text-clear-400">Capabilities</div>
              <h2 className="mt-3 font-display text-4xl font-bold tracking-tight text-white">Catches what the eye misses.</h2>
              <p className="mt-4 text-slate-400">Manual checks are slow and inconsistent, and they can’t reliably spot a digitally altered document. SmartClear checks every card, every time, the same way.</p>
              <div className="mt-8 flex items-center gap-3 text-sm text-slate-500"><LogoMark size={28} /> Built for ZRA’s Taxpayer Services & Education and Domestic Taxes Division.</div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {features.map(({ Icon, t, d }) => (
                <div key={t} className="card p-6">
                  <Icon size={22} className="text-clear-400" />
                  <div className="mt-4 font-semibold text-white">{t}</div>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{d}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="results" className="relative z-10 pb-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="card relative overflow-hidden p-8 sm:p-12">
            <div className="absolute -right-20 -top-20 h-72 w-72 rounded-full bg-clear-400/10 blur-3xl" />
            <div className="label text-clear-400">Pilot results · synthetic NRC set ({m?.documents ?? 100} documents)</div>
            <div className="mt-8 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
              {[['Extraction accuracy', pct(m?.extraction_accuracy), 'NRC no., name, DOB vs manual reading'],
                ['Verification accuracy', pct(m?.verification_accuracy), 'match / review / mismatch vs expected'],
                ['Fraud recall', pct(m?.fraud_recall), 'labelled fraudulent NRCs flagged'],
                ['Flag precision', pct(m?.fraud_precision), 'flags that were real issues']].map(([a, b, c]) => (
                <div key={a}>
                  <div className="font-display text-4xl font-bold text-white">{b}</div>
                  <div className="mt-2 text-sm font-medium text-slate-300">{a}</div>
                  <div className="mt-1 text-xs text-slate-500">{c}</div>
                </div>
              ))}
            </div>
            <p className="mt-8 max-w-3xl text-xs leading-relaxed text-slate-500">Measured on synthetic specimens. The tamper model is scored with document-grouped cross-validation, so no card is scored by a model that trained on it. Baselines against ZRA’s manual process will be established with real documents inside ZRA’s controlled sandbox.</p>
          </div>
        </div>
      </section>

      <footer className="relative z-10 border-t border-white/[0.06] py-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 text-xs text-slate-500 sm:px-6">
          <Logo size={26} />
          <span className="flex flex-col items-center gap-1 text-center">
            <span className="font-semibold italic text-[#E5C77A]">My Tax, Your Tax, Our Destiny</span>
            <span>A ZRA AI Unit pilot · AI for Public Good Challenge · Mukuba UniPod (CBU)</span>
          </span>
          <span>Prototype: not for production use</span>
        </div>
      </footer>
    </div>
  )
}
