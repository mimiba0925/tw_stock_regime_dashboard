import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
} from 'lightweight-charts'
import { fmtPct, fmtYi, isNum, TONE_HEX, type Tone } from '../format'

interface Point { time: string; value: number | null }
interface Candle { time: string; open: number | null; high: number | null; low: number | null; close: number | null }

/** TradingView Lightweight Charts 封裝（價格/均線/K線） */
export function PriceChart({
  candles, close, ma20, ma60, ma120, ma240, height = 270, mode = 'candles',
}: {
  candles?: Candle[]
  close?: Point[]
  ma20?: Point[]
  ma60?: Point[]
  ma120?: Point[]
  ma240?: Point[]
  height?: number
  mode?: 'candles' | 'line'
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const dark = document.documentElement.classList.contains('dark')
    const chart: IChartApi = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: dark ? '#8b949e' : '#667080',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: dark ? '#1f2630' : '#eef1f4' },
        horzLines: { color: dark ? '#1f2630' : '#eef1f4' },
      },
      rightPriceScale: { borderColor: dark ? '#262d36' : '#e3e6ea' },
      timeScale: { borderColor: dark ? '#262d36' : '#e3e6ea', timeVisible: false },
      crosshair: { mode: 0 },
    })

    if (mode === 'candles' && candles?.length) {
      const s = chart.addSeries(CandlestickSeries, {
        upColor: TONE_HEX.positive, downColor: TONE_HEX.negative,
        borderUpColor: TONE_HEX.positive, borderDownColor: TONE_HEX.negative,
        wickUpColor: TONE_HEX.positive, wickDownColor: TONE_HEX.negative,
      })
      s.setData(
        candles
          .filter((c) => isNum(c.open) && isNum(c.high) && isNum(c.low) && isNum(c.close))
          .map((c) => ({ time: c.time, open: c.open!, high: c.high!, low: c.low!, close: c.close! })),
      )
    } else if (close?.length) {
      const s = chart.addSeries(LineSeries, { color: dark ? '#e6edf3' : '#1c2128', lineWidth: 2, title: '收盤' })
      s.setData(close.filter((p) => isNum(p.value)).map((p) => ({ time: p.time, value: p.value! })))
    }

    const addMa = (pts: Point[] | undefined, color: string, title: string) => {
      if (!pts?.length) return
      const s = chart.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title })
      s.setData(pts.filter((p) => isNum(p.value)).map((p) => ({ time: p.time, value: p.value! })))
    }
    addMa(ma20, '#58a6ff', 'MA20')
    addMa(ma60, '#d4a72c', 'MA60')
    addMa(ma120, '#bc8cff', 'MA120')
    addMa(ma240, '#8b949e', 'MA240')

    chart.timeScale().fitContent()
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }))
    ro.observe(el)
    return () => { ro.disconnect(); chart.remove() }
  }, [candles, close, ma20, ma60, ma120, ma240, height, mode])

  return (
    <div>
      <div className="flex gap-3 text-[11px] muted mb-1">
        <span className="inline-flex items-center gap-1"><i className="w-2.5 h-0.5 bg-[#58a6ff] inline-block" />MA20</span>
        <span className="inline-flex items-center gap-1"><i className="w-2.5 h-0.5 bg-[#d4a72c] inline-block" />MA60</span>
        <span className="inline-flex items-center gap-1"><i className="w-2.5 h-0.5 bg-[#bc8cff] inline-block" />MA120</span>
        {ma240 && <span className="inline-flex items-center gap-1"><i className="w-2.5 h-0.5 bg-[#8b949e] inline-block" />MA240</span>}
      </div>
      <div ref={ref} className="w-full" />
    </div>
  )
}

/** 成交量柱狀圖（Lightweight Charts） */
export function VolumeChart({ data, height = 95 }: { data: { time: string; value: number | null; up?: boolean }[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !data?.length) return
    const dark = document.documentElement.classList.contains('dark')
    const chart = createChart(el, {
      height,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: dark ? '#8b949e' : '#667080', fontSize: 10 },
      grid: { vertLines: { visible: false }, horzLines: { color: dark ? '#1f2630' : '#eef1f4' } },
      rightPriceScale: { borderColor: dark ? '#262d36' : '#e3e6ea' },
      timeScale: { borderColor: dark ? '#262d36' : '#e3e6ea' },
    })
    const s = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } })
    s.setData(
      data.filter((d) => isNum(d.value)).map((d) => ({
        time: d.time, value: d.value!,
        color: d.up === false ? TONE_HEX.negative : d.up === true ? TONE_HEX.positive : TONE_HEX.neutral,
      })),
    )
    chart.timeScale().fitContent()
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }))
    ro.observe(el)
    return () => { ro.disconnect(); chart.remove() }
  }, [data, height])
  return <div ref={ref} className="w-full" />
}

