import { useState } from 'react'
import { useApi } from '../api'
import {
  FLOW_STATE, fmtNum, fmtPct, fmtYi, isNum, NA, SCORE_NAME, scoreTone, signTone, STATE_LABEL, type Tone,
} from '../format'
import { MultiLineChart, PriceChart, SectorTreemap } from './Charts'
import { TimeDimensionRow, TimeTableHeader } from './TimeDimension'
import { Bars, Card, ErrorBox, Gauge, Loading, Pill, ScoreBar, Sparkline, Value } from './ui'

export function MarketDashboard({ onOpenStock, onOpenTab }: { onOpenStock: (sym: string) => void; onOpenTab: (t: string) => void }) {
  const sum = useApi('/api/market/summary')
  const trend = useApi('/api/market/trend')
  const breadth = useApi('/api/market/breadth')
  const flow = useApi('/api/market/flow')
  const liq = useApi('/api/market/liquidity')
  const risk = useApi('/api/market/risk')
  const sectors = useApi('/api/sectors')
  const watch = useApi('/api/stocks/watchlist')
  const alerts = useApi('/api/alerts')

  const [idxTab, setIdxTab] = useState<'taiex' | 'otc'>('taiex')
  const [secPeriod, setSecPeriod] = useState<'1' | '5' | '20' | '60'>('5')
  const [secSort, setSecSort] = useState<'strong' | 'weak' | 'improving' | 'deteriorating'>('strong')
  const [showLayer2, setShowLayer2] = useState(false)

  if (sum.loading && !sum.data) return <Loading />
  if (sum.error) return <ErrorBox error={sum.error} />
  const S = sum.data
  if (!S) return null

  const reg = S.regime ?? {}
  const subs = S.subscores ?? {}
  const T = trend.data?.[idxTab]
  const B = breadth.data
  const F = flow.data
  const L = liq.data
  const R = risk.data
  const SecList = (sectors.data?.sectors ?? []) as any[]
  const sortedSectors = [...SecList].sort((a, b) => {
    if (secSort === 'strong') return (b.relative_strength?.[secPeriod] ?? -9) - (a.relative_strength?.[secPeriod] ?? -9)
    if (secSort === 'weak') return (a.relative_strength?.[secPeriod] ?? 9) - (b.relative_strength?.[secPeriod] ?? 9)
    if (secSort === 'improving') return (b.momentum_shift ?? -9) - (a.momentum_shift ?? -9)
    return (a.momentum_shift ?? 9) - (b.momentum_shift ?? 9)
  })

  return (
    <div className="flex flex-col gap-3">
      {/* 1 & 2. MARKET REGIME + MARKET SCORE + 30 秒十問快答 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <Card title="1. MARKET REGIME 市場狀態" question="現在台股是強還是弱？處於什麼 Regime？" className="lg:col-span-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <span className={`inline-block w-3 h-3 rounded-full bg-tone-${reg.tone ?? 'neutral'}`} style={{ background: reg.tone === 'positive' ? '#22a06b' : reg.tone === 'negative' ? '#e5484d' : reg.tone === 'caution' ? '#d4a72c' : '#8b949e' }} />
                <span className={`text-xl font-bold tone-${reg.tone ?? 'neutral'}`}>{reg.label ?? NA}</span>
                <Pill tone={reg.tone ?? 'neutral'}>{reg.regime}</Pill>
              </div>
              <ul className="text-[11px] muted list-disc list-inside space-y-0.5">
                {(reg.reasons ?? []).map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
              <div className="text-[10px] muted pt-1">{S.disclaimer}</div>
            </div>
            <Gauge v={S.score} label="Market Score" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 pt-2 border-t line">
            {(['trend', 'breadth', 'momentum', 'liquidity', 'money_flow', 'risk'] as const).map((k) => (
              <ScoreBar key={k} label={SCORE_NAME[k]} v={subs[k]?.score} />
            ))}
          </div>

          {/* Matrix：近 15 日 Regime 狀態演進 */}
          {S.score_history?.length > 1 && (
            <div className="pt-2 border-t line">
              <div className="flex items-center justify-between text-[11px] muted mb-1">
                <span>近 {S.score_history.length} 交易日 Regime 演進（左舊 → 右新）</span>
                <span className="num">5D Score Δ: {isNum(S.score_history.at(-1)?.score) && isNum(S.score_history.at(-6)?.score) ? (S.score_history.at(-1).score - S.score_history.at(-6).score).toFixed(1) : NA}</span>
              </div>
              <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${S.score_history.length}, minmax(0, 1fr))` }}>
                {S.score_history.map((h: any) => {
                  const t = scoreTone(h.score)
                  return (
                    <div key={h.date} title={`${h.date}｜Score ${h.score ?? 'N/A'}｜${h.regime}`} className={`h-4 rounded-sm bg-tone-${t} flex items-center justify-center text-[9px] num tone-${t}`}>
                      {isNum(h.score) ? Math.round(h.score) : ''}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </Card>

        {/* 30 秒 10 問快答 */}
        <Card
          title="30 秒市場狀態判讀（State + Change + Trend + Acceleration）"
          question="打開首頁 30 秒內必須回答的 10 個核心問題"
          className="lg:col-span-7"
          right={<Pill tone="neutral">基準日 {S.as_of}</Pill>}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {(S.answers ?? []).map((x: { q: string; a: string; tone: Tone }, i: number) => (
              <div key={i} className="p-2 rounded border line flex flex-col justify-between gap-0.5">
                <div className="text-[11px] muted">{i + 1}. {x.q}</div>
                <div className={`text-[12px] font-semibold tone-${x.tone}`}>{x.a}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* 3 & 4. TAIEX / OTC + Market Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <Card
          title="3–4. 指數與趨勢結構（TAIEX / OTC）"
          question="趨勢正在變強還是變弱？價格與均線結構為 Bullish / Neutral / Bearish？"
          className="lg:col-span-8"
          right={
            <div className="flex items-center gap-1">
              {(['taiex', 'otc'] as const).map((k) => (
                <button key={k} onClick={() => setIdxTab(k)} className={`px-2 py-0.5 rounded text-[11px] border line ${idxTab === k ? 'bg-white/10 font-semibold' : 'muted'}`}>
                  {k === 'taiex' ? '加權指數 TAIEX' : '櫃買指數 OTC'}
                </button>
              ))}
              {trend.data?.state && <Pill tone={STATE_LABEL[trend.data.state]?.tone}>{STATE_LABEL[trend.data.state]?.text}</Pill>}
            </div>
          }
        >
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pb-2 border-b line">
            {(['taiex', 'otc'] as const).map((k) => {
              const b = S[k]
              const t = signTone(b?.chg_pct)
              return (
                <div key={k} className="p-2 rounded border line">
                  <div className="text-[11px] muted flex justify-between">
                    <span>{k === 'taiex' ? '加權指數' : '櫃買指數'}</span>
                    <span>{b?.as_of ?? ''}</span>
                  </div>
                  <div className="flex items-baseline gap-2 mt-0.5">
                    <span className="num text-base font-bold">{fmtNum(b?.close, 2)}</span>
                    <Value v={`${fmtNum(b?.chg, 2)} (${fmtPct(b?.chg_pct)})`} tone={t} className="text-[11px]" />
                  </div>
                  <div className="text-[10px] muted num mt-1">
                    5D {fmtPct(b?.pct_changes?.['5'], 1)} · 20D {fmtPct(b?.pct_changes?.['20'], 1)} · 60D {fmtPct(b?.pct_changes?.['60'], 1)}
                  </div>
                </div>
              )
            })}
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">距離均線 / 52W 高點</div>
              <div className="text-[11px] num space-y-0.5 mt-1">
                <div>距 MA20：<Value v={fmtPct(T?.dist_ma20)} tone={signTone(T?.dist_ma20)} /></div>
                <div>距 MA60：<Value v={fmtPct(T?.dist_ma60)} tone={signTone(T?.dist_ma60)} /></div>
                <div>距 52W 高：<Value v={fmtPct(T?.dist_52w_high)} tone={signTone(T?.dist_52w_high)} /></div>
              </div>
            </div>
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">均線排列檢核</div>
              <div className="space-y-1 mt-1">
                {(T?.checks ?? []).map((c: any) => (
                  <div key={c.label} className="flex items-center justify-between text-[11px]">
                    <span>{c.label}</span>
                    <Pill tone={STATE_LABEL[c.state]?.tone ?? 'neutral'}>{c.state === 'bullish' ? 'Bullish' : c.state === 'bearish' ? 'Bearish' : 'Neutral'}</Pill>
                  </div>
                ))}
              </div>
            </div>
          </div>
          {T?.chart && <PriceChart candles={T.chart.candles} close={T.chart.close} ma20={T.chart.ma20} ma60={T.chart.ma60} ma120={T.chart.ma120} ma240={T.chart.ma240} height={240} />}
        </Card>

        {/* 9. Watchlist & Market Alerts */}
        <Card
          title="9. 異常與狀態改變警示（Divergence & Regime Change）"
          question="哪些指標出現背離或 Regime Change？"
          className="lg:col-span-4"
          right={<button onClick={() => onOpenTab('alerts')} className="text-[11px] underline muted">全部警示 ({alerts.data?.alerts?.length ?? 0})</button>}
        >
          <div className="flex flex-col gap-2 max-h-[340px] overflow-y-auto pr-1">
            {(alerts.data?.alerts ?? []).slice(0, 8).map((a: any, i: number) => {
              const tone: Tone = a.severity === 'high' ? 'negative' : a.severity === 'medium' ? 'caution' : 'positive'
              return (
                <div key={i} className="p-2 rounded border line flex flex-col gap-1" onClick={() => a.category === 'stock' && onOpenStock(a.symbol)}>
                  <div className="flex items-center justify-between gap-1">
                    <span className={`font-semibold text-[12px] tone-${tone}`}>
                      {a.severity === 'high' ? '🔴' : a.severity === 'medium' ? '🟡' : '🟢'} {a.title}
                    </span>
                    <Pill tone={tone}>{a.category.toUpperCase()}</Pill>
                  </div>
                  <div className="text-[11px] muted">{a.reason}</div>
                  {a.metrics?.length > 0 && (
                    <div className="flex flex-wrap gap-2 text-[11px] num">
                      {a.metrics.map((m: any, j: number) => <span key={j} className="px-1.5 py-0.5 rounded bg-white/5">{m.label}: {m.from} → {m.to}</span>)}
                    </div>
                  )}
                  {a.conclusion && <div className="text-[11px] italic muted">結論：{a.conclusion}</div>}
                </div>
              )
            })}
            {!alerts.data?.alerts?.length && <div className="muted text-[12px] p-3">目前未偵測到顯著背離或 Regime Change。</div>}
          </div>
        </Card>
      </div>

      {/* 5, 6, 7. Breadth + Money Flow + Liquidity */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <Card
          title="5. 市場廣度 Market Breadth"
          question="市場廣度支持指數嗎？"
          className="lg:col-span-6"
          right={B?.state && <Pill tone={STATE_LABEL[B.state]?.tone}>{STATE_LABEL[B.state]?.text}</Pill>}
          subtitle={B?.note}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <TimeTableHeader />
              <tbody>
                <TimeDimensionRow label="站上 MA20 比例" m={B?.metrics?.above_ma20} kind="pct" />
                <TimeDimensionRow label="站上 MA60 比例" m={B?.metrics?.above_ma60} kind="pct" />
                <TimeDimensionRow label="站上 MA120 比例" m={B?.metrics?.above_ma120} kind="pct" />
                <TimeDimensionRow label="上漲家數" m={B?.metrics?.advance} kind="int" />
                <TimeDimensionRow label="下跌家數" m={B?.metrics?.decline} kind="int" />
                <TimeDimensionRow label="漲跌家數比 A/D" m={B?.metrics?.ad_ratio} kind="num" />
                <TimeDimensionRow label="上漲成交額佔比" m={B?.metrics?.ad_volume} kind="pct" />
                <TimeDimensionRow label="52W 新高家數" m={B?.metrics?.new_high} kind="int" />
                <TimeDimensionRow label="52W 新低家數" m={B?.metrics?.new_low} kind="int" />
              </tbody>
            </table>
          </div>
        </Card>

        <div className="lg:col-span-6 flex flex-col gap-3">
          {/* 6. Money Flow */}
          <Card
            title="6. 三大法人資金流向 Money Flow"
            question="外資 / 投信正在買還是賣？買超是在擴大還是縮小？"
            right={
              F?.progress?.running
                ? <Pill tone="caution">歷史回補中 {F.progress.market?.[0]}/{F.progress.market?.[1]}</Pill>
                : <Pill tone={scoreTone(F?.score?.score)}>Flow Score {F?.score?.score ?? NA}</Pill>
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <TimeTableHeader isSum />
                <tbody>
                  {(['foreign', 'trust', 'dealer', 'total'] as const).map((k) => {
                    const m = F?.flows?.[k]
                    return <TimeDimensionRow key={k} label={m?.label ?? k} m={m} kind="yi" changeMode="sum" />
                  })}
                </tbody>
              </table>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
              {(['foreign', 'trust', 'dealer', 'total'] as const).map((k) => {
                const m = F?.flows?.[k]
                const fs = FLOW_STATE[m?.flow_state ?? 'N/A'] ?? FLOW_STATE['N/A']
                return (
                  <div key={k} className="p-1.5 rounded border line">
                    <div className="flex items-center justify-between text-[11px] mb-1">
                      <span className="font-medium">{m?.label ?? k}</span>
                      <Pill tone={fs.tone}>{fs.text}</Pill>
                    </div>
                    <Bars data={m?.bars ?? []} height={44} fmt={(v) => fmtYi(v)} />
                  </div>
                )
              })}
            </div>
          </Card>

          {/* 7. Liquidity */}
          <Card
            title="7. 量能與價量關係 Liquidity / Volume"
            question="成交量是在支持還是背離價格？"
            right={L?.pv_state && <Pill tone={L.pv_state.tone}>{L.pv_state.label}</Pill>}
          >
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px]">
              <div className="p-2 rounded border line">
                <div className="text-[11px] muted">今日成交額 / MA20</div>
                <div className="num font-bold text-sm mt-0.5">{fmtYi(L?.turnover?.current, false)}</div>
                <div className="text-[11px] muted num">MA20 比：{fmtNum(L?.ratio_ma20, 2)}x（{L?.level === 'high' ? '高量' : L?.level === 'low' ? '低量' : '常態量'}）</div>
              </div>
              <div className="p-2 rounded border line">
                <div className="text-[11px] muted">5D / 20D 均量</div>
                <div className="num text-[12px] mt-0.5">5D：{fmtYi(L?.avg5, false)}</div>
                <div className="num text-[12px]">20D：{fmtYi(L?.avg20, false)}</div>
              </div>
              <div className="p-2 rounded border line">
                <div className="text-[11px] muted">成交量歷史百分位</div>
                <div className="num text-[11px] mt-0.5">
                  20D P{L?.percentiles?.['20']?.toFixed(0) ?? NA} · 60D P{L?.percentiles?.['60']?.toFixed(0) ?? NA} · 250D P{L?.percentiles?.['250']?.toFixed(0) ?? NA}
                </div>
                <div className="text-[11px] muted num mt-0.5">上漲量佔比：{fmtPct(L?.up_volume_ratio, 0, false)}</div>
              </div>
              {/* 價量四象限視覺化 */}
              <div className="p-2 rounded border line">
                <div className="text-[11px] muted mb-1">價量四象限（5D）</div>
                <div className="grid grid-cols-2 gap-1 text-[10px]">
                  {[
                    ['up_up', '價↑ 量↑', 'positive'],
                    ['up_down', '價↑ 量↓', 'caution'],
                    ['down_up', '價↓ 量↑', 'negative'],
                    ['down_down', '價↓ 量↓', 'neutral'],
                  ].map(([k, txt, t]) => (
                    <div key={k} className={`px-1.5 py-0.5 rounded text-center border line ${L?.pv_state?.key === k ? `bg-tone-${t} tone-${t} font-bold` : 'muted opacity-60'}`}>
                      {txt}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* 8. Sector Rotation */}
      <Card
        title="8. 類股輪動 Sector Rotation（面積 = 成交額、顏色 = 報酬）"
        question="哪些類股正在領導？哪些正在轉弱？資金流向哪裡？"
        subtitle={sectors.data?.note}
        right={
          <div className="flex flex-wrap items-center gap-1">
            {(['1', '5', '20', '60'] as const).map((p) => (
              <button key={p} onClick={() => setSecPeriod(p)} className={`px-2 py-0.5 rounded text-[11px] border line ${secPeriod === p ? 'bg-white/10 font-semibold' : 'muted'}`}>
                {p}D
              </button>
            ))}
            <span className="muted mx-1">|</span>
            {([
              ['strong', '最強 Strongest'],
              ['weak', '最弱 Weakest'],
              ['improving', '轉強 Improving'],
              ['deteriorating', '轉弱 Deteriorating'],
            ] as const).map(([k, lab]) => (
              <button key={k} onClick={() => setSecSort(k)} className={`px-2 py-0.5 rounded text-[11px] border line ${secSort === k ? 'bg-white/10 font-semibold' : 'muted'}`}>
                {lab}
              </button>
            ))}
          </div>
        }
      >
        <SectorTreemap sectors={SecList} period={secPeriod} />
        <div className="overflow-x-auto pt-2">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[11px]">
                <th className="text-left pb-1">類股</th>
                <th className="text-right pb-1 px-2">1D</th>
                <th className="text-right pb-1 px-2">5D</th>
                <th className="text-right pb-1 px-2">20D</th>
                <th className="text-right pb-1 px-2">60D</th>
                <th className="text-right pb-1 px-2">相對大盤 RS (20D)</th>
                <th className="text-right pb-1 px-2">站上 MA20</th>
                <th className="text-right pb-1 px-2">5D 均成交</th>
                <th className="text-center pb-1 px-2">輪動方向</th>
                <th className="text-right pb-1 pl-2">60D</th>
              </tr>
            </thead>
            <tbody>
              {sortedSectors.map((s) => (
                <tr key={s.name} className="border-t line hover:bg-white/[0.02]">
                  <td className="py-1 font-medium">{s.name} <span className="muted text-[10px]">({s.count})</span></td>
                  {(['1', '5', '20', '60'] as const).map((w) => (
                    <td key={w} className="py-1 px-2 text-right"><Value v={fmtPct(s.returns?.[w], 1)} tone={signTone(s.returns?.[w])} /></td>
                  ))}
                  <td className="py-1 px-2 text-right"><Value v={fmtPct(s.relative_strength?.['20'], 1)} tone={signTone(s.relative_strength?.['20'])} /></td>
                  <td className="py-1 px-2 text-right num">{s.breadth?.toFixed(0) ?? NA}%</td>
                  <td className="py-1 px-2 text-right num">{fmtYi(s.turnover, false)}</td>
                  <td className="py-1 px-2 text-center">
                    <Pill tone={s.state === 'improving' ? 'positive' : s.state === 'deteriorating' ? 'negative' : 'neutral'}>
                      {s.state === 'improving' ? '↑ 轉強' : s.state === 'deteriorating' ? '↓ 轉弱' : '→ 持平'}
                    </Pill>
                  </td>
                  <td className="py-1 pl-2 text-right"><Sparkline data={s.spark} width={80} height={20} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 自選股快覽（首頁第 9 區延伸：點擊即進入個股頁） */}
      <Card
        title="自選股強度排行（點擊進入個股頁）"
        question="我的自選股是否強於大盤？目前處於什麼 Regime？"
        right={<button onClick={() => onOpenTab('watchlist')} className="text-[11px] underline muted">管理自選股 CSV →</button>}
      >
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {(watch.data?.rows ?? []).slice(0, 10).map((r: any) => (
            <div key={r.symbol} onClick={() => onOpenStock(r.symbol)} className="p-2 rounded border line cursor-pointer hover:bg-white/[0.03] flex flex-col justify-between gap-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold">{r.symbol} {r.name}</span>
                <Pill tone={r.regime_tone ?? 'neutral'}>{r.regime_label ?? NA}</Pill>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="num font-bold">{fmtNum(r.price, 2)}</span>
                <Value v={fmtPct(r.change)} tone={signTone(r.change)} className="text-[11px]" />
              </div>
              <div className="flex items-center justify-between text-[11px] muted num">
                <span>Score <b className={`tone-${scoreTone(r.score)}`}>{r.score?.toFixed(0) ?? NA}</b></span>
                <span>RS <b className={`tone-${scoreTone(r.rs)}`}>{r.rs?.toFixed(0) ?? NA}</b></span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* 第二層：詳細圖表與 External Risk Context */}
      <div>
        <button onClick={() => setShowLayer2((v) => !v)} className="panel px-3 py-1.5 text-[12px] muted hover:text-[var(--text)]">
          {showLayer2 ? '▼ 收合第二層詳細資料（廣度歷史圖 / 外部風險背景 External Risk Context）' : '▶ 展開第二層詳細資料（廣度歷史圖 / 外部風險背景 External Risk Context）'}
        </button>
      </div>

      {showLayer2 && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <Card title="廣度時間序列（站上 MA20 / MA60 比例）" question="廣度與指數在中期是否同步？" className="lg:col-span-6">
            {B?.chart && (
              <MultiLineChart
                series={[
                  { name: 'Above MA20 %', color: '#58a6ff', data: B.chart.above20 },
                  { name: 'Above MA60 %', color: '#22a06b', data: B.chart.above60 },
                ]}
                refLines={[50]}
                height={200}
              />
            )}
          </Card>

          <Card
            title="外部風險背景 External Risk Context"
            question="國際波動、匯率、美債與費半是否構成外部逆風？"
            subtitle={R?.note}
            className="lg:col-span-6"
            right={<Pill tone={scoreTone(R?.score?.score)}>Risk Score {R?.score?.score ?? NA}（越高越健康）</Pill>}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-[11px]">
                    <th className="text-left pb-1">指標</th>
                    <th className="text-right pb-1 px-2">最新</th>
                    <th className="text-right pb-1 px-2">1D</th>
                    <th className="text-right pb-1 px-2">5D</th>
                    <th className="text-right pb-1 px-2">20D</th>
                    <th className="text-right pb-1 px-2">250D 位置</th>
                    <th className="text-right pb-1 pl-2">60D</th>
                  </tr>
                </thead>
                <tbody>
                  {(R?.external ?? []).map((e: any) => (
                    <tr key={e.name} className="border-t line">
                      <td className="py-1 font-medium">{e.name}</td>
                      <td className="py-1 px-2 text-right num">{fmtNum(e.close, 2)}</td>
                      <td className="py-1 px-2 text-right"><Value v={fmtPct(e.chg1)} tone={signTone(e.chg1)} /></td>
                      <td className="py-1 px-2 text-right"><Value v={fmtPct(e.chg5)} tone={signTone(e.chg5)} /></td>
                      <td className="py-1 px-2 text-right"><Value v={fmtPct(e.chg20)} tone={signTone(e.chg20)} /></td>
                      <td className="py-1 px-2 text-right num">{isNum(e.percentile250) ? `P${e.percentile250.toFixed(0)}` : NA}</td>
                      <td className="py-1 pl-2 text-right"><Sparkline data={e.spark} width={76} height={18} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
