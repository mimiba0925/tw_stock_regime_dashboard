import { useState } from 'react'
import { useApi } from '../api'
import type { Tone } from '../format'
import { Card, ErrorBox, Loading, Pill } from './ui'

export function AlertsView({ onOpenStock }: { onOpenStock: (sym: string) => void }) {
  const { data, error, loading } = useApi('/api/alerts')
  const [cat, setCat] = useState<'all' | 'market' | 'sector' | 'stock'>('all')

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />

  const list = (data?.alerts ?? []).filter((a: any) => cat === 'all' || a.category === cat)

  return (
    <Card
      title="警示中心 Alert Center（背離偵測 + Regime Change）"
      question="大盤、類股與自選股有哪些結構改變、突破或量價/廣度/法人背離？"
      right={
        <div className="flex gap-1">
          {([
            ['all', '全部'],
            ['market', '大盤 Market'],
            ['sector', '類股 Sector'],
            ['stock', '個股 Stock'],
          ] as const).map(([k, lab]) => (
            <button key={k} onClick={() => setCat(k)} className={`px-2 py-0.5 rounded text-[11px] border line ${cat === k ? 'bg-white/10 font-semibold' : 'muted'}`}>
              {lab}
            </button>
          ))}
        </div>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {list.map((a: any, i: number) => {
          const tone: Tone = a.severity === 'high' ? 'negative' : a.severity === 'medium' ? 'caution' : 'positive'
          return (
            <div
              key={i}
              onClick={() => a.category === 'stock' && onOpenStock(a.symbol)}
              className={`p-3 rounded border line flex flex-col gap-1.5 ${a.category === 'stock' ? 'cursor-pointer hover:bg-white/[0.03]' : ''}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span>{a.severity === 'high' ? '🔴' : a.severity === 'medium' ? '🟡' : '🟢'}</span>
                  <span className={`font-bold text-[13px] tone-${tone}`}>{a.title}</span>
                </div>
                <div className="flex items-center gap-1">
                  <Pill tone={tone}>{a.severity.toUpperCase()}</Pill>
                  <Pill tone="neutral">{a.symbol}</Pill>
                  <span className="text-[11px] muted num">{a.time}</span>
                </div>
              </div>
              <div className="text-[12px]">{a.reason}</div>
              {a.metrics?.length > 0 && (
                <div className="flex flex-wrap gap-2 text-[11px] num">
                  {a.metrics.map((m: any, j: number) => (
                    <span key={j} className="px-2 py-0.5 rounded bg-white/5 border line">
                      {m.label}：{m.from} → {m.to}
                    </span>
                  ))}
                </div>
              )}
              {a.conclusion && <div className="text-[11px] muted">結論：{a.conclusion}</div>}
            </div>
          )
        })}
        {!list.length && <div className="muted p-4 text-[12px]">此分類目前無警示。</div>}
      </div>
    </Card>
  )
}
