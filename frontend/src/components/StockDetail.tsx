import { useApi } from '../api'
import {
  FLOW_STATE, fmtLots, fmtNum, fmtPct, isNum, NA, SCORE_NAME, scoreTone, signTone, STATE_LABEL,
} from '../format'
import { MultiLineChart, PriceChart, VolumeChart } from './Charts'
import { TimeDimensionRow, TimeTableHeader } from './TimeDimension'
import { Bars, Card, ErrorBox, Gauge, Loading, Pill, QualityBadge, ScoreBar, Value } from './ui'

export function StockDetail({ symbol, onSelect }: { symbol: string; onSelect: (s: string) => void }) {
  const watch = useApi('/api/stocks/watchlist')
  const info = useApi(`/api/stocks/${symbol}`, [symbol])
  const trend = useApi(`/api/stocks/${symbol}/trend`, [symbol])
  const flow = useApi(`/api/stocks/${symbol}/flow`, [symbol])
  const fund = useApi(`/api/stocks/${symbol}/fundamentals`, [symbol])

  if (info.loading && !info.data) return <Loading />
  if (info.error) return <ErrorBox error={info.error} />
  const D = info.data
  if (!D) return null

  const row = D.row ?? {}
  const reg = D.regime ?? {}
  const subs = D.subscores ?? {}
  const T = trend.data
  const F = flow.data
  const Fd = fund.data

  return (
    <div className="flex flex-col gap-3">
      {/* 自選股快速切換列 */}
      <div className="flex flex-wrap items-center gap-1">
        {(watch.data?.rows ?? []).map((r: any) => (
          <button
            key={r.symbol}
            onClick={() => onSelect(r.symbol)}
            className={`px-2.5 py-1 rounded text-[12px] border line flex items-center gap-1.5 ${r.symbol === symbol ? 'bg-white/10 font-bold' : 'muted hover:text-[var(--text)]'}`}
          >
            <span className="num">{r.symbol}</span>
            <span>{r.name}</span>
            <span className={`num text-[11px] tone-${scoreTone(r.score)}`}>{r.score?.toFixed(0) ?? '-'}</span>
          </button>
        ))}
      </div>

      {/* Header + Stock Score + Regime + Relative Strength */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <Card title="個股狀態與總分 Stock Regime & Score" question="這檔股票目前處於什麼 Regime？六大面向強弱如何？" className="lg:col-span-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold num">{row.symbol}</span>
                <span className="text-xl font-bold">{row.name}</span>
                <Pill tone="neutral">{row.sector} · {row.market}</Pill>
              </div>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="num text-2xl font-bold">{fmtNum(row.price, 2)}</span>
                <Value v={`${fmtNum(row.change_abs, 2)} (${fmtPct(row.change)})`} tone={signTone(row.change)} className="text-sm font-semibold" />
              </div>
              <div className="flex items-center gap-2 mt-2">
                <Pill tone={reg.tone ?? 'neutral'}>{reg.label} · {reg.regime}</Pill>
                {row.regime_prev && row.regime_prev !== row.regime && (
                  <Pill tone="caution">5D 前：{row.regime_prev}</Pill>
                )}
              </div>
              <ul className="text-[11px] muted list-disc list-inside mt-1">
                {(reg.reasons ?? []).map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            </div>
            <Gauge v={row.score} label="Stock Score" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 pt-2 border-t line">
            {(['trend', 'momentum', 'volume', 'institutional', 'relative_strength', 'fundamental'] as const).map((k) => (
              <ScoreBar key={k} label={SCORE_NAME[k]} v={subs[k]?.score} />
            ))}
          </div>
        </Card>

        {/* Relative Strength */}
        <Card
          title="相對強度 Relative Strength（個股核心）"
          question="這檔股票是否贏過大盤與所屬類股？"
          className="lg:col-span-6"
          right={<Pill tone={scoreTone(row.rs)}>RS Score {row.rs?.toFixed(0) ?? NA} / 100</Pill>}
        >
          <div className="grid grid-cols-5 gap-2 text-center">
            {(['1', '5', '20', '60', '120'] as const).map((w) => {
              const v = D.rs_market?.[w]
              return (
                <div key={w} className="p-2 rounded border line">
                  <div className="text-[11px] muted">vs 大盤 {w}D</div>
                  <Value v={fmtPct(v, 1)} tone={signTone(v)} className="text-sm font-bold" />
                </div>
              )
            })}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {(['5', '20', '60'] as const).map((w) => {
              const v = D.rs_sector?.[w]
              return (
                <div key={w} className="p-2 rounded border line">
                  <div className="text-[11px] muted">vs {row.sector} {w}D</div>
                  <Value v={fmtPct(v, 1)} tone={signTone(v)} className="text-sm font-semibold" />
                </div>
              )
            })}
          </div>
          {T?.relative?.length > 0 && (
            <div>
              <div className="text-[11px] muted mb-1">相對大盤強弱線（Stock / TAIEX，基期 = 100）</div>
              <MultiLineChart series={[{ name: 'RS Line', color: '#22a06b', data: T.relative }]} refLines={[100]} height={125} />
            </div>
          )}
        </Card>
      </div>

      {/* Price / Trend + Volume */}
      <Card
        title="價格、均線與成交量（Candlestick + MA20/60/120/240 + Volume）"
        question="價格位於均線之上或之下？均線斜率方向為何？"
        right={
          <div className="flex gap-1">
            {(T?.checks ?? []).map((c: any) => (
              <Pill key={c.label} tone={STATE_LABEL[c.state]?.tone ?? 'neutral'}>
                {c.label}: {c.state === 'bullish' ? 'Bullish' : c.state === 'bearish' ? 'Bearish' : 'Neutral'}
              </Pill>
            ))}
          </div>
        }
      >
        {T?.chart && (
          <>
            <PriceChart candles={T.chart.candles} close={T.chart.close} ma20={T.chart.ma20} ma60={T.chart.ma60} ma120={T.chart.ma120} ma240={T.chart.ma240} height={280} />
            <VolumeChart data={T.volume ?? []} height={90} />
          </>
        )}
        <div className="overflow-x-auto pt-2 border-t line">
          <table className="w-full text-[12px]">
            <TimeTableHeader />
            <tbody>
              <TimeDimensionRow label="收盤價（變動率）" m={T?.price_metric} kind="num" changeMode="pct" />
            </tbody>
          </table>
        </div>
      </Card>

      {/* Momentum (只用 RSI / MACD / ROC) + Volume metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <Card
          title="動能 Momentum（僅使用 RSI / MACD / ROC）"
          question="動能處於強勢區、中性區或超買超賣？"
          className="lg:col-span-6"
          right={<Pill tone={scoreTone(subs.momentum?.score)}>Momentum {subs.momentum?.score ?? NA}</Pill>}
        >
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">RSI (14)</div>
              <Value v={fmtNum(T?.momentum?.rsi_now, 1)} tone={scoreTone(T?.momentum?.rsi_now)} className="text-base font-bold" />
            </div>
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">ROC (20D)</div>
              <Value v={fmtPct(T?.momentum?.roc20_now, 1)} tone={signTone(T?.momentum?.roc20_now)} className="text-base font-bold" />
            </div>
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">MACD 柱狀</div>
              <Value v={fmtNum(T?.momentum?.macd_hist_now, 2)} tone={signTone(T?.momentum?.macd_hist_now)} className="text-base font-bold" />
            </div>
          </div>
          {T?.momentum && (
            <MultiLineChart
              series={[
                { name: 'RSI14', color: '#58a6ff', data: T.momentum.rsi },
              ]}
              refLines={[30, 50, 70]}
              height={150}
            />
          )}
        </Card>

        <Card
          title="量能與波動 Volume / OBV / ATR"
          question="OBV 是否與價格同步創高？成交量位於歷史何處？"
          className="lg:col-span-6"
          right={<Pill tone={scoreTone(subs.volume?.score)}>Volume {subs.volume?.score ?? NA}</Pill>}
        >
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">量 / MA20</div>
              <div className="num text-base font-bold">{fmtNum(T?.volume_metrics?.vol_ratio_ma20, 2)}x</div>
            </div>
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">ATR (14) / 價格比</div>
              <div className="num text-base font-bold">{fmtNum(T?.volume_metrics?.atr, 2)} ({fmtPct(T?.volume_metrics?.atr_pct, 1, false)})</div>
            </div>
            <div className="p-2 rounded border line">
              <div className="text-[11px] muted">量能百分位 20/60/250D</div>
              <div className="num text-[12px] font-semibold mt-1">
                P{T?.volume_metrics?.percentiles?.['20']?.toFixed(0) ?? NA} / P{T?.volume_metrics?.percentiles?.['60']?.toFixed(0) ?? NA} / P{T?.volume_metrics?.percentiles?.['250']?.toFixed(0) ?? NA}
              </div>
            </div>
          </div>
          {T?.volume_metrics?.obv && (
            <MultiLineChart series={[{ name: 'OBV', color: '#d4a72c', data: T.volume_metrics.obv }]} height={150} />
          )}
        </Card>
      </div>

      {/* Institutional + Fundamental */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <Card
          title="三大法人買賣超 Institutional Flow（張）"
          question="外資與投信在 1D / 5D / 20D / 60D 是在吸籌還是調節？"
          className="lg:col-span-7"
          right={<Pill tone={scoreTone(subs.institutional?.score)}>Chip {subs.institutional?.score ?? NA}</Pill>}
        >
          {!F?.available ? (
            <div className="muted text-[12px] p-4">{F?.reason ?? 'N/A（Data unavailable）'}</div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <TimeTableHeader isSum />
                  <tbody>
                    {(['foreign', 'trust', 'dealer'] as const).map((k) => (
                      <TimeDimensionRow key={k} label={F.flows[k]?.label ?? k} m={F.flows[k]} kind="lots" changeMode="sum" />
                    ))}
                    {F.positioning?.margin && (
                      <TimeDimensionRow label="融資餘額（張）" m={F.positioning.margin} kind="int" changeMode="diff" />
                    )}
                    {F.positioning?.short && (
                      <TimeDimensionRow label="融券餘額（張）" m={F.positioning.short} kind="int" changeMode="diff" />
                    )}
                  </tbody>
                </table>
              </div>
              <div className="grid grid-cols-3 gap-2 pt-1">
                {(['foreign', 'trust', 'dealer'] as const).map((k) => {
                  const m = F.flows[k]
                  const fs = FLOW_STATE[m?.flow_state ?? 'N/A'] ?? FLOW_STATE['N/A']
                  return (
                    <div key={k} className="p-1.5 rounded border line">
                      <div className="flex justify-between text-[11px] mb-1">
                        <span>{m?.label}</span>
                        <Pill tone={fs.tone}>{fs.text}</Pill>
                      </div>
                      <Bars data={m?.bars ?? []} height={44} fmt={(v) => fmtLots(v)} />
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </Card>

        <Card
          title="基本面與估值 Fundamental & Valuation"
          question="營收動能與估值在全市場處於什麼百分位？"
          className="lg:col-span-5"
          subtitle={Fd?.note}
          right={<Pill tone={scoreTone(subs.fundamental?.score)}>Fundamental {subs.fundamental?.score ?? NA}</Pill>}
        >
          <div className="text-[11px] muted">營收月份：{Fd?.revenue_month ?? NA}｜估值日期：{Fd?.as_of_valuation ?? NA}</div>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[11px]">
                <th className="text-left pb-1">項目</th>
                <th className="text-right pb-1 px-2">數值</th>
                <th className="text-right pb-1 px-2">市場百分位</th>
                <th className="text-right pb-1">資料品質</th>
              </tr>
            </thead>
            <tbody>
              {(Fd?.items ?? []).map((it: any) => (
                <tr key={it.key} className="border-t line">
                  <td className="py-1.5 font-medium">{it.label}</td>
                  <td className="py-1.5 px-2 text-right">
                    <Value v={isNum(it.value) ? `${fmtNum(it.value, 2)}${it.unit}` : NA} tone={it.unit === '%' ? signTone(it.value) : undefined} />
                  </td>
                  <td className="py-1.5 px-2 text-right num">
                    {isNum(it.market_percentile) ? `P${it.market_percentile.toFixed(0)}` : NA}
                  </td>
                  <td className="py-1.5 text-right"><QualityBadge q={it.quality} source="TWSE/TPEx OpenAPI" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  )
}
