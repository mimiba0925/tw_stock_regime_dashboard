import { useState } from 'react'
import { api, useApi } from '../api'
import { fmtNum, fmtPct, isNum, NA, scoreTone, signTone } from '../format'
import { Card, ErrorBox, Loading, Pill, QualityBadge, Sparkline, Value } from './ui'

export function WatchlistView({ onSelect }: { onSelect: (sym: string) => void }) {
  const { data, error, loading, reload } = useApi('/api/stocks/watchlist')
  const [sortKey, setSortKey] = useState<'score' | 'rs' | 'trend' | 'momentum' | 'chip' | 'fundamental' | 'change'>('score')
  const [symbol, setSymbol] = useState('')
  const [name, setName] = useState('')
  const [market, setMarket] = useState<'TWSE' | 'TPEX'>('TWSE')
  const [sector, setSector] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />

  const rows = [...(data?.rows ?? [])].sort((a, b) => (b[sortKey] ?? -999) - (a[sortKey] ?? -999))

  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!symbol.trim()) return
    setBusy(true)
    setMsg(null)
    try {
      await api('/api/stocks/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: symbol.trim(), name: name.trim() || symbol.trim(), market, sector: sector.trim() || '未分類' }),
      })
      setSymbol(''); setName(''); setSector('')
      reload()
    } catch (err: any) {
      setMsg(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (sym: string, ev: React.MouseEvent) => {
    ev.stopPropagation()
    setBusy(true)
    try {
      await api(`/api/stocks/watchlist/${sym}`, { method: 'DELETE' })
      reload()
    } finally {
      setBusy(false)
    }
  }

  const scoreCell = (v: number | null | undefined) => (
    <td className="py-2 px-2 text-right">
      <Value v={isNum(v) ? v.toFixed(0) : NA} tone={scoreTone(v)} className="font-semibold" />
    </td>
  )

  const th = (k: typeof sortKey, label: string) => (
    <th onClick={() => setSortKey(k)} className="text-right pb-1.5 px-2 cursor-pointer hover:text-[var(--text)]">
      {label} {sortKey === k ? '▼' : ''}
    </th>
  )

  return (
    <div className="flex flex-col gap-3">
      <Card
        title="自選股 Watchlist（與 CSV 檔案雙向同步）"
        question="我的自選股誰最強？是否強於大盤？目前處於什麼 Regime？"
        subtitle={`CSV 路徑：backend/${data?.csv ?? 'config/watchlist.csv'}（可直接用文字編輯器/Excel 修改，或於下方新增/刪除）`}
      >
        <form onSubmit={add} className="flex flex-wrap items-center gap-2 pb-2 border-b line text-[12px]">
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="代號 例 2330" className="px-2 py-1 rounded border line bg-transparent w-28 num" />
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="名稱 例 台積電" className="px-2 py-1 rounded border line bg-transparent w-28" />
          <select value={market} onChange={(e) => setMarket(e.target.value as any)} className="px-2 py-1 rounded border line bg-[var(--panel)]">
            <option value="TWSE">TWSE 上市</option>
            <option value="TPEX">TPEx 上櫃</option>
          </select>
          <input value={sector} onChange={(e) => setSector(e.target.value)} placeholder="產業 例 半導體" className="px-2 py-1 rounded border line bg-transparent w-36" />
          <button disabled={busy} className="px-3 py-1 rounded border line bg-white/10 hover:bg-white/15 font-medium">
            {busy ? '處理中…' : '＋ 加入自選股 CSV'}
          </button>
          {msg && <span className="tone-negative text-[11px]">{msg}</span>}
        </form>

        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[11px]">
                <th className="text-left pb-1.5">代號 / 名稱</th>
                <th className="text-left pb-1.5 px-2">產業</th>
                <th className="text-right pb-1.5 px-2">價格</th>
                {th('change', '1D 漲跌')}
                {th('trend', '趨勢 Trend')}
                {th('momentum', '動能 Mom')}
                <th className="text-right pb-1.5 px-2">量能 Vol</th>
                {th('chip', '籌碼 Chip')}
                {th('rs', '相對強度 RS')}
                {th('fundamental', '基本面 Fund')}
                {th('score', '總分 Score')}
                <th className="text-center pb-1.5 px-2">Regime</th>
                <th className="text-right pb-1.5 px-2">60D</th>
                <th className="pb-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.symbol} onClick={() => onSelect(r.symbol)} className="border-t line hover:bg-white/[0.03] cursor-pointer">
                  <td className="py-2 pr-2 font-semibold">
                    <span className="num">{r.symbol}</span> {r.name}
                    <span className="ml-1"><QualityBadge q={r.quality} /></span>
                  </td>
                  <td className="py-2 px-2 muted text-[11px]">{r.sector}</td>
                  <td className="py-2 px-2 text-right num font-semibold">{fmtNum(r.price, 2)}</td>
                  <td className="py-2 px-2 text-right"><Value v={fmtPct(r.change)} tone={signTone(r.change)} /></td>
                  {scoreCell(r.trend)}
                  {scoreCell(r.momentum)}
                  {scoreCell(r.volume)}
                  {scoreCell(r.chip)}
                  {scoreCell(r.rs)}
                  {scoreCell(r.fundamental)}
                  {scoreCell(r.score)}
                  <td className="py-2 px-2 text-center">
                    <Pill tone={r.regime_tone ?? 'neutral'}>{r.regime_label ?? NA}</Pill>
                    {r.regime_prev && r.regime_prev !== r.regime && (
                      <span className="ml-1 text-[10px] tone-caution" title="近 5 日發生狀態改變">⚡</span>
                    )}
                  </td>
                  <td className="py-2 px-2 text-right"><Sparkline data={r.spark} width={80} height={22} /></td>
                  <td className="py-2 pl-2 text-right">
                    <button onClick={(ev) => remove(r.symbol, ev)} className="muted hover:tone-negative text-[11px] px-1" title="自 CSV 移除">✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
