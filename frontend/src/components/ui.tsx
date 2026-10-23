import type { ReactNode } from 'react'
import {
  ACCEL_LABEL, isNum, NA, QUALITY_LABEL, scoreTone, TONE_HEX, TREND_LABEL, type Tone,
} from '../format'

export function Card({ title, subtitle, right, children, className = '', question }: {
  title: ReactNode; subtitle?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; question?: string
}) {
  return (
    <section className={`panel p-3 flex flex-col gap-2 min-w-0 ${className}`}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[12px] font-semibold tracking-wide uppercase muted">{title}</h2>
          {question && <div className="text-[11px] muted opacity-80">❓ {question}</div>}
          {subtitle && <div className="text-[11px] muted">{subtitle}</div>}
        </div>
        {right}
      </header>
      {children}
    </section>
  )
}

export function Pill({ tone = 'neutral', children, className = '' }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-tone-${tone} tone-${tone} ${className}`}>{children}</span>
}

export function QualityBadge({ q, source }: { q?: string; source?: string }) {
  if (!q) return null
  const l = QUALITY_LABEL[q] ?? QUALITY_LABEL.missing
  if (q === 'available') return source ? <span className="text-[10px] muted" title={source}>{source}</span> : null
  return <span title={source}><Pill tone={l.tone}>{l.text}</Pill></span>
}

export function Value({ v, tone, className = '' }: { v: string; tone?: Tone; className?: string }) {
  return <span className={`num ${tone ? `tone-${tone}` : ''} ${v === NA ? 'muted' : ''} ${className}`} title={v === NA ? '資料不可用 Data unavailable' : undefined}>{v}</span>
}

export function TrendTag({ trend, accel }: { trend?: string; accel?: string }) {
  const t = TREND_LABEL[trend ?? 'N/A'] ?? TREND_LABEL['N/A']
  const a = ACCEL_LABEL[accel ?? 'N/A'] ?? ACCEL_LABEL['N/A']
  return (
    <span className="inline-flex gap-1">
      <Pill tone={t.tone}>{t.arrow} {t.text}</Pill>
      {accel && <Pill tone={a.tone}>{a.arrow} {a.text}</Pill>}
    </span>
  )
}

/** 0–100 分數條 */
export function ScoreBar({ label, v, onClick }: { label: string; v: number | null | undefined; onClick?: () => void }) {
  const tone = scoreTone(v)
  return (
    <div className={`grid grid-cols-[110px_1fr_34px] items-center gap-2 ${onClick ? 'cursor-pointer' : ''}`} onClick={onClick}>
      <span className="text-[12px] muted truncate">{label}</span>
      <div className="h-1.5 rounded bg-[var(--line)] overflow-hidden">
        {isNum(v) && <div className="h-full rounded" style={{ width: `${v}%`, background: TONE_HEX[tone] }} />}
      </div>
      <Value v={isNum(v) ? v.toFixed(0) : NA} tone={tone} className="text-right" />
    </div>
  )
}

/** 半圓 Gauge：回答「目前總分在 0–100 的哪裡」 */
export function Gauge({ v, size = 150, label }: { v: number | null | undefined; size?: number; label?: string }) {
  const r = size / 2 - 10
  const cx = size / 2
  const cy = size / 2
  const tone = scoreTone(v)
  const arc = (from: number, to: number) => {
    const a0 = Math.PI * (1 - from / 100)
    const a1 = Math.PI * (1 - to / 100)
    const x0 = cx + r * Math.cos(a0), y0 = cy - r * Math.sin(a0)
    const x1 = cx + r * Math.cos(a1), y1 = cy - r * Math.sin(a1)
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`
  }
  return (
    <svg width={size} height={size / 2 + 22} viewBox={`0 0 ${size} ${size / 2 + 22}`}>
      <path d={arc(0, 100)} stroke="var(--line)" strokeWidth={10} fill="none" strokeLinecap="round" />
      {[40, 60].map((t) => {
        const a = Math.PI * (1 - t / 100)
        return <line key={t} x1={cx + (r - 8) * Math.cos(a)} y1={cy - (r - 8) * Math.sin(a)} x2={cx + (r + 8) * Math.cos(a)} y2={cy - (r + 8) * Math.sin(a)} stroke="var(--muted)" strokeWidth={1} opacity={0.5} />
      })}
      {isNum(v) && <path d={arc(0, Math.max(0.5, v))} stroke={TONE_HEX[tone]} strokeWidth={10} fill="none" strokeLinecap="round" />}
      <text x={cx} y={cy - 4} textAnchor="middle" className="num" fontSize={size / 5} fontWeight={600} fill={isNum(v) ? TONE_HEX[tone] : 'var(--muted)'}>
        {isNum(v) ? v.toFixed(0) : NA}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fontSize={11} fill="var(--muted)">{label ?? '/ 100'}</text>
    </svg>
  )
}

