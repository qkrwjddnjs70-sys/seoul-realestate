import { useState, useEffect, useRef } from 'react'

const CUR_YEAR = new Date().getFullYear()

export const GU_LIST = [
  { lawd_cd: '11110', name: '종로구', lat: 37.5730, lng: 126.9794 },
  { lawd_cd: '11140', name: '중구',   lat: 37.5636, lng: 126.9975 },
  { lawd_cd: '11170', name: '용산구', lat: 37.5311, lng: 126.9810 },
  { lawd_cd: '11200', name: '성동구', lat: 37.5633, lng: 127.0372 },
  { lawd_cd: '11215', name: '광진구', lat: 37.5385, lng: 127.0823 },
  { lawd_cd: '11230', name: '동대문구', lat: 37.5744, lng: 127.0397 },
  { lawd_cd: '11260', name: '중랑구', lat: 37.6063, lng: 127.0927 },
  { lawd_cd: '11290', name: '성북구', lat: 37.5894, lng: 127.0167 },
  { lawd_cd: '11305', name: '강북구', lat: 37.6397, lng: 127.0257 },
  { lawd_cd: '11320', name: '도봉구', lat: 37.6688, lng: 127.0471 },
  { lawd_cd: '11350', name: '노원구', lat: 37.6542, lng: 127.0568 },
  { lawd_cd: '11380', name: '은평구', lat: 37.6027, lng: 126.9290 },
  { lawd_cd: '11410', name: '서대문구', lat: 37.5791, lng: 126.9368 },
  { lawd_cd: '11440', name: '마포구', lat: 37.5663, lng: 126.9014 },
  { lawd_cd: '11470', name: '양천구', lat: 37.5170, lng: 126.8666 },
  { lawd_cd: '11500', name: '강서구', lat: 37.5510, lng: 126.8495 },
  { lawd_cd: '11530', name: '구로구', lat: 37.4954, lng: 126.8874 },
  { lawd_cd: '11545', name: '금천구', lat: 37.4569, lng: 126.8955 },
  { lawd_cd: '11560', name: '영등포구', lat: 37.5264, lng: 126.8963 },
  { lawd_cd: '11590', name: '동작구', lat: 37.5124, lng: 126.9393 },
  { lawd_cd: '11620', name: '관악구', lat: 37.4784, lng: 126.9516 },
  { lawd_cd: '11650', name: '서초구', lat: 37.4837, lng: 127.0324 },
  { lawd_cd: '11680', name: '강남구', lat: 37.5172, lng: 127.0473 },
  { lawd_cd: '11710', name: '송파구', lat: 37.5145, lng: 127.1059 },
  { lawd_cd: '11740', name: '강동구', lat: 37.5301, lng: 127.1238 },
]

export const COMMUTE_HUBS = [
  { key: 'maxTimeGangnam',    label: '강남역',   icon: '🏢', color: 'text-purple-600' },
  { key: 'maxTimeYeouido',    label: '여의도역',  icon: '🏦', color: 'text-blue-600' },
  { key: 'maxTimeGwanghwamun',label: '광화문역',  icon: '🏛️', color: 'text-green-600' },
  { key: 'maxTimeSiccheong',  label: '시청역',   icon: '🏙️', color: 'text-orange-600' },
  { key: 'maxTimeHongdae',    label: '홍대입구역', icon: '🎨', color: 'text-rose-600' },
]

export const HOJAE_LIST = [
  { tag: '재건축',   icon: '🏗️',  color: { activeBg: 'bg-orange-500', activeText: 'text-white' } },
  { tag: '재개발',   icon: '🏚️',  color: { activeBg: 'bg-red-500',    activeText: 'text-white' } },
  { tag: '뉴타운',   icon: '🌆',  color: { activeBg: 'bg-blue-500',   activeText: 'text-white' } },
  { tag: '리모델링', icon: '🔨',  color: { activeBg: 'bg-green-500',  activeText: 'text-white' } },
  { tag: 'GTX',      icon: '🚄',  color: { activeBg: 'bg-purple-500', activeText: 'text-white' } },
  { tag: '역세권개발', icon: '🚉', color: { activeBg: 'bg-cyan-500',   activeText: 'text-white' } },
  { tag: '신규노선',   icon: '🆕', color: { activeBg: 'bg-rose-500',   activeText: 'text-white' } },
]

