import { useEffect, useState } from 'react'
import { api, isStaticMode, reloadSnapshot, useApi } from './api'
import { AlertsView } from './components/AlertsView'
import { MarketDashboard } from './components/MarketDashboard'
import { StockDetail } from './components/StockDetail'
import { Pill } from './components/ui'
import { WatchlistView } from './components/WatchlistView'

type Tab = 'market' | 'watchlist' | 'stock' | 'alerts'

export default function App() {
  const [tab, setTab] = useState<Tab>('market')
  const [symbol, setSymbol] = useState('2330')
  const [dark, setDark] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const sum = useApi('/api/market/summary')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const openStock = (sym: string) => {
    setSymbol(sym)
    setTab('stock')
  }

  const doRefresh = async () => {
    setRefreshing(true)
    try {
      if (isStaticMode()) {
        await reloadSnapshot()
        return
      }
      await api('/api/refresh', { method: 'POST' })
      sum.reload()
    } finally {
      setRefreshing(false)
    }
  }

  const inst = sum.data?.data_status?.institutional_progress

  return (
    <div className="min-h-screen flex flex-col">
      <header className="panel rounded-none border-x-0 border-t-0 px-4 py-2 flex flex-wrap items-center justify-between gap-2 sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="font-bold text-sm tracking-wide">台股市場狀態儀表板 · Market &amp; Stock Regime</div>
          {sum.data?.regime && (
            <Pill tone={sum.data.regime.tone}>
              {sum.data.regime.label} · {sum.data.score ?? 'N/A'}/100
            </Pill>
          )}
        </div>

        <nav className="flex items-center gap-1">
          {([
            ['market', '大盤總覽 Market'],
            ['watchlist', '自選股 Watchlist (CSV)'],
            ['stock', `個股深度 (${symbol})`],
            ['alerts', '警示中心 Alerts'],
          ] as const).map(([k, lab]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`px-3 py-1 rounded text-[12px] border line transition ${tab === k ? 'bg-white/10 font-semibold' : 'muted hover:text-[var(--text)]'}`}
            >
              {lab}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-2 text-[11px] muted">
          {inst?.running && (
            <Pill tone="caution">
              法人資料回補中 {inst.market?.[0]}/{inst.market?.[1]}
            </Pill>
          )}
          <span className="num">Last updated: {sum.data?.last_updated ?? '—'} (TST)</span>
          <button onClick={doRefresh} disabled={refreshing} className="px-2 py-0.5 rounded border line hover:text-[var(--text)]" title="重新載入最新快照資料（破除瀏覽器快取）">
            {refreshing ? '載入中…' : '↻ 重新載入最新資料'}
          </button>
          {isStaticMode() && (
            <a
              href="https://github.com/mimiba0925/tw_stock_regime_dashboard/actions/workflows/update_data.yml"
              target="_blank"
              rel="noreferrer"
              className="px-2 py-0.5 rounded border line hover:text-[var(--text)]"
              title="每日 14:25 / 17:20 / 21:45 / 06:30 (台灣時間) 自動更新，或點擊前往 GitHub Actions 手動觸發 Run workflow"
            >
              ⚡ 雲端觸發重算
            </a>
          )}
          <button onClick={() => setDark((d) => !d)} className="px-2 py-0.5 rounded border line hover:text-[var(--text)]">
            {dark ? '☀ 淺色' : '☾ 深色'}
          </button>
        </div>
      </header>

      <main className="flex-1 p-3 max-w-[1600px] w-full mx-auto">
        {tab === 'market' && <MarketDashboard onOpenStock={openStock} onOpenTab={(t) => setTab(t as Tab)} />}
        {tab === 'watchlist' && <WatchlistView onSelect={openStock} />}
        {tab === 'stock' && <StockDetail symbol={symbol} onSelect={openStock} />}
        {tab === 'alerts' && <AlertsView onOpenStock={openStock} />}
      </main>

      <footer className="px-4 py-2 text-[11px] muted border-t line flex flex-wrap justify-between gap-2">
        <span>設計理念：State + Change + Trend + Acceleration + Relative Strength + Historical Percentile → Regime（Don’t show more data. Show more context.）</span>
        <span>自選股清單：backend/config/watchlist.csv｜權重與門檻：backend/config/settings.yaml</span>
      </footer>
    </div>
  )
}
