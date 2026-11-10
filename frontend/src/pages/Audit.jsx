import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { PageHeader, Spinner } from '../components/ui'

export default function Audit() {
  const [rows, setRows] = useState(null)
  useEffect(() => { api('/audit').then(setRows) }, [])
  if (!rows) return <Spinner />
  return (
    <div>
      <PageHeader title="Audit trail" subtitle="Every submission, view and decision is recorded" />
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[700px] text-sm">
          <thead><tr className="border-b border-white/[0.06] text-left">{['Time', 'Actor', 'Action', 'Case', 'Detail'].map((h) => <th key={h} className="label px-5 py-3.5">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-white/[0.05]">
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="whitespace-nowrap px-5 py-2.5 font-mono text-xs text-slate-500">{new Date(r.ts).toLocaleString()}</td>
                <td className="px-5 py-2.5 text-slate-300">{r.actor}</td>
                <td className="px-5 py-2.5"><span className="rounded-md bg-white/[0.04] px-2 py-0.5 text-xs text-slate-300">{r.action}</span></td>
                <td className="px-5 py-2.5">{r.case_id && <Link to={`/app/cases/${r.case_id}`} className="font-mono text-xs text-clear-300">#{r.case_id}</Link>}</td>
                <td className="max-w-md truncate px-5 py-2.5 font-mono text-[11px] text-slate-500">{r.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
