export function LogoMark({ size = 36, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden>
      <defs>
        <linearGradient id="sc-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1BA3E0" />
          <stop offset="1" stopColor="#2DD4BF" />
        </linearGradient>
        <linearGradient id="sc-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#13234A" />
          <stop offset="1" stopColor="#0A1428" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill="url(#sc-bg)" />
      <rect x="0.75" y="0.75" width="62.5" height="62.5" rx="15.25" fill="none" stroke="white" strokeOpacity=".08" />
      <path d="M14 22V16a2 2 0 0 1 2-2h6M42 14h6a2 2 0 0 1 2 2v6M50 42v6a2 2 0 0 1-2 2h-6M22 50h-6a2 2 0 0 1-2-2v-6"
        stroke="url(#sc-g)" strokeWidth="4" fill="none" strokeLinecap="round" />
      <path d="M21 33l7 7 15-16" stroke="url(#sc-g)" strokeWidth="5.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="49.5" cy="14.5" r="2.5" fill="#C9A24A" />
    </svg>
  )
}

export function Logo({ size = 34, showTag = false }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark size={size} />
      <div className="leading-none">
        <div className="font-display text-[19px] font-extrabold tracking-tight text-white">
          Smart<span className="grad-text">Clear</span>
        </div>
        {showTag && <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">AI NRC Verification</div>}
      </div>
    </div>
  )
}

export function CoBrand({ size = 34 }) {
  return (
    <div className="flex items-center gap-4">
      <Logo size={size} showTag />
      <div className="h-9 w-px bg-white/10" />
      <div className="flex items-center gap-2 rounded-xl bg-white px-3 py-1.5 shadow-lg shadow-black/20">
        <img src="/zra-logo.png" alt="Zambia Revenue Authority" className="h-11 w-auto" />
      </div>
    </div>
  )
}
