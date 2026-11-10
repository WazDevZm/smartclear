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
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

export const imageUrl = (id) => `/api/cases/${id}/image?token=${encodeURIComponent(session()?.token || '')}`