/** 多條線比較圖（例如 Above MA20 / MA60、RSI、相對強度） */
export function MultiLineChart({
  series, height = 160, refLines = [],
}: {
  series: { name: string; color: string; data: Point[] }[]
  height?: number
  refLines?: number[]
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const dark = document.documentElement.classList.contains('dark')
    const chart = createChart(el, {
      height,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: dark ? '#8b949e' : '#667080', fontSize: 10 },
      grid: { vertLines: { color: dark ? '#1f2630' : '#eef1f4' }, horzLines: { color: dark ? '#1f2630' : '#eef1f4' } },
      rightPriceScale: { borderColor: dark ? '#262d36' : '#e3e6ea' },
      timeScale: { borderColor: dark ? '#262d36' : '#e3e6ea' },
    })
    series.forEach((sr) => {
      if (!sr.data?.length) return
      const l = chart.addSeries(LineSeries, { color: sr.color, lineWidth: 2, title: sr.name })
      const clean = sr.data.filter((p) => isNum(p.value)).map((p) => ({ time: p.time, value: p.value! }))
      l.setData(clean)
      refLines.forEach((rv) => l.createPriceLine({ price: rv, color: '#8b949e', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' }))
    })
    chart.timeScale().fitContent()
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }))
    ro.observe(el)
    return () => { ro.disconnect(); chart.remove() }
  }, [series, height, refLines])
  return <div ref={ref} className="w-full" />
}

/** Sector Treemap：面積 = 成交值、顏色 = 期間報酬率 */
export function SectorTreemap({
  sectors, period = '5', onSelect,
}: {
  sectors: { name: string; turnover: number | null; count: number; returns: Record<string, number | null>; relative_strength: Record<string, number | null>; breadth: number | null }[]
  period?: '1' | '5' | '20' | '60'
  onSelect?: (name: string) => void
}) {
  if (!sectors?.length) return <div className="muted text-[12px] p-4">無類股資料</div>
  const items = sectors
    .map((s) => ({ ...s, w: Math.max(s.turnover ?? 1e8, 1e8), ret: s.returns?.[period] ?? null }))
    .sort((a, b) => b.w - a.w)
  const total = items.reduce((a, b) => a + b.w, 0) || 1

  // Slice-and-dice 雙列配置：按權重分配寬度，穩定清楚
  const half = total * 0.55
  let acc = 0
  const row1: typeof items = [], row2: typeof items = []
  for (const it of items) {
    if (acc < half || row1.length === 0) { row1.push(it); acc += it.w } else row2.push(it)
  }
  const colorOf = (r: number | null): { bg: string; tone: Tone } => {
    if (!isNum(r)) return { bg: 'rgba(139,148,158,0.18)', tone: 'neutral' }
    const intensity = Math.min(Math.abs(r) / 0.06, 1) * 0.42 + 0.12
    if (r > 0.001) return { bg: `rgba(34,160,107,${intensity})`, tone: 'positive' }
    if (r < -0.001) return { bg: `rgba(229,72,77,${intensity})`, tone: 'negative' }
    return { bg: 'rgba(212,167,44,0.18)', tone: 'caution' }
  }
  const renderRow = (row: typeof items, h: string) => {
    const rt = row.reduce((a, b) => a + b.w, 0) || 1
    return (
      <div className={`flex gap-1 ${h}`}>
        {row.map((s) => {
          const c = colorOf(s.ret)
          return (
            <div
              key={s.name}
              style={{ flex: `${(s.w / rt) * 100} 1 0%`, background: c.bg }}
              onClick={() => onSelect?.(s.name)}
              className="rounded p-2 border line flex flex-col justify-between min-w-[68px] overflow-hidden cursor-pointer hover:opacity-90 transition"
              title={`${s.name}｜${period}D 報酬 ${fmtPct(s.ret)}｜RS ${fmtPct(s.relative_strength?.[period])}｜廣度 ${s.breadth?.toFixed(0) ?? 'N/A'}%｜5D均成交 ${fmtYi(s.turnover, false)}`}
            >
              <div className="font-semibold text-[12px] truncate">{s.name}</div>
              <div>
                <div className={`num text-[13px] font-bold tone-${c.tone}`}>{fmtPct(s.ret, 1)}</div>
                <div className="text-[10px] muted truncate">RS {fmtPct(s.relative_strength?.[period], 1)} · 廣度 {s.breadth?.toFixed(0) ?? '-'}%</div>
              </div>
            </div>
          )
        })}
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1">
      {renderRow(row1, 'h-24')}
      {row2.length > 0 && renderRow(row2, 'h-20')}
    </div>
  )
}
