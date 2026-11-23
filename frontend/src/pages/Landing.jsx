import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, BadgeCheck, ChevronDown, Clock, CreditCard, HeartHandshake, Lock, Search, ShieldCheck, Smile,
  UserCheck, Users,
} from 'lucide-react'
import { CoBrand, Logo } from '../components/Logo'

const pillars = [
  { Icon: Clock, t: 'Faster service', d: 'Your card is checked in about a second, so you spend less time waiting at the counter.' },
  { Icon: ShieldCheck, t: 'Protects your identity', d: 'It helps stop anyone from registering for tax using your name or a fake card.' },
  { Icon: UserCheck, t: 'A person always decides', d: 'SmartClear only helps. A trained ZRA officer makes every final decision.' },
  { Icon: Lock, t: 'Your details stay private', d: 'Your name, NRC number and date of birth stay on government systems and are never sent to outside companies.' },
]

const steps = [
  { Icon: CreditCard, t: 'Show your NRC', d: 'At registration, the officer scans your National Registration Card, just as they do today.' },
  { Icon: Search, t: 'SmartClear checks it', d: 'In about a second it reads your name, NRC number and date of birth, and compares them with what you filled in.' },
  { Icon: BadgeCheck, t: 'The officer confirms', d: 'If everything matches, you’re on your way. If something looks off, the officer takes a closer look with you.' },
]

const people = [
  { img: '/images/person-woman.jpg', t: 'Taxpayers', d: 'Register quickly and know that nobody else can sign up in your name.' },
  { img: '/images/person-man.jpg', t: 'Small business owners', d: 'Get your TPIN sorted with fewer trips back and forth.' },
  { img: '/images/person-woman3.jpg', t: 'ZRA officers', d: 'Spend less time squinting at faded cards and more time helping people.' },
]

const faqs = [
  ['Does a computer decide if I can register?', 'No. SmartClear only points out things worth a second look. A ZRA officer always looks at your case and makes the decision, and nothing on your record is ever changed automatically.'],
  ['What happens to the scan of my NRC?', 'It stays on ZRA’s own systems. Your details are checked against the national register at the Ministry of Home Affairs, and are never sent to any outside company. Every time someone views or acts on a case it is written down for accountability.'],
  ['My card is old or faded. Will that be a problem?', 'No. If part of the card is hard to read, SmartClear says so instead of guessing, and the officer simply checks that part by eye.'],
  ['What if SmartClear flags my card by mistake?', 'A flag just means “please check this”. It is not an accusation. The officer looks at the card with you and can approve it straight away.'],
  ['Is this being used at ZRA offices today?', 'Not yet. SmartClear is a pilot being tested with practice cards by the ZRA AI Unit. It will only be used with real cards inside ZRA’s secure environment.'],
]

/** Fades children in when they scroll into view. */
function Reveal({ children, className = '', delay = 0, as: Tag = 'div' }) {
  const ref = useRef(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) { setShown(true); return }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect() } },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return <Tag ref={ref} className={`reveal ${shown ? 'is-visible' : ''} ${className}`} style={{ transitionDelay: `${delay}ms` }}>{children}</Tag>
}

/** Counts up to a number once visible ("99%", "~1s"). */
function CountUp({ value }) {
  const m = /^(\D*)(\d+(?:\.\d+)?)(.*)$/.exec(value || '')
  const ref = useRef(null)
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!m) return
    const target = parseFloat(m[2])
    let raf, start
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return
      io.disconnect()
      const tick = (t) => {
        start ??= t
        const k = Math.min(1, (t - start) / 1200)
        setN(target * (1 - Math.pow(1 - k, 3)))
        if (k < 1) raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
    })
    ref.current && io.observe(ref.current)
    return () => { io.disconnect(); cancelAnimationFrame(raf) }
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!m) return <span>{value}</span>
  const decimals = m[2].includes('.') ? 1 : 0
  return <span ref={ref}>{m[1]}{n.toFixed(decimals)}{m[3]}</span>
}

