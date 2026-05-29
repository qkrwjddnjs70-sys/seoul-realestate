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

export default function PropertyDetail({ property: initialProperty, onClose }) {
  // 수동 입력으로 갱신될 수 있어 local state로 관리
  const [property, setProperty] = useState(initialProperty)
  useEffect(() => { setProperty(initialProperty) }, [initialProperty?.id])

  const [trend, setTrend] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [isMock, setIsMock] = useState(false)
  const [tab, setTab] = useState('trend')
  const [loading, setLoading] = useState(true)
  const [listings, setListings] = useState(null)
  const [listingsLoading, setListingsLoading] = useState(false)
  const [editFar, setEditFar] = useState(false)
  const [farInput, setFarInput] = useState('')
  const [savingFar, setSavingFar] = useState(false)

  async function saveFar() {
    const v = parseFloat(farInput)
    if (!v || v < 50 || v > 1500) {
      alert('용적률은 50~1500 사이로 입력하세요 (단위: %)')
      return
    }
    setSavingFar(true)
    try {
      const r = await axios.patch(`/api/properties/${property.id}/manual`, { far: v })
      setProperty(r.data)
      setEditFar(false)
    } catch (e) {
      alert('저장 실패: ' + e.message)
    } finally {
      setSavingFar(false)
    }
  }

  useEffect(() => {
    if (!property) return
    setLoading(true)
    setListings(null); setListingsLoading(true)

    Promise.all([
      axios.get(`/api/properties/${property.id}/trend`),
      axios.get(`/api/properties/${property.id}/transactions`),
    ]).then(([trendRes, txRes]) => {
      setTrend(trendRes.data.trend)
      setTransactions(txRes.data.items.slice(0, 30))
      setIsMock(trendRes.data.is_mock)
    }).catch(console.error)
      .finally(() => setLoading(false))

    axios.get(`/api/listings/${property.id}`)
      .then(r => setListings(r.data))
      .catch(() => setListings({ available: false }))
      .finally(() => setListingsLoading(false))
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
          <div className="min-w-0">
            <h2 className="text-xl font-bold text-gray-900">{property.name}</h2>
            <p className="text-sm text-gray-500 mt-0.5">{property.address}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <a
                href={property.naver_id
                  ? `https://new.land.naver.com/complexes/${property.naver_id}?ms=${property.lat},${property.lng},17&a=APT:PRE:ABYG:JGC&e=RETAIL`
                  : `https://new.land.naver.com/complexes?ms=${property.lat},${property.lng},17&a=APT:PRE:ABYG:JGC&e=RETAIL`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md bg-green-600 hover:bg-green-700 px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition-colors"
                title={property.naver_id ? '네이버 부동산 단지 페이지 (매물 바로 보기)' : '네이버 부동산 지도'}
              >
                🏠 네이버 부동산{property.naver_id && ' (매물)'}
              </a>
              <a
                href={`https://map.naver.com/p/search/${encodeURIComponent(property.name + ' ' + property.address)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md bg-emerald-50 border border-emerald-200 hover:bg-emerald-100 text-emerald-700 px-2.5 py-1 text-xs font-semibold transition-colors"
                title="네이버 지도에서 위치 보기"
              >
                🗺️ 네이버 지도
              </a>
            </div>
          </div>
          <button onClick={onClose} className="ml-4 rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 shrink-0">
            ✕
          </button>
        </div>

        {/* 재건축 진행 단계 배지 */}
        {property.redev_stage && (() => {
          // detail 파싱: "사업시행인가 / 2024.11 / 신길우성2차 (서울시 공식)"
          const parts = (property.redev_detail || '').split(' / ').map(s => s.trim())
          let date = '', zone = '', source = ''
          for (const part of parts) {
            if (/\(.*공식\)|\(.*\)$/.test(part)) {
              source = part.replace(/[()]/g, '').trim()
            } else if (/^\d{4}\.\d{1,2}/.test(part)) {
              date = part
            } else if (part !== property.redev_stage) {
              zone = part.replace(/\s*\(.*\)\s*$/, '').trim()
            }
          }
          // 단지명과 정비구역명이 다르면 통합 재건축 안내
          const aptCore = (property.name || '').replace(/\d+차$/, '').trim()
          const zoneCore = zone.replace(/\d+차$/, '').trim()
          const isMerged = zone && aptCore && zoneCore && aptCore === zoneCore && zone !== property.name
          return (
            <div className="border-b border-purple-100 bg-gradient-to-r from-purple-50 to-fuchsia-50 px-6 py-3">
              <div className="flex items-start gap-2">
                <svg viewBox="0 0 24 24" width="22" height="22" xmlns="http://www.w3.org/2000/svg"
                     className="shrink-0 mt-0.5"
                     style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.2))' }}>
                  <polygon points="12,2 15,9 22,9.5 17,14.5 18.5,22 12,18 5.5,22 7,14.5 2,9.5 9,9"
                           fill="#a855f7" stroke="#fff" strokeWidth="1.5" strokeLinejoin="round" />
                </svg>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-bold text-purple-700">재건축 진행</p>
                  <p className="text-sm font-semibold text-gray-900">
                    {property.redev_stage}{date && <span className="text-xs text-gray-500 font-normal ml-1.5">({date})</span>}
                  </p>
                  {zone && (
                    <p className="text-xs text-gray-600 mt-0.5">
                      <span className="text-gray-400">정비구역:</span> <b>{zone}</b>
                      {isMerged && <span className="ml-1.5 inline-block rounded bg-purple-100 text-purple-700 text-[10px] font-semibold px-1.5 py-0.5">통합 재건축</span>}
                    </p>
                  )}
                  {source && <p className="text-[10px] text-gray-400 mt-0.5">출처: {source}</p>}
                </div>
                {property.redev_updated && (
                  <p className="text-[10px] text-gray-400 shrink-0">업데이트 {property.redev_updated}</p>
                )}
              </div>
            </div>
          )
        })()}

        {/* 네이버 부동산 현재 매물 */}
        {(listingsLoading || listings?.available) && (
          <div className="border-b border-green-100 bg-green-50/50 px-6 py-3">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-xs font-bold text-green-700">🏠 네이버 부동산 — 현재 매물</p>
              {listings?.link && (
                <a href={listings.link} target="_blank" rel="noopener noreferrer"
                   className="text-[11px] text-green-700 hover:text-green-900 underline">전체 보기 →</a>
              )}
            </div>
            {listingsLoading && <p className="text-xs text-gray-400">조회 중...</p>}
            {!listingsLoading && listings?.available && (
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="rounded bg-white border border-green-200 px-2 py-1.5">
                  <p className="text-[10px] text-gray-500">매매</p>
                  <p className="font-bold text-gray-900">{listings.deal.count}건</p>
                  {listings.deal.count > 0 && (
                    <p className="text-[11px] text-gray-700">{listings.deal.minPrc}~{listings.deal.maxPrc}</p>
                  )}
                </div>
                <div className="rounded bg-white border border-green-200 px-2 py-1.5">
                  <p className="text-[10px] text-gray-500">전세</p>
                  <p className="font-bold text-gray-900">{listings.lease.count}건</p>
                  {listings.lease.count > 0 && (
                    <p className="text-[11px] text-gray-700">{listings.lease.minPrc}~{listings.lease.maxPrc}</p>
                  )}
                </div>
                <div className="rounded bg-white border border-green-200 px-2 py-1.5">
                  <p className="text-[10px] text-gray-500">월세</p>
                  <p className="font-bold text-gray-900">{listings.rent.count}건</p>
                  {listings.rent.count > 0 && (
                    <p className="text-[11px] text-gray-700">{listings.rent.minPrc}~{listings.rent.maxPrc}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 기본 정보 그리드 */}
        <div className="grid grid-cols-4 gap-3 border-b border-gray-100 px-6 py-4">
          <Stat label="실거래가" value={fmt(property.price)} highlight />
          <Stat label="면적" value={`${property.area_m2}㎡`} />
          <Stat label="세대수" value={`${property.units.toLocaleString()}세대`} />
          {/* 용적률 — 클릭 시 수동 입력 가능 */}
          <div className="rounded-lg bg-gray-50 px-3 py-2">
            <p className="text-[11px] text-gray-500 mb-0.5">용적률</p>
            {editFar ? (
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  value={farInput}
                  onChange={e => setFarInput(e.target.value)}
                  placeholder="예: 240"
                  className="w-14 rounded border border-blue-400 px-1 py-0.5 text-sm outline-none"
                  autoFocus
                  onKeyDown={e => e.key === 'Enter' && saveFar()}
                />
                <span className="text-xs text-gray-500">%</span>
                <button onClick={saveFar} disabled={savingFar}
                  className="text-xs text-blue-600 hover:text-blue-800 font-bold">
                  {savingFar ? '...' : '✓'}
                </button>
                <button onClick={() => setEditFar(false)}
                  className="text-xs text-gray-400 hover:text-gray-600">✕</button>
              </div>
            ) : (
              <button
                onClick={() => { setFarInput(property.far > 0 ? String(property.far) : ''); setEditFar(true) }}
                className="text-sm font-bold text-gray-900 hover:text-blue-600 flex items-center gap-1 group"
                title="용적률 수동 입력"
              >
                {property.far > 0 ? `${property.far}%` : '-'}
                <span className="text-[10px] text-gray-400 group-hover:text-blue-500">✎</span>
              </button>
            )}
          </div>
          <Stat
            label={`대지지분 (${property.area_m2}㎡)`}
            value={property.land_share > 0
              ? `${property.land_share.toFixed(1)}㎡ (${(property.land_share * 0.3025).toFixed(1)}평)`
              : '-'}
            highlight={property.land_share >= 30}
          />
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
