import { PageHeader, Stat } from '../components/ui'

const fields = [
  ['NRC number', '100%'], ['Card number', '99%'], ['Full name', '81%'],
  ['Date of birth', '95%'], ['Sex', '96%'], ['District', '96%'],
]

export default function Performance() {
  return (
    <div>
      <PageHeader
        title="Model performance"
        subtitle="Fine-tuned PP-OCRv4 recognizer (onnx_model branch). Synthetic cards only; real cards have not been measured."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Stat label="Single text crops, test set" value="97.1%" sub="277 synthetic crops, from the Colab training run" />
        <Stat label="Whole cards, all six fields" value="80 of 100" sub="100 synthetic cards" accent="from-sky-400 to-indigo-400" />
      </div>
      <div className="card mt-6 p-6">
        <div className="font-semibold text-white">Whole-card accuracy by field (100 synthetic cards)</div>
        <table className="mt-5 w-full text-sm">
          <thead><tr><th className="label pb-2 text-left">Field</th><th className="label pb-2 text-right">Read exactly</th></tr></thead>
          <tbody>
            {fields.map(([name, v]) => (
              <tr key={name} className="border-t border-white/5">
                <td className="py-2 text-slate-300">{name}</td>
                <td className="py-2 text-right font-mono text-slate-200">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-5 text-xs leading-relaxed text-slate-500">
          Names are the weakest field. The full charts and method are in the project README.
        </p>
      </div>
    </div>
  )
}
