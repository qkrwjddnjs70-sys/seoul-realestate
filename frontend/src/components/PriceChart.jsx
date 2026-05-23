import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts'

function fmt(manwon) {
  if (manwon >= 10000) return `${(manwon / 10000).toFixed(1)}억`
  return `${(manwon / 1000).toFixed(0)}천`
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-3 shadow-lg text-xs">
      <p className="font-semibold text-gray-700 mb-1">{label}</p>
      <p className="text-blue-600 font-bold text-sm">{fmt(d.avg_price)}</p>
      <p className="text-gray-400">{d.count}건 거래</p>
    </div>
  )
}

export default function PriceChart({ trend, currentPrice }) {
  if (!trend || trend.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-gray-400 text-sm">
        시세 데이터 없음
      </div>
    )
  }

  const prices = trend.map(d => d.avg_price)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const pad = (maxP - minP) * 0.15 || 10000

  // 최근 가격 vs 1년 전 가격 비교
  const latest = trend[trend.length - 1]?.avg_price ?? 0
  const yearAgo = trend[Math.max(0, trend.length - 13)]?.avg_price ?? latest
  const diff = latest - yearAgo
  const diffPct = yearAgo ? ((diff / yearAgo) * 100).toFixed(1) : '0.0'
  const isUp = diff >= 0

  return (
    <div>
      {/* 요약 배지 */}
      <div className="mb-3 flex items-center gap-3">
        <div className="rounded-lg bg-blue-50 px-3 py-1.5">
          <p className="text-xs text-gray-500">최근 거래가</p>
          <p className="font-bold text-blue-600">{fmt(latest)}</p>
        </div>
        <div className={`rounded-lg px-3 py-1.5 ${isUp ? 'bg-red-50' : 'bg-blue-50'}`}>
          <p className="text-xs text-gray-500">1년 전 대비</p>
          <p className={`font-bold ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
            {isUp ? '▲' : '▼'} {Math.abs(diff / 10000).toFixed(1)}억 ({diffPct}%)
          </p>
        </div>
        <div className="rounded-lg bg-gray-50 px-3 py-1.5">
          <p className="text-xs text-gray-500">거래건수</p>
          <p className="font-bold text-gray-700">{trend.reduce((s, d) => s + d.count, 0)}건</p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={trend} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="ym"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            interval={Math.floor(trend.length / 6)}
          />
          <YAxis
            domain={[minP - pad, maxP + pad]}
            tickFormatter={fmt}
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            axisLine={false}
            width={50}
          />
          <Tooltip content={<CustomTooltip />} />
          {currentPrice && (
            <ReferenceLine
              y={currentPrice}
              stroke="#f59e0b"
              strokeDasharray="4 2"
              label={{ value: '매물가', position: 'insideTopRight', fontSize: 10, fill: '#f59e0b' }}
            />
          )}
          <Line
            type="monotone"
            dataKey="avg_price"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#2563eb' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
