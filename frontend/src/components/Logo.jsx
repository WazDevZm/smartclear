export function LogoMark({ size = 36, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden>
      <defs>
        <linearGradient id="sc-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1B3F8B" />
          <stop offset="1" stopColor="#1BA3E0" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="18" fill="url(#sc-bg)" />
      <path d="M14 22V16a2 2 0 0 1 2-2h6M42 14h6a2 2 0 0 1 2 2v6M50 42v6a2 2 0 0 1-2 2h-6M22 50h-6a2 2 0 0 1-2-2v-6"
        stroke="white" strokeOpacity=".7" strokeWidth="4" fill="none" strokeLinecap="round" />
      <path d="M21 33l7 7 15-16" stroke="white" strokeWidth="5.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="49.5" cy="14.5" r="3" fill="#C9A24A" />
    </svg>
  )
}

export function Logo({ size = 34, showTag = false }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark size={size} />
      <div className="leading-none">
        <div className="font-display text-[19px] font-extrabold tracking-tight text-slate-900">
          Smart<span className="text-zra-sky">Clear</span>
        </div>
        {showTag && <div className="mt-1 text-[11px] font-medium text-slate-500">Quick, safe ID checks</div>}
      </div>
    </div>
  )
}

export function CoBrand({ size = 34 }) {
  return (
    <div className="flex items-center gap-4">
      <Logo size={size} showTag />
      <div className="hidden h-9 w-px bg-slate-200 sm:block" />
      <img src="/zra-logo.png" alt="Zambia Revenue Authority" className="hidden h-11 w-auto sm:block" />
    </div>
  )
}
