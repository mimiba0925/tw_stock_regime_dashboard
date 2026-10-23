import {
  fmtLots, fmtNum, fmtPct, fmtPP, fmtYi, isNum, NA, signTone, type Tone,
} from '../format'
import { Pill, QualityBadge, Sparkline, TrendTag, Value } from './ui'

export interface MetricSummary {
  current?: number | null
  as_of?: string
  source?: string
  unit?: string
  higher_is_better?: boolean
  quality?: string
  changes?: Record<string, number | null>
  pct_changes?: Record<string, number | null>
  sums?: Record<string, number | null>
  slopes?: Record<string, number | null>
  acceleration?: number | null
  percentiles?: Record<string, number | null>
  zscores?: Record<string, number | null>
  trend?: string
  accel?: string
  flow_state?: string
  sparkline?: (number | null)[]
}

function fmtByKind(v: number | null | undefined, kind: 'num' | 'pct' | 'yi' | 'lots' | 'int', sign = false) {
  if (!isNum(v)) return NA
  if (kind === 'yi') return fmtYi(v, sign)
  if (kind === 'lots') return fmtLots(v)
  if (kind === 'pct') return `${sign && v > 0 ? '+' : ''}${v.toFixed(1)}%`
  if (kind === 'int') return `${sign && v > 0 ? '+' : ''}${Math.round(v).toLocaleString('zh-TW')}`
  return `${sign && v > 0 ? '+' : ''}${fmtNum(v, 2)}`
}

/**
 * 時間維度橫列：Current | 1D | 5D | 20D | 60D | Trend | Acceleration | Percentile | Sparkline
 * 實踐核心設計原則：State + Change + Trend + Acceleration + Historical Position
 */
export function TimeDimensionRow({
  label, m, kind = 'num', changeMode = 'diff',
}: {
  label: string
  m?: MetricSummary
  kind?: 'num' | 'pct' | 'yi' | 'lots' | 'int'
  changeMode?: 'diff' | 'pct' | 'sum'
}) {
  if (!m || m.quality === 'missing') {
    return (
      <tr className="border-t line">
        <td className="py-1.5 pr-2 font-medium">{label}</td>
        <td colSpan={8} className="py-1.5 muted text-[11px]">N/A（Data unavailable）</td>
      </tr>
    )
  }
  const hib = m.higher_is_better !== false
  const toneOf = (v: number | null | undefined): Tone => {
    const t = signTone(v)
    if (hib || t === 'neutral') return t
    return t === 'positive' ? 'negative' : 'positive'
  }
  const cell = (w: string) => {
    if (changeMode === 'sum') {
      const v = m.sums?.[w]
      return <Value v={fmtByKind(v, kind, true)} tone={toneOf(v)} />
    }
    if (changeMode === 'pct') {
      const v = m.pct_changes?.[w]
      return <Value v={fmtPct(v, 1)} tone={toneOf(v)} />
    }
    const v = m.changes?.[w]
    return <Value v={kind === 'pct' ? `${fmtPP(v, 0)}%` : fmtByKind(v, kind, true)} tone={toneOf(v)} />
  }
  const p60 = m.percentiles?.['60'] ?? m.percentiles?.['250']
  return (
    <tr className="border-t line hover:bg-white/[0.02]">
      <td className="py-1.5 pr-2 font-medium">
        <div className="flex items-center gap-1.5">
          <span>{label}</span>
          <QualityBadge q={m.quality} source={m.source} />
        </div>
      </td>
      <td className="py-1.5 px-2 text-right font-semibold">
        <Value v={fmtByKind(m.current, kind, changeMode === 'sum')} tone={changeMode === 'sum' ? toneOf(m.current) : undefined} />
      </td>
      <td className="py-1.5 px-2 text-right">{cell('1')}</td>
      <td className="py-1.5 px-2 text-right">{cell('5')}</td>
      <td className="py-1.5 px-2 text-right">{cell('20')}</td>
      <td className="py-1.5 px-2 text-right">{cell('60')}</td>
      <td className="py-1.5 px-2 text-center"><TrendTag trend={m.trend} accel={m.accel} /></td>
      <td className="py-1.5 px-2 text-right">
        {isNum(p60) ? <Pill tone={p60 >= 80 ? 'positive' : p60 <= 20 ? 'negative' : 'neutral'}>P{p60.toFixed(0)}</Pill> : <span className="muted">{NA}</span>}
      </td>
      <td className="py-1.5 pl-2 text-right"><Sparkline data={m.sparkline} width={86} height={22} /></td>
    </tr>
  )
}

export function TimeTableHeader({ isSum = false }: { isSum?: boolean }) {
  return (
    <thead>
      <tr className="text-[11px]">
        <th className="text-left pb-1">指標</th>
        <th className="text-right pb-1 px-2">最新</th>
        <th className="text-right pb-1 px-2">{isSum ? '1D' : '1D Δ'}</th>
        <th className="text-right pb-1 px-2">{isSum ? '5D 累計' : '5D Δ'}</th>
        <th className="text-right pb-1 px-2">{isSum ? '20D 累計' : '20D Δ'}</th>
        <th className="text-right pb-1 px-2">{isSum ? '60D 累計' : '60D Δ'}</th>
        <th className="text-center pb-1 px-2">趨勢 / 加速度</th>
        <th className="text-right pb-1 px-2">歷史位置</th>
        <th className="text-right pb-1 pl-2">60D 走勢</th>
      </tr>
    </thead>
  )
}