/** Sparkline：時間變化 */
export function Sparkline({ data, width = 120, height = 28, tone, zero = false }: {
  data?: (number | null)[]; width?: number; height?: number; tone?: Tone; zero?: boolean
}) {
  const pts = (data ?? []).filter(isNum)
  if (pts.length < 2) return <span className="text-[10px] muted">N/A</span>
  let min = Math.min(...pts), max = Math.max(...pts)
  if (zero) { min = Math.min(min, 0); max = Math.max(max, 0) }
  const rng = max - min || 1
  const t: Tone = tone ?? (pts[pts.length - 1] >= pts[0] ? 'positive' : 'negative')
  const d = pts.map((p, i) => `${(i / (pts.length - 1)) * width},${height - ((p - min) / rng) * (height - 2) - 1}`).join(' ')
  const zy = height - ((0 - min) / rng) * (height - 2) - 1
  return (
    <svg width={width} height={height} className="overflow-visible">
      {zero && <line x1={0} x2={width} y1={zy} y2={zy} stroke="var(--muted)" strokeDasharray="2 2" opacity={0.5} />}
      <polyline points={d} fill="none" stroke={TONE_HEX[t]} strokeWidth={1.4} />
    </svg>
  )
}

/** 簡易長條圖（法人買賣超等）：回答「每日資金是流入還是流出」 */
export function Bars({ data, height = 70, fmt }: { data: { time: string; value: number | null }[]; height?: number; fmt?: (v: number) => string }) {
  const vals = data.map((d) => d.value).filter(isNum)
  if (!vals.length) return <div className="text-[11px] muted h-[40px] flex items-center">N/A — 資料不可用</div>
  const maxAbs = Math.max(...vals.map(Math.abs)) || 1
  const w = 100 / data.length
  const allPos = vals.every((v) => v >= 0)
  const mid = allPos ? height : height / 2
  return (
    <svg width="100%" height={height} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none">
      <line x1={0} x2={100} y1={mid} y2={mid} stroke="var(--line)" strokeWidth={0.5} vectorEffect="non-scaling-stroke" />
      {data.map((d, i) => {
        if (!isNum(d.value)) return null
        const h = (Math.abs(d.value) / maxAbs) * (allPos ? height : height / 2 - 1)
        const y = d.value >= 0 ? mid - h : mid
        return (
          <rect key={d.time} x={i * w + w * 0.15} width={w * 0.7} y={y} height={Math.max(h, 0.5)} fill={allPos ? TONE_HEX.neutral : d.value >= 0 ? TONE_HEX.positive : TONE_HEX.negative}>
            <title>{`${d.time}  ${fmt ? fmt(d.value) : d.value}`}</title>
          </rect>
        )
      })}
    </svg>
  )
}

export function Loading({ text = '資料載入中…' }: { text?: string }) {
  return <div className="muted text-[12px] p-6 animate-pulse">{text}（首次啟動需下載歷史資料，約 1–3 分鐘）</div>
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="panel p-4 tone-negative text-[12px]">⚠ {error}</div>
}
