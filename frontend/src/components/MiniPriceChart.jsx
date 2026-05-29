import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

function fmt(manwon) {
  if (manwon >= 10000) return `${(manwon / 10000).toFixed(1)}억`
  return `${(manwon / 1000).toFixed(0)}천`
}

function MiniTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-md border border-gray-100 bg-white p-1.5 shadow text-xs">
      <p className="text-gray-500">{label}</p>
      <p className="text-blue-600 font-bold">{fmt(d.avg_price)} <span className="text-gray-400 font-normal">({d.count}건)</span></p>
    </div>
  )
}

export default function MiniPriceChart({ trend, height = 90, title }) {
  if (!trend || trend.length === 0) {
    return (
      <div className="rounded-lg bg-gray-50 text-xs text-gray-400 text-center py-3">
        시세 데이터 없음
      </div>
    )
  }

  const prices = trend.map(d => d.avg_price).filter(p => p > 0)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const pad = (maxP - minP) * 0.1 || 5000

  const latest = trend[trend.length - 1]?.avg_price ?? 0
  const yearAgo = trend[Math.max(0, trend.length - 13)]?.avg_price ?? latest
  const diff = latest - yearAgo
  const diffPct = yearAgo ? ((diff / yearAgo) * 100).toFixed(1) : '0.0'
  const isUp = diff >= 0

  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-gray-500">{title || '최근 24개월 시세 (해당 법정동)'}</span>
        <span className={`font-semibold ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
          {isUp ? '▲' : '▼'} {Math.abs(diff/10000).toFixed(1)}억 ({diffPct}%)
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={trend} margin={{ top: 2, right: 4, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="ym"
            tick={{ fontSize: 8, fill: '#9ca3af' }}
            tickLine={false}
            axisLine={false}
            interval={Math.floor(trend.length / 4)}
          />
          <YAxis
            domain={[minP - pad, maxP + pad]}
            tickFormatter={fmt}
            tick={{ fontSize: 8, fill: '#9ca3af' }}
            tickLine={false}
            axisLine={false}
            width={32}
          />
          <Tooltip content={<MiniTooltip />} />
          <Line type="monotone" dataKey="avg_price" stroke="#2563eb" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
