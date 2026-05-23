import { useEffect, useState } from 'react'
import axios from 'axios'
import PriceChart from './PriceChart'

function fmt(manwon) {
  if (!manwon) return '-'
  if (manwon >= 10000) return `${(manwon / 10000).toFixed(1)}억`
  return `${manwon.toLocaleString()}만`
}

function slopeLabel(m) {
  if (m == null) return '-'
  if (m <= 1)  return '평지'
  if (m < 5)   return `평지 (±${m}m)`
  if (m < 10)  return `약경사 (±${m}m)`
  if (m < 20)  return `경사 (±${m}m)`
  return `급경사 (±${m}m)`
}

export default function PropertyDetail({ property, onClose }) {
  const [trend, setTrend] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [isMock, setIsMock] = useState(false)
  const [tab, setTab] = useState('trend')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!property) return
    setLoading(true)

    Promise.all([
      axios.get(`/api/properties/${property.id}/trend`),
      axios.get(`/api/properties/${property.id}/transactions`),
    ]).then(([trendRes, txRes]) => {
      setTrend(trendRes.data.trend)
      setTransactions(txRes.data.items.slice(0, 30))
      setIsMock(trendRes.data.is_mock)
    }).catch(console.error)
      .finally(() => setLoading(false))
  }, [property?.id])

  if (!property) return null

  const age = new Date().getFullYear() - property.built_year

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-start justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{property.name}</h2>
            <p className="text-sm text-gray-500 mt-0.5">{property.address}</p>
          </div>
          <button onClick={onClose} className="ml-4 rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            ✕
          </button>
        </div>

        {/* 기본 정보 그리드 */}
        <div className="grid grid-cols-4 gap-3 border-b border-gray-100 px-6 py-4">
          <Stat label="실거래가" value={fmt(property.price)} highlight />
          <Stat label="면적" value={`${property.area_m2}㎡`} />
          <Stat label="세대수" value={`${property.units.toLocaleString()}세대`} />
          <Stat label="용적률" value={property.far > 0 ? `${property.far}%` : '-'} />
          <Stat label="경사도" value={slopeLabel(property.slope)} />
          <Stat label="연식" value={`${property.built_year}년 (${age}년)`} />
          <Stat label="역 도보" value={`${property.nearest_subway}역 ${property.walk_minutes}분`} />
          <Stat label="호선" value={property.subway_line} />
          <Stat label="층" value={`${property.floor}/${property.total_floors}층`} />
          <Stat label="버스" value={property.bus_routes.slice(0, 2).join(', ')} />
        </div>

        {/* 탭 */}
        <div className="flex border-b border-gray-100 px-6">
          {[
            { key: 'trend', label: '📈 시세 추이' },
            { key: 'tx', label: '📋 실거래 내역' },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`mr-4 border-b-2 py-3 text-sm font-medium transition-colors ${
                tab === t.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
          {isMock ? (
            <span className="ml-auto self-center rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-600">
              ⚠ 샘플 데이터
            </span>
          ) : (
            <span className="ml-auto self-center rounded-full bg-green-50 px-2 py-0.5 text-xs text-green-600">
              ✓ 국토부 실거래 데이터
            </span>
          )}
        </div>

        {/* 콘텐츠 */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-gray-400 text-sm">
              데이터 불러오는 중...
            </div>
          ) : tab === 'trend' ? (
            <div>
              <p className="mb-3 text-xs text-gray-400">최근 24개월 월별 평균 실거래가 (해당 법정동 기준)</p>
              <PriceChart trend={trend} currentPrice={property.price} />
              <p className="mt-2 text-xs text-gray-400">
                ━ 주황 점선: 현재 매물 가격 ({fmt(property.price)})
              </p>
            </div>
          ) : (
            <TransactionTable transactions={transactions} />
          )}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, highlight }) {
  return (
    <div className="rounded-xl bg-gray-50 p-3">
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`mt-0.5 font-semibold ${highlight ? 'text-blue-600 text-base' : 'text-gray-800 text-sm'}`}>
        {value}
      </p>
    </div>
  )
}

function TransactionTable({ transactions }) {
  if (!transactions.length) {
    return <p className="text-sm text-center text-gray-400 py-8">거래 내역 없음</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-xs text-gray-400">
            <th className="pb-2 text-left font-medium">거래일</th>
            <th className="pb-2 text-right font-medium">거래가</th>
            <th className="pb-2 text-right font-medium">면적</th>
            <th className="pb-2 text-right font-medium">층</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx, i) => (
            <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
              <td className="py-2 text-gray-600">
                {tx.year}.{String(tx.month).padStart(2, '0')}.{String(tx.day).padStart(2, '0')}
              </td>
              <td className="py-2 text-right font-semibold text-blue-600">
                {(tx.price / 10000).toFixed(1)}억
              </td>
              <td className="py-2 text-right text-gray-500">{tx.area_m2}㎡</td>
              <td className="py-2 text-right text-gray-500">{tx.floor}층</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
