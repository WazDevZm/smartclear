import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { api } from '../api'
import { PageHeader, Pagination, Spinner, usePagination } from '../components/ui'

export default function Records() {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState(null)
  useEffect(() => {
    const t = setTimeout(() => api(`/taxpayers${q ? `?q=${encodeURIComponent(q)}` : ''}`).then(setRows), 200)
    return () => clearTimeout(t)
  }, [q])
  const pg = usePagination(rows)
  return (
    <div>
      <PageHeader title="Captured taxpayer records" subtitle="Synthetic stand-in for ZRA’s registration records (the real source is still being identified)" />
      <div className="relative mb-5 max-w-md">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input className="input pl-9" placeholder="Search name, NRC or TPIN…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!rows ? <Spinner /> : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[800px] text-sm">
            <thead><tr className="border-b border-white/[0.06] text-left">
              {['TPIN', 'Full name', 'NRC number', 'Date of birth', 'Sex', 'District', 'Test scenario'].map((h) => <th key={h} className="label px-5 py-3.5">{h}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-white/[0.05]">
              {pg.slice.map((r) => (
                <tr key={r.tpin} className="hover:bg-white/[0.02]">
                  <td className="px-5 py-3 font-mono text-xs text-slate-400">{r.tpin}</td>
                  <td className="px-5 py-3 text-white">{r.full_name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-300">{r.nrc_number}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-300">{r.date_of_birth}</td>
                  <td className="px-5 py-3 text-slate-400">{r.sex}</td>
                  <td className="px-5 py-3 text-slate-400">{r.district}</td>
                  <td className="px-5 py-3"><span className="rounded-md bg-white/[0.04] px-2 py-0.5 font-mono text-[11px] text-slate-400">{r.scenario}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <div className="p-10 text-center text-sm text-slate-500">No records match “{q}”.</div>}
          <Pagination {...pg} />
        </div>
      )}
    </div>
  )
}