export const HOJAE_STYLE = {
  '재건축':   'bg-orange-100 text-orange-700',
  '재개발':   'bg-red-100 text-red-700',
  '뉴타운':   'bg-blue-100 text-blue-700',
  '리모델링': 'bg-green-100 text-green-700',
  'GTX':      'bg-purple-100 text-purple-700',
  '역세권개발': 'bg-cyan-100 text-cyan-700',
  '신규노선': 'bg-rose-100 text-rose-700',
}

function RangeRow({ label, min, max, value, onChange, unit, step = 1 }) {
  return (
    <div className="mb-4">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span className="font-medium text-gray-700">
          {value[0].toLocaleString()} ~ {value[1].toLocaleString()} {unit}
        </span>
      </div>
      <div className="flex gap-2 items-center">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value[0]}
          onChange={e => {
            const v = Number(e.target.value)
            if (v <= value[1]) onChange([v, value[1]])
          }}
          className="w-full accent-blue-600"
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value[1]}
          onChange={e => {
            const v = Number(e.target.value)
            if (v >= value[0]) onChange([value[0], v])
          }}
          className="w-full accent-blue-600"
        />
      </div>
    </div>
  )
}

export default function FilterPanel({ filters, onChange, total, loading, onGuSelect }) {
  const [stationInput, setStationInput] = useState(filters.subwayStation || '')
  const [aptNameInput, setAptNameInput] = useState(filters.aptName || '')
  const [dongList, setDongList] = useState([])

  // 단지명 디바운스 (입력 멈춘 뒤 0.4초 후 검색)
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.aptName || '') !== aptNameInput)
        onChange({ ...filters, aptName: aptNameInput || undefined })
    }, 400)
    return () => clearTimeout(t)
  }, [aptNameInput]) // eslint-disable-line react-hooks/exhaustive-deps

  function set(key, val) {
    onChange({ ...filters, [key]: val })
  }

  const selectedCodes = filters.lawdCds ?? []
  const selectedGuNames = GU_LIST.filter(g => selectedCodes.includes(g.lawd_cd)).map(g => g.name)
  const selectedDongs = filters.dongs ?? []

  // 구 선택 바뀔 때 동 목록 로드
  useState(() => {})
  const prevCodes = useRef([])
  useEffect(() => {
    if (selectedCodes.join(',') === prevCodes.current.join(',')) return
    prevCodes.current = selectedCodes
    setDongList([])
    onChange({ ...filters, dongs: [] })  // 구 바뀌면 동 초기화
    if (selectedCodes.length === 0) return
    fetch(`/api/properties/dongs?lawd_cd=${selectedCodes.join(',')}`)
      .then(r => r.json())
      .then(d => setDongList(d.dongs ?? []))
      .catch(() => {})
  }, [selectedCodes.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-gray-200 bg-white">
      {/* 헤더 */}
      <div className="border-b border-gray-200 px-5 py-4">
        <h1 className="text-lg font-bold text-gray-900">🏙️ 서울 부동산</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          {loading ? '검색 중...' : `총 ${total}개 매물`}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

        {/* 단지명 검색 */}
        <section>
          <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-gray-800">
            🔎 단지명 검색
          </h2>
          <div className="relative">
            <input
              type="text"
              value={aptNameInput}
              onChange={e => setAptNameInput(e.target.value)}
              placeholder="예: 신길우성, 래미안에스티움"
              className="w-full rounded-lg border border-gray-200 px-3 py-2 pr-7 text-xs outline-none focus:border-blue-400"
            />
            {aptNameInput && (
              <button
                onClick={() => setAptNameInput('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-sm"
              >✕</button>
            )}
          </div>
          <p className="mt-1 text-xs text-gray-400">띄어쓰기 오차는 자동 보정됩니다</p>
        </section>

        <hr className="border-gray-100" />

        {/* 구 선택 (다중) */}
        <section>
          <h2 className="mb-1.5 flex items-center justify-between text-sm font-semibold text-gray-800">
            <span>🗺️ 구 선택 <span className="text-xs font-normal text-gray-400">(복수 선택 가능)</span></span>
            {selectedCodes.length > 0 && (
              <button
                onClick={() => onChange({ ...filters, lawdCds: [] })}
                className="text-xs text-gray-400 hover:text-red-400"
              >전체</button>
            )}
          </h2>
          <div className="flex flex-wrap gap-1">
            {GU_LIST.map(g => {
              const active = selectedCodes.includes(g.lawd_cd)
              return (
                <button
                  key={g.lawd_cd}
                  onClick={() => {
                    const next = active
                      ? selectedCodes.filter(c => c !== g.lawd_cd)
                      : [...selectedCodes, g.lawd_cd]
                    onChange({ ...filters, lawdCds: next })
                    if (!active && onGuSelect) onGuSelect(g)
                  }}
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium border transition-all ${
                    active
                      ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                      : 'bg-gray-50 text-gray-600 border-gray-200 hover:border-blue-300 hover:text-blue-600'
                  }`}
                >
                  {g.name}
                </button>
              )
            })}
          </div>
          {selectedGuNames.length > 0 && (
            <p className="mt-1.5 text-xs text-blue-600 font-medium">📍 {selectedGuNames.join(', ')} 선택됨</p>
          )}
        </section>

        {/* 동 선택 — 구가 선택됐을 때만 표시 */}
        {dongList.length > 0 && (
          <>
            <hr className="border-gray-100" />
            <section>
              <h2 className="mb-1.5 flex items-center justify-between text-sm font-semibold text-gray-800">
                <span>🏘️ 동 선택 <span className="text-xs font-normal text-gray-400">(복수 선택)</span></span>
                {selectedDongs.length > 0 && (
                  <button
                    onClick={() => onChange({ ...filters, dongs: [] })}
                    className="text-xs text-gray-400 hover:text-red-400"
                  >전체</button>
                )}
              </h2>
              <div className="flex flex-wrap gap-1 max-h-36 overflow-y-auto">
                {dongList.map(dong => {
                  const active = selectedDongs.includes(dong)
                  return (
                    <button
                      key={dong}
                      onClick={() => {
                        const next = active
                          ? selectedDongs.filter(d => d !== dong)
                          : [...selectedDongs, dong]
                        onChange({ ...filters, dongs: next })
                      }}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium border transition-all ${
                        active
                          ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm'
                          : 'bg-gray-50 text-gray-600 border-gray-200 hover:border-emerald-300 hover:text-emerald-600'
                      }`}
                    >
                      {dong}
                    </button>
                  )
                })}
              </div>
              {selectedDongs.length > 0 && (
                <p className="mt-1.5 text-xs text-emerald-600 font-medium">🏘️ {selectedDongs.join(', ')} 선택됨</p>
              )}
            </section>
          </>
        )}

        <hr className="border-gray-100" />

        {/* 지하철역 도보 시간 */}
        <section>
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-gray-800">
            🚇 역 도보 시간
          </h2>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>최대 도보</span>
            <span className="font-medium text-blue-600">
              {filters.maxWalkMinutes == null ? '제한없음' : `${filters.maxWalkMinutes}분 이내`}
            </span>
          </div>
          <input
            type="range"
            min={1}
            max={30}
            step={1}
            value={filters.maxWalkMinutes ?? 30}
            onChange={e => set('maxWalkMinutes', Number(e.target.value))}
            className="w-full accent-blue-600"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-0.5">
            <span>1분</span><span>30분</span>
          </div>
          <input
            type="text"
            placeholder="특정 역 이름 (예: 강남)"
            value={stationInput}
            onChange={e => setStationInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && set('subwayStation', stationInput)}
            onBlur={() => set('subwayStation', stationInput)}
            className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-1.5 text-xs outline-none focus:border-blue-400"
          />
        </section>

        <hr className="border-gray-100" />

        {/* 세대수 */}
        <section>
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-gray-800">
            🏢 세대수
          </h2>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>범위</span>
            <span className="font-medium text-gray-700">
              {(filters.minUnits ?? 0).toLocaleString()} ~ {(filters.maxUnits ?? 3000).toLocaleString()} 세대
            </span>
          </div>
          <div className="flex gap-2">
            <input type="range" min={0} max={3000} step={50}
              value={filters.minUnits ?? 0}
              onChange={e => { const v = Number(e.target.value); if (v <= (filters.maxUnits ?? 3000)) set('minUnits', v) }}
              className="w-full accent-blue-600" />
            <input type="range" min={0} max={3000} step={50}
              value={filters.maxUnits ?? 3000}
              onChange={e => { const v = Number(e.target.value); if (v >= (filters.minUnits ?? 0)) set('maxUnits', v) }}
              className="w-full accent-blue-600" />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-0.5">
            <span>0</span><span>3,000세대</span>
          </div>
        </section>

        <hr className="border-gray-100" />

        {/* 실거래가 */}
        <section>
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-gray-800">
            💰 실거래가
          </h2>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>범위</span>
            <span className="font-medium text-gray-700">
              {formatPrice(filters.minPrice ?? 10000)} ~ {formatPrice(filters.maxPrice ?? 200000)}
            </span>
          </div>
          <div className="flex gap-2">
            <input type="range" min={10000} max={200000} step={5000}
              value={filters.minPrice ?? 10000}
              onChange={e => { const v = Number(e.target.value); if (v <= (filters.maxPrice ?? 200000)) set('minPrice', v) }}
              className="w-full accent-blue-600" />
            <input type="range" min={10000} max={200000} step={5000}
              value={filters.maxPrice ?? 200000}
              onChange={e => { const v = Number(e.target.value); if (v >= (filters.minPrice ?? 10000)) set('maxPrice', v) }}
              className="w-full accent-blue-600" />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-0.5">
            <span>1억</span><span>20억</span>
          </div>
        </section>

        <hr className="border-gray-100" />

        {/* 연식 */}
        <section>
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-gray-800">
            📅 연식 (준공년도)
          </h2>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>범위</span>
            <span className="font-medium text-gray-700">
              {filters.minBuiltYear ?? 1985}년 ~ {filters.maxBuiltYear ?? CUR_YEAR}년
            </span>
          </div>
          <div className="flex gap-2">
            <input type="range" min={1985} max={CUR_YEAR} step={1}
              value={filters.minBuiltYear ?? 1985}
              onChange={e => { const v = Number(e.target.value); if (v <= (filters.maxBuiltYear ?? CUR_YEAR)) set('minBuiltYear', v) }}
              className="w-full accent-blue-600" />
            <input type="range" min={1985} max={CUR_YEAR} step={1}
              value={filters.maxBuiltYear ?? CUR_YEAR}
              onChange={e => { const v = Number(e.target.value); if (v >= (filters.minBuiltYear ?? 1985)) set('maxBuiltYear', v) }}
              className="w-full accent-blue-600" />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-0.5">
            <span>1985</span><span>{CUR_YEAR}</span>
          </div>
        </section>

      </div>

      {/* 초기화 버튼 */}
      <div className="border-t border-gray-200 px-5 py-3">
        <button
          onClick={() => {
            setStationInput('')
            setAptNameInput('')
            onChange({ lawdCds: ['11560', '11500'] })
          }}
          className="w-full rounded-lg border border-gray-300 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
        >
          필터 초기화
        </button>
      </div>
    </aside>
  )
}

function formatPrice(manwon) {
  if (manwon >= 10000) return `${(manwon / 10000).toFixed(1)}억`
  return `${manwon.toLocaleString()}만`
}
