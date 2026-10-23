// 格式化與顏色語意（全站共用，確保語意一致）
export type Tone = 'positive' | 'negative' | 'caution' | 'neutral'

export const NA = 'N/A'

export function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (!isNum(v)) return NA
  return v.toLocaleString('zh-TW', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function fmtPct(v: number | null | undefined, digits = 2, sign = true): string {
  if (!isNum(v)) return NA
  const s = (v * 100).toFixed(digits)
  return `${sign && v > 0 ? '+' : ''}${s}%`
}

export function fmtPP(v: number | null | undefined, digits = 1): string {
  if (!isNum(v)) return NA
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)}`
}

/** 金額：元 → 億 */
export function fmtYi(v: number | null | undefined, sign = true): string {
  if (!isNum(v)) return NA
  const x = v / 1e8
  const s = Math.abs(x) >= 100 ? x.toFixed(0) : x.toFixed(1)
  return `${sign && x > 0 ? '+' : ''}${Number(s).toLocaleString('zh-TW')} 億`
}

export function fmtLots(v: number | null | undefined): string {
  if (!isNum(v)) return NA
  return `${v > 0 ? '+' : ''}${Math.round(v).toLocaleString('zh-TW')} 張`
}

export function signTone(v: number | null | undefined, flat = 0): Tone {
  if (!isNum(v)) return 'neutral'
  return v > flat ? 'positive' : v < -flat ? 'negative' : 'neutral'
}

export function scoreTone(v: number | null | undefined): Tone {
  if (!isNum(v)) return 'neutral'
  if (v >= 60) return 'positive'
  if (v <= 40) return 'negative'
  return 'caution'
}

export const TONE_HEX: Record<Tone, string> = {
  positive: '#22a06b',
  negative: '#e5484d',
  caution: '#d4a72c',
  neutral: '#8b949e',
}

export const TREND_LABEL: Record<string, { text: string; arrow: string; tone: Tone }> = {
  improving: { text: '改善', arrow: '↑', tone: 'positive' },
  deteriorating: { text: '惡化', arrow: '↓', tone: 'negative' },
  neutral: { text: '持平', arrow: '→', tone: 'neutral' },
  'N/A': { text: NA, arrow: '', tone: 'neutral' },
}

export const ACCEL_LABEL: Record<string, { text: string; arrow: string; tone: Tone }> = {
  accelerating: { text: '加速', arrow: '↑↑', tone: 'positive' },
  decelerating: { text: '減速', arrow: '↓↓', tone: 'negative' },
  stable: { text: '穩定', arrow: '→', tone: 'neutral' },
  'N/A': { text: NA, arrow: '', tone: 'neutral' },
}

export const STATE_LABEL: Record<string, { text: string; tone: Tone }> = {
  bullish: { text: '偏多 Bullish', tone: 'positive' },
  bearish: { text: '偏空 Bearish', tone: 'negative' },
  neutral: { text: '中性 Neutral', tone: 'neutral' },
  improving: { text: '廣度改善', tone: 'positive' },
  deteriorating: { text: '廣度惡化', tone: 'negative' },
  'N/A': { text: NA, tone: 'neutral' },
}

export const FLOW_STATE: Record<string, { text: string; tone: Tone }> = {
  increasing_buying: { text: '買超擴大', tone: 'positive' },
  decreasing_buying: { text: '買超縮小', tone: 'caution' },
  increasing_selling: { text: '賣超擴大', tone: 'negative' },
  decreasing_selling: { text: '賣超縮小', tone: 'caution' },
  'N/A': { text: NA, tone: 'neutral' },
}

export const QUALITY_LABEL: Record<string, { text: string; tone: Tone }> = {
  available: { text: '即時/最新', tone: 'positive' },
  estimated: { text: '估計值', tone: 'caution' },
  stale: { text: '資料過期', tone: 'caution' },
  missing: { text: '資料不可用', tone: 'negative' },
}

export const SCORE_NAME: Record<string, string> = {
  trend: '趨勢 Trend',
  breadth: '廣度 Breadth',
  momentum: '動能 Momentum',
  liquidity: '量能 Liquidity',
  money_flow: '資金 Money Flow',
  risk: '風險 Risk',
  volume: '量能 Volume',
  institutional: '籌碼 Chip',
  relative_strength: '相對強度 RS',
  fundamental: '基本面',
}
