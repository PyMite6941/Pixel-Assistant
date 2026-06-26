const BASE = '/api'

export async function apiGet<T = any>(path: string): Promise<T> {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`)
  return r.json()
}

export async function apiPost<T = any>(path: string, body?: any): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`)
  return r.json()
}

export async function apiPut<T = any>(path: string, body: any): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`)
  return r.json()
}

export async function apiPatch<T = any>(path: string, body?: any): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'PATCH',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`)
  return r.json()
}

export async function apiDelete<T = any>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { method: 'DELETE' })
  if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`)
  return r.json()
}
