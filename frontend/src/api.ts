import { useCallback, useEffect, useState } from 'react'

// API 回應結構以 any 為主；計算邏輯全在後端，前端只負責呈現
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Json = any

declare global {
  interface Window {
    __DASHBOARD_SNAPSHOT__?: Record<string, Json>
  }
}

let _remoteSnapLoaded = false
let _remoteSnapPromise: Promise<void> | null = null

/** 在 GitHub Pages 靜態模式下，於首次載入時附加 timestamp 動態抓取最新 snapshot.js，破除瀏覽器與 CDN 快取 */
export function ensureFreshSnapshot(): Promise<void> {
  if (!window.__DASHBOARD_SNAPSHOT__ || _remoteSnapLoaded) return Promise.resolve()
  if (_remoteSnapPromise) return _remoteSnapPromise
  _remoteSnapPromise = fetch(`./snapshot.js?t=${Date.now()}`, { cache: 'no-store' })
    .then((r) => (r.ok ? r.text() : ''))
    .then((txt) => {
      const prefix = 'window.__DASHBOARD_SNAPSHOT__='
      if (txt.startsWith(prefix)) {
        const jsonStr = txt.slice(prefix.length).trim().replace(/;$/, '')
        window.__DASHBOARD_SNAPSHOT__ = JSON.parse(jsonStr)
      }
    })
    .catch(() => {
      /* ignore */
    })
    .finally(() => {
      _remoteSnapLoaded = true
    })
  return _remoteSnapPromise
}

export function isStaticMode(): boolean {
  return Boolean(window.__DASHBOARD_SNAPSHOT__)
}

export function reloadSnapshot(): Promise<void> {
  _remoteSnapLoaded = false
  _remoteSnapPromise = null
  return ensureFreshSnapshot()
}

export async function api<T = Json>(path: string, init?: RequestInit): Promise<T> {
  // 靜態發佈模式（GitHub Pages）：若 window.__DASHBOARD_SNAPSHOT__ 存在且為 GET，直接回傳預先計算好的快照
  const snap = window.__DASHBOARD_SNAPSHOT__
  const method = (init?.method ?? 'GET').toUpperCase()
  if (snap && method === 'GET' && path in snap) {
    return snap[path] as T
  }

  try {
    const r = await fetch(path, init)
    if (!r.ok) {
      let msg = `${r.status}`
      try {
        const j = await r.json()
        msg = j.detail ?? msg
      } catch {
        /* ignore */
      }
      throw new Error(msg)
    }
    return await r.json()
  } catch (e) {
    if (snap && path in snap) {
      return snap[path] as T
    }
    if (snap && method !== 'GET') {
      throw new Error('目前為 GitHub Pages 靜態展示模式；請修改 backend/config/watchlist.csv 後執行 python3 sync_github.py 更新。')
    }
    throw e
  }
}

export function useApi<T = Json>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(() => {
    const snap = window.__DASHBOARD_SNAPSHOT__
    return path && snap && path in snap ? (snap[path] as T) : null
  })
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const load = useCallback(() => {
    if (!path) return
    const snap = window.__DASHBOARD_SNAPSHOT__
    if (snap && path in snap) {
      setData(snap[path] as T)
      setError(null)
      ensureFreshSnapshot().then(() => {
        const latest = window.__DASHBOARD_SNAPSHOT__
        if (latest && path in latest) setData(latest[path] as T)
      })
      return
    }
    setLoading(true)
    api<T>(path)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps])
  useEffect(load, [load])
  return { data, error, loading, reload: load }
}