function Faq({ q, a }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-slate-200 last:border-0">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-4 py-5 text-left" aria-expanded={open}>
        <span className="text-base font-semibold text-slate-900">{q}</span>
        <ChevronDown size={20} className={`shrink-0 text-slate-400 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <p className="-mt-1 pb-5 pr-8 leading-relaxed text-slate-600">{a}</p>}
    </div>
  )
}

export default function Landing() {
  const [m, setM] = useState(null)
  useEffect(() => { fetch('/api/public/metrics').then((r) => r.json()).then(setM).catch(() => {}) }, [])
  const pct = (v) => (v === undefined ? '—' : `${Math.round(v * 100)}%`)
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  return (
    <div id="top" className="min-h-screen bg-cream text-slate-700">
      <header className="fixed inset-x-0 top-0 z-30 px-3 pt-3 sm:px-6 sm:pt-4">
        <div className={`mx-auto flex items-center justify-between rounded-full border bg-white/80 pl-4 pr-2 backdrop-blur-xl transition-all duration-500 sm:pl-5 ${
          scrolled ? 'max-w-5xl border-slate-200/80 py-1.5 shadow-[0_12px_40px_-12px_rgba(15,23,42,.25)]' : 'max-w-7xl border-white/60 py-2.5 shadow-[0_8px_30px_-16px_rgba(15,23,42,.18)]'}`}>
          <a href="#top" aria-label="SmartClear home"><CoBrand size={scrolled ? 30 : 34} /></a>
          <nav className="hidden items-center gap-1 text-sm font-medium text-slate-600 md:flex">
            {[['#how', 'How it works'], ['#who', 'Who it helps'], ['#faq', 'Questions']].map(([href, label]) => (
              <a key={href} href={href} className="rounded-full px-4 py-2 transition hover:bg-slate-100 hover:text-zra-navy">{label}</a>
            ))}
          </nav>
          <Link to="/login" className="btn-primary px-4 py-2">Staff sign in <ArrowRight size={15} /></Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute -right-40 -top-40 h-[520px] w-[520px] animate-drift rounded-full bg-zra-sky/15 blur-3xl" />
        <div className="pointer-events-none absolute -left-32 top-40 h-[380px] w-[380px] animate-drift rounded-full bg-zra-gold/15 blur-3xl [animation-delay:-7s]" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-4 pb-20 pt-32 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-40">
          <div className="animate-fadeup">
            <h1 className="font-display text-[2.6rem] font-extrabold leading-[1.08] tracking-tight text-slate-900 sm:text-6xl">
              Registering for tax,<br />
              <span className="text-zra-navy">made quicker</span> and <span className="text-zra-sky">safer.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">
              SmartClear helps ZRA officers check your National Registration Card (NRC) in seconds. Honest
              taxpayers get through faster, and it’s much harder for anyone to register in your name.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <a href="#how" className="btn-primary px-7 py-3.5 text-base">See how it works <ArrowRight size={18} /></a>
              <a href="#faq" className="btn-ghost px-7 py-3.5 text-base">Common questions</a>
            </div>
            <div className="mt-10 flex items-center gap-4">
              <div className="flex -space-x-3">
                {['person-man.jpg', 'person-woman.jpg', 'person-man2.jpg', 'person-woman2.jpg'].map((f, i) => (
                  <img key={f} src={`/images/${f}`} alt="" style={{ animationDelay: `${0.5 + i * 0.12}s` }}
                    className="h-11 w-11 animate-popin rounded-full border-[3px] border-cream object-cover transition hover:z-10 hover:-translate-y-1" />
                ))}
              </div>
              <p className="text-sm leading-snug text-slate-600"><b className="text-slate-900">Built for every Zambian taxpayer</b><br />from first-time earners to business owners</p>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-[520px] animate-popin [animation-delay:.15s]">
            <div className="absolute inset-4 -rotate-3 animate-wiggle rounded-[2.5rem] bg-zra-sky/15" />
            <img src="/images/hero-woman.jpg" alt="A smiling woman" className="relative aspect-[4/5] w-full rounded-[2.5rem] object-cover shadow-soft" />
            <div className="absolute -left-4 top-10 flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-soft animate-float sm:-left-10">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600"><BadgeCheck size={22} /></span>
              <div><div className="text-sm font-bold text-slate-900">ID checked</div><div className="text-xs text-slate-500">in about 1 second</div></div>
            </div>
            <div className="absolute -right-3 bottom-12 flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-soft animate-float [animation-delay:1.5s] sm:-right-8">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-sky-100 text-zra-navy"><ShieldCheck size={22} /></span>
              <div><div className="text-sm font-bold text-slate-900">Your details stay safe</div><div className="text-xs text-slate-500">on ZRA’s own systems</div></div>
            </div>
          </div>
        </div>
      </section>

      {/* Pillars */}
      <section className="border-y border-slate-200/70 bg-white py-14">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
          {pillars.map(({ Icon, t, d }, i) => (
            <Reveal key={t} delay={i * 100} className="group flex gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-zra-navy/[0.07] text-zra-navy transition duration-300 group-hover:-translate-y-1 group-hover:bg-zra-navy group-hover:text-white"><Icon size={22} /></span>
              <div><div className="font-semibold text-slate-900">{t}</div><p className="mt-1 text-sm leading-relaxed text-slate-600">{d}</p></div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 py-24">
        <div className="mx-auto grid max-w-7xl items-center gap-14 px-4 sm:px-6 lg:grid-cols-2">
          <Reveal className="relative order-2 lg:order-1">
            <div className="overflow-hidden rounded-[2rem] shadow-soft">
              <img src="/images/counter-help.jpg" alt="An officer helping a member of the public at a desk" className="aspect-[5/4] w-full object-cover transition duration-700 hover:scale-105" />
            </div>
            <div className="absolute -bottom-6 right-6 rounded-2xl bg-zra-navy px-5 py-4 text-white shadow-soft">
              <div className="font-display text-3xl font-extrabold">3 steps</div>
              <div className="text-sm text-white/75">and you’re done</div>
            </div>
          </Reveal>
          <Reveal delay={120} className="order-1 lg:order-2">
            <div className="text-sm font-semibold text-zra-sky">How it works</div>
            <h2 className="mt-2 font-display text-4xl font-bold tracking-tight text-slate-900">Nothing changes for you, it just gets faster.</h2>
            <p className="mt-4 text-lg text-slate-600">You register the same way you always have. SmartClear works quietly in the background to help the officer.</p>
            <ol className="mt-10 space-y-6">
              {steps.map(({ Icon, t, d }, i) => (
                <Reveal as="li" key={t} delay={200 + i * 150} className="flex gap-5">
                  <div className="relative flex flex-col items-center">
                    <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-zra-navy shadow-md ring-1 ring-slate-200"><Icon size={22} /></span>
                    {i < steps.length - 1 && <span className="mt-2 w-px flex-1 bg-slate-200" />}
                  </div>
                  <div className="pb-2">
                    <div className="text-xs font-bold text-zra-sky">Step {i + 1}</div>
                    <div className="mt-0.5 text-lg font-semibold text-slate-900">{t}</div>
                    <p className="mt-1 leading-relaxed text-slate-600">{d}</p>
                  </div>
                </Reveal>
              ))}
            </ol>
          </Reveal>
        </div>
      </section>

      {/* Protects you */}
      <section className="bg-white py-24">
        <div className="mx-auto grid max-w-7xl items-center gap-14 px-4 sm:px-6 lg:grid-cols-2">
          <Reveal>
            <div className="text-sm font-semibold text-zra-sky">Why it matters</div>
            <h2 className="mt-2 font-display text-4xl font-bold tracking-tight text-slate-900">Stopping people from pretending to be you.</h2>
            <p className="mt-4 text-lg leading-relaxed text-slate-600">
              Sometimes people try to register using someone else’s details or a card that has been changed.
              These are hard to spot by eye, especially on a busy day. SmartClear notices small things, like a
              number in a different ink or a date that doesn’t add up, and asks the officer to take a second look.
            </p>
            <div className="mt-8 grid gap-4 sm:grid-cols-3">
              {[[pct(m?.extraction_accuracy), 'of practice cards read correctly'],
                [pct(m?.fraud_recall), 'of fake practice cards spotted'],
                [`~${m?.median_seconds ?? 1}s`, 'to check each card']].map(([v, l]) => (
                <div key={l} className="rounded-2xl bg-cream p-5 ring-1 ring-slate-200/70 transition hover:-translate-y-1 hover:shadow-soft">
                  <div className="font-display text-3xl font-extrabold text-zra-navy"><CountUp value={v} /></div>
                  <div className="mt-1 text-sm text-slate-600">{l}</div>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs text-slate-500">Results from testing on {m?.documents ?? 100} practice (made-up) cards. Real-world results will be measured during the pilot.</p>
          </Reveal>
          <Reveal delay={150} className="relative">
            <div className="overflow-hidden rounded-[2rem] shadow-soft">
              <img src="/images/conversation.jpg" alt="Two women talking and smiling" className="aspect-[4/3] w-full object-cover transition duration-700 hover:scale-105" />
            </div>
            <div className="absolute -left-4 -top-6 flex animate-float items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-soft sm:-left-8">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100 text-amber-600"><HeartHandshake size={22} /></span>
              <div className="text-sm font-bold text-slate-900">Trust, on both sides<br /><span className="font-normal text-slate-500">of the counter</span></div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Who it helps */}
      <section id="who" className="scroll-mt-20 py-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <Reveal className="mx-auto max-w-2xl text-center">
            <div className="text-sm font-semibold text-zra-sky">Who it helps</div>
            <h2 className="mt-2 font-display text-4xl font-bold tracking-tight text-slate-900">Good for everyone in the queue.</h2>
          </Reveal>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {people.map(({ img, t, d }, i) => (
              <Reveal key={t} delay={i * 130} className="card group overflow-hidden p-0 transition duration-300 hover:-translate-y-2 hover:shadow-soft">
                <div className="overflow-hidden"><img src={img} alt="" className="aspect-[4/3] w-full object-cover object-top transition duration-700 group-hover:scale-105" /></div>
                <div className="p-6">
                  <div className="text-lg font-semibold text-slate-900">{t}</div>
                  <p className="mt-2 leading-relaxed text-slate-600">{d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-20 bg-white py-24">
        <div className="mx-auto grid max-w-6xl gap-12 px-4 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
          <Reveal>
            <div className="text-sm font-semibold text-zra-sky">Questions</div>
            <h2 className="mt-2 font-display text-4xl font-bold tracking-tight text-slate-900">Things people often ask.</h2>
            <img src="/images/team-meeting.jpg" alt="Colleagues talking around a meeting table" className="mt-8 hidden aspect-[4/3] w-full rounded-[2rem] object-cover shadow-soft lg:block" />
          </Reveal>
          <Reveal delay={150} className="card px-6 sm:px-8">
            {faqs.map(([q, a]) => <Faq key={q} q={q} a={a} />)}
          </Reveal>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <Reveal className="relative overflow-hidden rounded-[2rem] bg-zra-navy px-8 py-14 text-center text-white sm:px-14">
            <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 animate-drift rounded-full bg-zra-sky/30 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-24 -left-16 h-72 w-72 animate-drift rounded-full bg-zra-gold/20 blur-3xl [animation-delay:-6s]" />
            <Smile size={36} className="relative mx-auto animate-wiggle text-zra-gold" />
            <h2 className="mx-auto mt-4 max-w-2xl font-display text-3xl font-bold sm:text-4xl">Less waiting. More trust. Same friendly faces.</h2>
            <p className="mx-auto mt-4 max-w-xl text-white/75">SmartClear is a pilot by the ZRA AI Unit to make registration smoother for every Zambian.</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <a href="#how" className="btn bg-white px-7 py-3.5 text-base text-zra-navy hover:bg-slate-100">How it works</a>
              <Link to="/login" className="btn border border-white/30 px-7 py-3.5 text-base text-white hover:bg-white/10"><Users size={18} /> ZRA staff sign in</Link>
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-white py-10">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-6 px-4 text-sm text-slate-500 sm:px-6">
          <Logo size={30} />
          <span className="flex flex-col items-center gap-1 text-center">
            <span className="font-semibold italic text-zra-gold">My Tax, Your Tax, Our Destiny</span>
            <span className="text-xs">A ZRA AI Unit pilot · AI for Public Good Challenge · Mukuba UniPod (CBU)</span>
          </span>
          <span className="text-xs">Pilot project: not yet in use at ZRA offices</span>
        </div>
      </footer>
    </div>
  )
}
