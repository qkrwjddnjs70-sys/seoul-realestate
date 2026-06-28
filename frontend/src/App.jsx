import { useState, useCallback, useRef, useEffect } from 'react'
import FilterPanel, { HOJAE_STYLE, GU_LIST } from './components/FilterPanel'
import NaverMap from './components/NaverMap'
import PropertyDetail from './components/PropertyDetail'
import CompareModal from './components/CompareModal'
import AiFilterModal from './components/AiFilterModal'
import WelcomeModal from './components/WelcomeModal'
import UsageBadge from './components/UsageBadge'
import CaptureButtons from './components/CaptureButtons'
import MiniPriceChart from './components/MiniPriceChart'
import { useProperties } from './hooks/useProperties'

export default function App() {
  const [filters, setFilters] = useState({ lawdCds: ['11560', '11500'] })
  const [selectedProperty, setSelectedProperty] = useState(null)
  const [detailProperty, setDetailProperty] = useState(null)
  const [listOpen, setListOpen] = useState(true)
  const [mapBounds, setMapBounds] = useState(null)
  const [searchBounds, setSearchBounds] = useState(null)   // 수동 "현재 화면 검색" 결과
  const [compareOpen, setCompareOpen] = useState(false)
  const [hojaeOpen, setHojaeOpen] = useState(false)
  const [aiFilterOpen, setAiFilterOpen] = useState(false)
  const [usageRefresh, setUsageRefresh] = useState(0)
  const bumpUsage = useCallback(() => setUsageRefresh(k => k + 1), [])
  const [filterOpen, setFilterOpen] = useState(false)
  const [zoneQuery, setZoneQuery] = useState('')
  const [redevZones, setRedevZones] = useState([])
  const [showAllZones, setShowAllZones] = useState(false)
  const [nohu, setNohu] = useState({ on: false, candOn: false, grades: [], subtypes: [] })

  // "정비사업 보기" 토글 → 선택 구가 있으면 그 구만, 없으면 서울 전체
  useEffect(() => {
    if (!showAllZones) return
    let cancelled = false
    const guNames = (filters.lawdCds || [])
      .map(c => GU_LIST.find(g => g.lawd_cd === c)?.name)
      .filter(Boolean)
    ;(async () => {
      try {
        let zones = []
        if (guNames.length) {
          const results = await Promise.all(
            guNames.map(gu => fetch(`/api/redev-zones/all?gu=${encodeURIComponent(gu)}`).then(r => r.json()))
          )
          zones = results.flatMap(j => j.zones || [])
        } else {
          const j = await (await fetch('/api/redev-zones/all')).json()
          zones = j.zones || []
        }
        if (!cancelled) setRedevZones(zones)
      } catch { /* ignore */ }
    })()
    return () => { cancelled = true }
  }, [showAllZones, filters.lawdCds])

  function toggleAllZones(on) {
    setShowAllZones(on)
    if (!on) { setRedevZones([]); setZoneQuery('') }
  }

  async function searchZones() {
    const q = zoneQuery.trim()
    if (!q) { setRedevZones([]); return }
    try {
      const r = await fetch(`/api/redev-zones/search?q=${encodeURIComponent(q)}`)
      const j = await r.json()
      setRedevZones(j.zones || [])
      if (j.zones?.length) {
        // 첫 결과로 지도 이동
        const z = j.zones[0]
        mapRef.current?.flyTo(z.lat, z.lng, 15)
      } else {
        alert('해당 정비사업 구역을 찾지 못했습니다')
      }
    } catch {
      setRedevZones([])
    }
  }

  const { properties, total, loading } = useProperties(filters, mapBounds)

  // 하단 목록 = "현재 화면 검색" 버튼이 마지막으로 잡은 영역의 단지만
  const visibleProperties = searchBounds
    ? properties.filter(p =>
        p.lat >= searchBounds.south && p.lat <= searchBounds.north &&
        p.lng >= searchBounds.west  && p.lng <= searchBounds.east
      )
    : []

  // 첫 로드 시 자동으로 한 번 잡아주기
  useEffect(() => {
    if (mapBounds && !searchBounds) setSearchBounds(mapBounds)
  }, [mapBounds, searchBounds])

  function handleMarkerClick(property) {
    setSelectedProperty(prev => prev?.id === property.id ? null : property)
  }

  const handleBoundsChange = useCallback((bounds) => {
    setMapBounds(bounds)
  }, [])

  const mapRef = useRef(null)
  const handleGuSelect = useCallback((gu) => {
    // NaverMap 인스턴스에 직접 접근해서 해당 구 중심으로 이동
    if (mapRef.current) {
      mapRef.current.flyTo(gu.lat, gu.lng, 13)
    }
  }, [])

  // 단지명 검색 시 결과 위치로 자동 줌
  const lastFitName = useRef(null)
  useEffect(() => {
    const name = filters.aptName || ''
    if (!name) { lastFitName.current = null; return }
    if (!properties.length) return
    if (lastFitName.current === name) return
    lastFitName.current = name
    mapRef.current?.fitTo(properties)
  }, [filters.aptName, properties])

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gray-50">
      {/* 모바일 필터 드로어 배경 */}
      {filterOpen && (
        <div
          className="fixed inset-0 z-[2400] bg-black/40 md:hidden"
          onClick={() => setFilterOpen(false)}
        />
      )}
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        total={total}
        loading={loading}
        onGuSelect={(gu) => { handleGuSelect(gu); setFilterOpen(false) }}
        showAllZones={showAllZones}
        onToggleAllZones={toggleAllZones}
        zoneCount={redevZones.length}
        nohu={nohu}
        onNohuChange={setNohu}
        open={filterOpen}
        onClose={() => setFilterOpen(false)}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 지도 */}
        <div className="relative flex-1 overflow-hidden">
          <NaverMap
            ref={mapRef}
            properties={properties}
            redevZones={redevZones}
            selectedId={selectedProperty?.id ?? null}
            onMarkerClick={handleMarkerClick}
            onBoundsChange={handleBoundsChange}
            nohu={nohu}
            onNohuToggle={() => setNohu(n => ({ ...n, on: !n.on }))}
          />

          {/* 모바일 전용 필터 열기 버튼 */}
          <button
            onClick={() => setFilterOpen(true)}
            className="md:hidden absolute top-3 left-3 z-[1000] flex items-center gap-1.5 rounded-full bg-white shadow-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-800"
          >
            ☰ 필터
          </button>

          {/* 정비사업 구역 검색 (상단중앙, 모바일은 한 줄 아래) */}
          <div className="absolute top-16 md:top-3 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-1 rounded-full bg-white shadow-lg border border-gray-200 px-2 py-1 max-w-[calc(100vw-1.5rem)] md:max-w-none">
            <span className="text-sm pl-1">🏗️</span>
            <input
              type="text"
              value={zoneQuery}
              onChange={e => setZoneQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && searchZones()}
              placeholder="정비사업 검색 (예: 문래동4가)"
              className="w-36 sm:w-56 text-sm outline-none px-1 py-0.5 min-w-0"
            />
            {redevZones.length > 0 && (
              <button onClick={() => { setZoneQuery(''); setRedevZones([]) }}
                className="text-gray-300 hover:text-gray-500 text-sm px-1">✕</button>
            )}
            <button onClick={searchZones}
              className="rounded-full bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold px-3 py-1">
              검색
            </button>
          </div>
          {redevZones.length > 0 && (
            <div className="absolute top-28 md:top-14 left-1/2 -translate-x-1/2 z-[1000] rounded-full bg-purple-50 border border-purple-200 text-purple-700 text-xs px-3 py-1 shadow whitespace-nowrap">
              정비사업 {redevZones.length}곳 표시 중
            </div>
          )}

          {/* 마커 클릭 시 뜨는 정보 카드 */}
          {selectedProperty && (
            <MapInfoCard
              property={selectedProperty}
              onClose={() => setSelectedProperty(null)}
              onDetail={() => setDetailProperty(selectedProperty)}
            />
          )}

          {/* 좌하단 액션 버튼 — 한 줄로 묶음 (모바일은 짧은 라벨) */}
          <div className="absolute bottom-4 left-3 md:left-4 z-[1000] flex flex-wrap items-center gap-2 max-w-[62vw] md:max-w-none">
            <button
              onClick={() => mapBounds && setSearchBounds({ ...mapBounds })}
              className="flex items-center gap-1.5 rounded-full bg-blue-600 hover:bg-blue-700 px-3 py-2 text-xs sm:text-sm sm:px-4 font-semibold text-white shadow-lg transition-colors"
              title="현재 보이는 화면의 단지를 목록에 표시"
            >
              🔍 <span className="md:hidden">검색</span><span className="hidden md:inline">현재 화면 검색</span>
            </button>
            <button
              onClick={() => setAiFilterOpen(true)}
              className="flex items-center gap-1.5 rounded-full bg-purple-600 hover:bg-purple-700 px-3 py-2 text-xs sm:text-sm sm:px-4 font-semibold text-white shadow-lg transition-colors"
            >
              🤖 <span className="md:hidden">AI분석</span><span className="hidden md:inline">종합 AI 분석</span>
            </button>
            <button
              onClick={() => setCompareOpen(true)}
              className="flex items-center gap-1.5 rounded-full bg-indigo-600 hover:bg-indigo-700 px-3 py-2 text-xs sm:text-sm sm:px-4 font-semibold text-white shadow-lg transition-colors"
            >
              ⚖️ <span className="md:hidden">비교</span><span className="hidden md:inline">단지·지역 비교</span>
            </button>
            {/* 호재 검색 — 단지 선택 시만 활성 */}
            <button
              onClick={() => selectedProperty && setHojaeOpen(true)}
              disabled={!selectedProperty}
              title={selectedProperty ? '선택한 단지의 호재 검색' : '먼저 단지를 선택하세요'}
              className={`flex items-center gap-1.5 rounded-full px-3 py-2 text-xs sm:text-sm sm:px-4 font-semibold text-white shadow-lg transition-colors ${
                selectedProperty
                  ? 'bg-emerald-600 hover:bg-emerald-700'
                  : 'bg-emerald-600/40 cursor-not-allowed'
              }`}
            >
              📰 <span className="md:hidden">호재</span><span className="hidden md:inline">호재 검색</span>
            </button>
          </div>

          <button
            onClick={() => setListOpen(p => !p)}
            className="absolute bottom-4 right-4 z-[1000] rounded-full bg-white px-4 py-2 text-sm font-medium shadow-lg hover:bg-gray-50 transition-colors border border-gray-200"
          >
            {listOpen
              ? '목록 닫기 ▼'
              : `목록 보기 (${visibleProperties.length}) ▲`}
          </button>
        </div>

        {/* 하단 매물 목록 — 현재 지도 화면 내 매물만 */}
        {listOpen && (
          <div className="h-72 shrink-0 border-t border-gray-200 bg-white">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
              <span className="text-sm font-medium text-gray-700">
                {searchBounds
                  ? <>검색 영역 <span className="text-blue-600">{visibleProperties.length}건</span> <span className="text-gray-400 text-xs">(전체 {total}건)</span></>
                  : <>매물 목록 <span className="text-blue-600">{total}건</span></>
                }
              </span>
              <span className="text-xs text-gray-400">🔍 버튼 누른 영역 기준</span>
            </div>
            <div className="h-[calc(100%-41px)] overflow-y-auto">
              <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {loading ? (
                  <p className="col-span-full text-center text-sm text-gray-400 py-8">검색 중...</p>
                ) : visibleProperties.length === 0 ? (
                  <div className="col-span-full flex flex-col items-center py-8 text-gray-400">
                    <p className="text-2xl mb-2">🔍</p>
                    <p className="text-sm">이 화면 안에 매물이 없습니다</p>
                    <p className="text-xs mt-1">지도를 이동하거나 줌아웃 하세요</p>
                  </div>
                ) : (
                  visibleProperties.map(p => (
                    <PropertyCardMini
                      key={p.id}
                      property={p}
                      selected={p.id === selectedProperty?.id}
                      onSelect={() => handleMarkerClick(p)}
                      onDetail={() => setDetailProperty(p)}
                    />
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 시세 상세 모달 */}
      {detailProperty && (
        <PropertyDetail
          property={detailProperty}
          onClose={() => setDetailProperty(null)}
        />
      )}

      {/* 호재 검색 모달 */}
      <HojaeModal
        property={selectedProperty}
        open={hojaeOpen}
        onClose={() => setHojaeOpen(false)}
        onAfterCall={bumpUsage}
      />

      {/* 환영 팝업 (첫 방문 시 1회) */}
      <WelcomeModal />

      {/* 우상단 AI 사용량 배지 */}
      <UsageBadge refreshKey={usageRefresh} />

      {/* 비교 분석 모달 */}
      <CompareModal open={compareOpen} onClose={() => setCompareOpen(false)} onAfterCall={bumpUsage} />

      {/* 종합 AI 분석 모달 */}
      <AiFilterModal
        open={aiFilterOpen}
        onClose={() => setAiFilterOpen(false)}
        onSelectProperty={setSelectedProperty}
        onLocateProperty={(p) => mapRef.current?.flyTo(p.lat, p.lng, 16)}
        onAfterCall={bumpUsage}
      />
    </div>
  )
}

/* ─── 호재 검색 모달 ─── */
function HojaeModal({ property, open, onClose, onAfterCall }) {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [trend, setTrend] = useState(null)
  const [rateError, setRateError] = useState(null)
  const captureRef = useRef(null)

  // property 바뀌면 데이터 리셋
  useEffect(() => { setData(null); setTrend(null); setRateError(null) }, [property?.id])

  // 모달 열릴 때 자동으로 검색 시작 + 시세 트렌드 fetch
  useEffect(() => {
    if (!open || !property) return
    let cancelled = false
    setLoading(true); setData(null); setTrend(null); setRateError(null)
    ;(async () => {
      try {
        const dong = property.address?.match(/(\S+동|\S+가)/)?.[1] ?? ''
        const gu   = property.address?.match(/(\S+구)/)?.[1] ?? ''
        const res  = await fetch(`/api/hojae?dong=${encodeURIComponent(dong)}&gu=${encodeURIComponent(gu)}&name=${encodeURIComponent(property.name)}`)
        if (res.status === 429) {
          const err = await res.json()
          if (!cancelled) setRateError(err.detail)
          return
        }
        const json = await res.json()
        if (!cancelled) { setData(json); onAfterCall?.() }
      } catch {
        if (!cancelled) setData({ items: [], query: '' })
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    ;(async () => {
      try {
        const r = await fetch(`/api/properties/${property.id}/trend`)
        const j = await r.json()
        if (!cancelled) setTrend(j.trend || [])
      } catch {
        if (!cancelled) setTrend([])
      }
    })()
    return () => { cancelled = true }
  }, [open, property?.id])

  if (!open || !property) return null

  return (
    <>
      {/* 모달 */}
      <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40" onClick={onClose}>
          <div
            className="relative w-full max-w-lg mx-4 max-h-[80vh] flex flex-col rounded-2xl bg-white shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            {/* 헤더 */}
            <div className="flex items-start justify-between gap-2 px-5 py-4 border-b border-gray-100">
              <div>
                <p className="font-bold text-gray-900">{property.name} 인근 호재</p>
                <p className="text-xs text-gray-400 mt-0.5">{property.address}</p>
              </div>
              <div className="flex items-center gap-2">
                <CaptureButtons targetRef={captureRef} filename={`호재_${property.name}.png`} />
                <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none ml-1">✕</button>
              </div>
            </div>

            {/* 본문 */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3" ref={captureRef}>
              {/* 미니 실거래가 추이 */}
              {trend !== null && (
                <div className="rounded-xl border border-gray-100 bg-white p-3">
                  <MiniPriceChart trend={trend} />
                </div>
              )}

              {/* 미래 교통호재 (GTX 등) */}
              {property?.future_transit?.length > 0 && (
                <div className="rounded-xl border border-sky-200 bg-sky-50/60 p-3">
                  <p className="text-xs font-bold text-sky-700 mb-1.5">🚄 미래 교통호재 (예정·착공 노선)</p>
                  <div className="flex flex-wrap gap-1.5">
                    {property.future_transit.map((t, k) => (
                      <span key={k} className="text-[11px] rounded-full bg-white border border-sky-200 text-sky-700 px-2 py-0.5">
                        <b>{t.line}</b> {t.station}역 도보 {t.walk_min}분 <span className="text-sky-400">· {t.status}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {loading && (
                <div className="flex flex-col items-center py-10 text-gray-400">
                  <div className="animate-spin text-3xl mb-2">🔍</div>
                  <p className="text-sm">네이버 검색 + AI 요약 분석 중...</p>
                  <p className="text-xs mt-1 text-gray-300">뉴스·블로그·카페 90개 글 분석</p>
                </div>
              )}

              {!loading && rateError && (
                <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-4 text-center">
                  <p className="text-2xl mb-2">⏰</p>
                  <p className="text-sm font-bold text-amber-800">오늘 호재 검색 한도 초과</p>
                  <p className="text-xs text-amber-700 mt-1">
                    {rateError.used}/{rateError.limit}회 사용함
                  </p>
                  <p className="text-xs text-gray-500 mt-2">
                    약 {rateError.reset_in_hours}시간 후 한국시간 자정에 리셋됩니다
                  </p>
                </div>
              )}

              {!loading && !rateError && data?.items?.length === 0 && (
                <p className="text-center text-sm text-gray-400 py-8">관련 호재 글을 찾지 못했습니다</p>
              )}

              {/* AI 요약 박스 */}
              {!loading && data?.summary && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-4 space-y-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-emerald-700 bg-emerald-100 rounded-full px-2 py-0.5">🤖 AI 요약</span>
                  </div>
                  <p className="text-sm font-bold text-gray-900 leading-snug">{data.summary.headline}</p>

                  {data.summary.key_points?.length > 0 && (
                    <ul className="space-y-1">
                      {data.summary.key_points.map((pt, i) => (
                        <li key={i} className="flex gap-1.5 text-xs text-gray-700">
                          <span className="text-emerald-600 shrink-0">✓</span>
                          <span>{pt}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {data.summary.categories?.length > 0 && (
                    <div className="space-y-1.5">
                      {data.summary.categories.map((c, i) => (
                        <div key={i} className="rounded-lg bg-white border border-emerald-100 px-2.5 py-1.5">
                          <span className="text-xs font-semibold text-emerald-700">{c.label}</span>
                          <p className="text-xs text-gray-600 mt-0.5">{c.detail}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {data.summary.outlook && (
                    <p className="text-xs text-gray-500 italic border-t border-emerald-100 pt-2">
                      💡 {data.summary.outlook}
                    </p>
                  )}
                </div>
              )}

              {/* 원문 글 목록 */}
              {!loading && data?.items?.length > 0 && (
                <p className="text-xs font-semibold text-gray-400 pt-1">📄 원문 글 {data.items.length}개</p>
              )}
              {!loading && data?.items?.map((item, i) => {
                const badge = { news: ['뉴스', 'bg-blue-100 text-blue-700'], blog: ['블로그', 'bg-green-100 text-green-700'], cafe: ['카페', 'bg-orange-100 text-orange-700'] }[item.type] ?? ['글', 'bg-gray-100 text-gray-700']
                return (
                  <a
                    key={i}
                    href={item.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block rounded-xl border border-gray-100 p-3 hover:border-blue-200 hover:bg-blue-50 transition-all"
                  >
                    <div className="flex items-start gap-2">
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${badge[1]}`}>
                        {badge[0]}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-gray-900 leading-snug line-clamp-2">{item.title}</p>
                        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{item.description}</p>
                        <p className="text-xs text-gray-300 mt-1">{item.date}</p>
                      </div>
                    </div>
                  </a>
                )
              })}
            </div>

            {data && !loading && (
              <div className="px-5 py-2 border-t border-gray-100 text-xs text-gray-400">
                검색어: {data.query}
              </div>
            )}
          </div>
        </div>
    </>
  )
}

/* ─── 지도 위 정보 카드 ─── */
function MapInfoCard({ property: p, onClose, onDetail }) {
  const { bg } = priceColorHex(p.price)
  const age = new Date().getFullYear() - p.built_year

  return (
    <div className="absolute left-3 top-16 md:top-3 z-[1100] w-72 max-w-[calc(100vw-1.5rem)] rounded-2xl bg-white shadow-2xl border border-gray-100 overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-2 px-4 pt-4 pb-2">
        <div className="min-w-0">
          <p className="font-bold text-gray-900 text-sm leading-tight truncate">{p.name}</p>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{p.address}</p>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 text-gray-300 hover:text-gray-500 text-lg leading-none mt-0.5"
        >✕</button>
      </div>

      {/* 가격 + 기본 정보 */}
      <div className="px-4 pb-3 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="rounded-full px-3 py-1 text-sm font-bold text-white"
            style={{ background: bg }}
          >
            {formatPrice(p.price)}
          </span>
          <span className="text-xs text-gray-500">🚇 {p.nearest_subway} 도보 {p.walk_minutes}분</span>
        </div>
        <div className="flex gap-3 text-xs text-gray-500 flex-wrap">
          <span>🏢 {p.units > 0 ? `${p.units.toLocaleString()}세대` : '세대정보없음'}</span>
          <span>📅 {p.built_year > 0 ? `${p.built_year}년 (${age}년)` : '연도미상'}</span>
          <span>📐 {p.area_m2}㎡</span>
          {p.far > 0 && <span>📊 용적률 {p.far}%</span>}
        </div>

        {/* 소요시간 */}
        {p.commute && (
          <div className="grid grid-cols-5 gap-1 pt-1">
            {[
              { label: '강남', key: 'gangnam',     color: '#7c3aed' },
              { label: '여의도', key: 'yeouido',   color: '#2563eb' },
              { label: '광화문', key: 'gwanghwamun',color: '#16a34a' },
              { label: '시청',  key: 'siccheong',  color: '#ea580c' },
              { label: '홍대',  key: 'hongdae',    color: '#e11d48' },
            ].map(({ label, key, color }) => (
              <div key={key} className="text-center bg-gray-50 rounded-lg py-1.5">
                <div className="text-gray-400" style={{ fontSize: '9px' }}>{label}</div>
                <div className="font-bold" style={{ fontSize: '12px', color }}>{p.commute[key]}분</div>
              </div>
            ))}
          </div>
        )}

        {/* 호재 태그 */}
        {p.hojaes?.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {p.hojaes.map(tag => (
              <span key={tag} className={`rounded-full px-2 py-0.5 text-xs font-medium ${HOJAE_STYLE[tag] ?? 'bg-gray-100 text-gray-600'}`}>
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 시세 보기 버튼 */}
      <button
        onClick={onDetail}
        className="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold py-3 transition-colors"
      >
        📈 시세 추이 보기
      </button>
    </div>
  )
}

/* ─── 하단 목록 카드 ─── */
function PropertyCardMini({ property: p, selected, onSelect, onDetail }) {
  const age = new Date().getFullYear() - p.built_year
  const colorCls = priceColorClass(p.price)

  return (
    <div
      className={`rounded-xl border p-3 transition-all cursor-pointer ${
        selected ? 'border-blue-400 bg-blue-50 shadow-md' : 'border-gray-200 bg-white hover:border-blue-200 hover:shadow-sm'
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-1 mb-2">
        <p className="truncate text-sm font-semibold text-gray-900 leading-tight">{p.name}</p>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-bold ${colorCls}`}>
          {formatPrice(p.price)}
        </span>
      </div>
      <div className="flex flex-wrap gap-1 text-xs text-gray-500 mb-1.5">
        <span>🚇 {p.nearest_subway} {p.walk_minutes}분</span>
        <span>·</span>
        <span>🏢 {p.units > 0 ? `${p.units.toLocaleString()}세대` : '-'}</span>
        <span>·</span>
        <span>📅 {p.built_year > 0 ? `${p.built_year}(${age}년)` : '-'}</span>
      </div>
      {p.commute && (
        <div className="grid grid-cols-5 gap-0.5 text-center mb-1.5">
          {[
            { label: '강남', key: 'gangnam',      color: 'text-purple-600' },
            { label: '여의도', key: 'yeouido',    color: 'text-blue-600' },
            { label: '광화문', key: 'gwanghwamun', color: 'text-green-600' },
            { label: '시청',  key: 'siccheong',   color: 'text-orange-600' },
            { label: '홍대',  key: 'hongdae',     color: 'text-rose-600' },
          ].map(({ label, key, color }) => (
            <div key={key} className="bg-gray-50 rounded py-0.5">
              <div className="text-gray-400" style={{ fontSize: '9px' }}>{label}</div>
              <div className={`font-semibold ${color}`} style={{ fontSize: '10px' }}>{p.commute[key]}분</div>
            </div>
          ))}
        </div>
      )}
      {p.hojaes?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1.5">
          {p.hojaes.map(tag => (
            <span key={tag} className={`rounded-full px-2 py-0.5 text-xs font-medium ${HOJAE_STYLE[tag] ?? 'bg-gray-100 text-gray-600'}`}>
              {tag}
            </span>
          ))}
        </div>
      )}
      <button
        onClick={e => { e.stopPropagation(); onDetail() }}
        className="w-full rounded-lg border border-blue-100 bg-blue-50 py-1 text-xs font-medium text-blue-600 hover:bg-blue-100 transition-colors"
      >
        📈 시세 추이 보기
      </button>
    </div>
  )
}

function priceColorHex(manwon) {
  if (manwon >= 300000) return { bg: '#7c3aed' }
  if (manwon >= 150000) return { bg: '#dc2626' }
  if (manwon >= 100000) return { bg: '#ea580c' }
  if (manwon >= 60000)  return { bg: '#ca8a04' }
  return { bg: '#16a34a' }
}

function priceColorClass(manwon) {
  if (manwon >= 300000) return 'text-purple-600 bg-purple-50'
  if (manwon >= 150000) return 'text-red-600 bg-red-50'
  if (manwon >= 100000) return 'text-orange-600 bg-orange-50'
  if (manwon >= 60000)  return 'text-yellow-600 bg-yellow-50'
  return 'text-green-600 bg-green-50'
}

function formatPrice(manwon) {
  if (manwon >= 10000) return `${(manwon / 10000).toFixed(1)}억`
  return `${manwon.toLocaleString()}만`
}
