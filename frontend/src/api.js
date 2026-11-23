const KEY = 'smartclear.session'

export function session() {
  try { return JSON.parse(localStorage.getItem(KEY)) } catch { return null }
}
export function setSession(s) {
  try { s ? localStorage.setItem(KEY, JSON.stringify(s)) : localStorage.removeItem(KEY) } catch {}
}

export async function api(path, opts = {}) {
  const s = session()
  const headers = { ...(opts.headers || {}) }
  if (s?.token) headers.Authorization = `Bearer ${s.token}`
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(opts.json)
  }
  const res = await fetch(`/api${path}`, { ...opts, headers })
  if (res.status === 401 && !path.startsWith('/login')) {
    setSession(null)
    window.location.href = '/login'
    throw new Error('Session expired')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(data.detail || GATEWAY[res.status] || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

// Hosting proxies answer these when the server is busy, restarting or took too long; the work may still finish.
const GATEWAY = {
  502: 'The server is busy or restarting. Please wait a moment and try again.',
  503: 'The server is starting up. Please wait a moment and try again.',
  504: 'The server took too long to answer. Please try again.',
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** Poll a background job until it finishes. Brief gateway errors while polling are retried, not shown. */
export async function waitForJob(id, onProgress, { interval = 1500, maxWaitMs = 30 * 60 * 1000 } = {}) {
  const started = Date.now()
  let misses = 0
  for (;;) {
    let job
    try {
      job = await api(`/jobs/${id}`)
      misses = 0
    } catch (e) {
      if (![502, 503, 504].includes(e.status) && !(e instanceof TypeError) || ++misses > 20) throw e
      await sleep(interval * 2)
      continue
    }
    onProgress?.(job)
    if (job.status === 'done') return job
    if (job.status === 'error') throw new Error(job.error || 'Processing failed')
    if (Date.now() - started > maxWaitMs) throw new Error('Still processing after 30 minutes. Check the review queue later.')
    await sleep(interval)
  }
}

export const imageUrl = (id) => `/api/cases/${id}/image?token=${encodeURIComponent(session()?.token || '')}`
