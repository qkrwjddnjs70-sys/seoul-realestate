import { useState, useRef, useEffect } from 'react'
import CaptureButtons from './CaptureButtons'
import MiniPriceChart from './MiniPriceChart'

function fmtPrice(manwon) {
  if (!manwon) return '-'
  if (manwon >= 10000) return `${(manwon / 10000).toFixed(1)}억`
  return `${manwon.toLocaleString()}만`
}

const TIER_STYLE = {
  '상': 'bg-emerald-50 border-emerald-200 text-emerald-700',
  '중': 'bg-amber-50 border-amber-200 text-amber-700',
  '하': 'bg-gray-50 border-gray-200 text-gray-500',
}

export default function CompareModal({ open, onClose, onAfterCall }) {
  const [targets, setTargets] = useState(['', '', ''])
  const [activeCount, setActiveCount] = useState(2)   // 2 or 3
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [trends, setTrends] = useState({})   // { [targetIdx]: trend[] }
  const captureRef = useRef(null)

  // 데이터 로드되면 각 단지별 트렌드 fetch
  useEffect(() => {
    if (!data?.targets) return
    let cancelled = false
    setTrends({})
    data.targets.forEach((side, i) => {
      if (!side.apt?.id) return
      ;(async () => {
        try {
          const r = await fetch(`/api/properties/${side.apt.id}/trend`)
          const j = await r.json()
          if (!cancelled) setTrends(prev => ({ ...prev, [i]: j.trend || [] }))
        } catch {
          if (!cancelled) setTrends(prev => ({ ...prev, [i]: [] }))
        }
      })()
    })
    return () => { cancelled = true }
  }, [data])

  function setTarget(i, v) {
    const next = [...targets]; next[i] = v; setTargets(next)
  }

  async function run() {
    const list = targets.slice(0, activeCount).map(t => t.trim()).filter(Boolean)
    if (list.length < 2) return
    setLoading(true); setData(null); setError(null)
    try {
      const qs = list.map(t => `targets=${encodeURIComponent(t)}`).join('&')
      const res = await fetch(`/api/compare?${qs}`)
      if (res.status === 429) {
        const err = await res.json()
        const d = err.detail
        setError(`⏰ 오늘 비교 분석 한도 초과 (${d.used}/${d.limit}회). 약 ${d.reset_in_hours}시간 후 한국시간 자정 리셋`)
        return
      }
      const json = await res.json()
      if (json.error) setError(json.error)
      else { setData(json); onAfterCall?.() }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setTargets(['', '', '']); setActiveCount(2); setData(null); setError(null)
  }

  if (!open) return null

  const n = data?.targets?.length ?? activeCount
  const gridCols = n === 3 ? 'grid-cols-3' : 'grid-cols-2'

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900">⚖️ 단지·지역 비교 분석</h2>
            <p className="text-xs text-gray-400 mt-0.5">단지명(예: 신길우성2차) 또는 지역명(예: 신길, 마포) — 최대 3개</p>
          </div>
          <div className="flex items-center gap-2">
            {data && <CaptureButtons targetRef={captureRef} filename={`비교_${(data.targets||[]).map(t=>t.label).join('_vs_')}.png`} />}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none ml-1">✕</button>
          </div>
        </div>

        {/* 입력 */}
        <div className="border-b border-gray-100 bg-gray-50 px-6 py-4">
          <div className={`grid gap-2 ${activeCount === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
            {targets.slice(0, activeCount).map((t, i) => (
              <input
                key={i}
                type="text"
                value={t}
                onChange={e => setTarget(i, e.target.value)}
                placeholder={`대상 ${String.fromCharCode(65 + i)}`}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-400"
                onKeyDown={e => e.key === 'Enter' && run()}
              />
            ))}
          </div>
          <div className="flex items-center justify-between mt-3">
            <div className="flex gap-2">
              {activeCount === 2 ? (
                <button
                  onClick={() => setActiveCount(3)}
                  className="text-xs text-blue-600 hover:text-blue-700 font-medium"
                >+ 대상 추가 (3개까지)</button>
              ) : (
                <button
                  onClick={() => { setActiveCount(2); setTarget(2, '') }}
                  className="text-xs text-gray-500 hover:text-gray-700"
                >− 대상 제거</button>
              )}
            </div>
            <button
              onClick={run}
              disabled={loading || targets.slice(0, activeCount).filter(t => t.trim()).length < 2}
              className="rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 px-4 py-2 text-sm font-semibold text-white"
            >
              {loading ? '분석 중...' : '비교 분석'}
            </button>
          </div>
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading && (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <div className="animate-spin text-3xl mb-2">⚖️</div>
              <p className="text-sm">호재 글 + DB 통계 + 인프라 데이터 수집 중...</p>
              <p className="text-xs mt-1 text-gray-300">Sonnet 4.6 비교 리포트 (20~40초)</p>
            </div>
          )}

          {error && (
            <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">⚠ {error}</div>
          )}

          {!loading && !data && !error && (
            <div className="text-center text-gray-400 py-16">
              <p className="text-sm">대상을 입력하고 분석을 시작하세요.</p>
              <p className="text-xs mt-2">예: 신길우성2차 vs 등촌주공3단지 vs 등촌주공5단지</p>
              <p className="text-xs mt-1">또는: 신길 vs 마포 vs 등촌</p>
            </div>
          )}

          {data && (
            <div ref={captureRef} className="space-y-4 bg-white p-4 rounded-xl">
              {/* 캡처용 상단 타이틀 (모달엔 안 보이는 느낌이지만 이미지엔 들어감) */}
              <div className="hidden">⚖️ 단지·지역 비교 분석</div>
              {/* 헤드라인 */}
              <div className="rounded-xl bg-blue-50 border border-blue-200 px-4 py-3">
                <p className="text-sm font-bold text-gray-900">{data.comparison.headline}</p>
              </div>

              {/* 단지·지역 메타 */}
              <div className={`grid gap-3 ${gridCols}`}>
                {data.targets.map((side, i) => (
                  <div key={i} className="rounded-xl border border-gray-200 p-3 bg-white">
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xs font-bold text-blue-600">{String.fromCharCode(65 + i)}</span>
                      <p className="font-bold text-gray-900 text-sm">{side.label}</p>
                    </div>
                    {side.match_type === 'fuzzy' && side.apt && (
                      <div className="mt-1.5 rounded-md bg-amber-50 border border-amber-200 px-2 py-1.5 text-xs text-amber-800">
                        ⚠ 입력과 정확히 일치하는 단지가 없어 <b>"{side.apt.display_name || side.apt.name}"</b>로 추정 분석했습니다
                        {side.match_score && <span className="text-amber-500 ml-1">(유사도 {Math.round(side.match_score*100)}%)</span>}
                      </div>
                    )}
                    {side.apt ? (
                      <div className="mt-2 text-xs text-gray-600 space-y-0.5">
                        <p>📍 {side.apt.address}</p>
                        <p>💰 {fmtPrice(side.apt.last_price)} ({side.apt.area_m2}㎡)</p>
                        <p>🏢 {side.apt.units > 0 ? `${side.apt.units}세대` : '-'} · 📅 {side.apt.built_year > 0 ? `${side.apt.built_year}년` : '-'}</p>
                        {side.apt.far > 0 && <p>📊 용적률 {side.apt.far}%</p>}
                        <p>🚇 {side.apt.nearest_subway}역 {side.apt.walk_minutes}분</p>
                      </div>
                    ) : (
                      <p className="text-xs text-gray-400 mt-1">지역 기반 분석</p>
                    )}

                    {/* 지역 시세 — 50㎡대 + 80㎡대 */}
                    {(side.region_stats?.s50 || side.region_stats?.s80) && (
                      <div className="mt-2 pt-2 border-t border-gray-100 text-xs space-y-1">
                        <p className="font-semibold text-gray-600">지역 시세 (표준 평형)</p>
                        {side.region_stats.s50 ? (
                          <div className="rounded bg-blue-50 px-2 py-1">
                            <p className="text-blue-700 font-semibold">50㎡대 ({side.region_stats.s50.count}개)</p>
                            <p className="text-gray-600">평균 {side.region_stats.s50.avg_price}억 · 범위 {side.region_stats.s50.min_price}~{side.region_stats.s50.max_price}억</p>
                          </div>
                        ) : (
                          <p className="text-gray-400 px-2">50㎡대: 거래 없음</p>
                        )}
                        {side.region_stats.s80 ? (
                          <div className="rounded bg-purple-50 px-2 py-1">
                            <p className="text-purple-700 font-semibold">80㎡대 ({side.region_stats.s80.count}개)</p>
                            <p className="text-gray-600">평균 {side.region_stats.s80.avg_price}억 · 범위 {side.region_stats.s80.min_price}~{side.region_stats.s80.max_price}억</p>
                          </div>
                        ) : (
                          <p className="text-gray-400 px-2">80㎡대: 거래 없음</p>
                        )}
                      </div>
                    )}

                    {/* 미니 실거래가 추이 */}
                    {side.apt && trends[i] !== undefined && (
                      <div className="mt-2 pt-2 border-t border-gray-100">
                        <MiniPriceChart trend={trends[i]} height={70} title="최근 24개월 시세" />
                      </div>
                    )}

                    {/* 인프라 */}
                    {side.infra && Object.keys(side.infra).length > 0 && (
                      <div className="mt-2 pt-2 border-t border-gray-100 text-xs">
                        <p className="font-semibold text-gray-600 mb-1">반경 1km 인프라</p>
                        <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-gray-500">
                          {Object.entries(side.infra).map(([k, v]) => (
                            <p key={k}>{k}: <span className="text-gray-700 font-medium">{v}</span></p>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 미래 교통호재 (GTX 등 예정노선) */}
                    {side.future_transit?.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-sky-100 text-xs">
                        <p className="font-semibold text-sky-700 mb-1">🚄 미래 교통호재</p>
                        <div className="flex flex-wrap gap-1">
                          {side.future_transit.map((t, k) => (
                            <span key={k} className="text-[11px] rounded-full bg-sky-50 border border-sky-200 text-sky-700 px-1.5 py-0.5">
                              {t.line} {t.station}역 {t.walk_min}분·{t.status}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 지역 개발성 (정비사업 정보몽땅) */}
                    {(side.nearby_redev?.length > 0 || side.dong_projects?.length > 0) && (
                      <div className="mt-2 pt-2 border-t border-purple-100 text-xs">
                        <div className="flex items-center justify-between mb-1">
                          <p className="font-semibold text-purple-700">🏗 지역 개발성</p>
                          {side.dev_grade && side.dev_grade !== '-' && (
                            <span className={`text-[11px] font-bold rounded-full px-2 py-0.5 ${
                              side.dev_grade === '상' ? 'bg-red-100 text-red-700'
                              : side.dev_grade === '중' ? 'bg-amber-100 text-amber-700'
                              : 'bg-gray-100 text-gray-500'}`}>
                              개발성 {side.dev_grade}
                            </span>
                          )}
                        </div>
                        {side.nearby_redev?.length > 0 && (
                          <div className="mb-1">
                            <p className="text-gray-500">반경 700m 재건축 <b className="text-purple-700">{side.nearby_redev.length}개</b></p>
                            <div className="mt-0.5 space-y-0.5">
                              {side.nearby_redev.slice(0, 5).map((n, k) => (
                                <p key={k} className="text-gray-600">
                                  · {n.name} <span className="text-gray-400">{n.dist_m}m</span>
                                  <span className={`ml-1 ${n.official ? 'text-purple-600' : 'text-amber-600'}`}>{n.stage}</span>
                                </p>
                              ))}
                            </div>
                          </div>
                        )}
                        {side.dong_projects?.length > 0 && (
                          <div className="mt-1">
                            <p className="text-gray-500">{side.apt?.dong} 정비사업 <b className="text-purple-700">{side.dong_projects.length}건</b></p>
                            <div className="mt-0.5 space-y-0.5">
                              {side.dong_projects.slice(0, 6).map((p, k) => (
                                <p key={k} className="text-gray-600">
                                  · <span className="text-gray-400">[{p.type}]</span> {p.name}
                                  <span className="text-purple-600 ml-1">{p.stage}</span>
                                </p>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* 카테고리 비교 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">📊 항목별 비교</h3>
                <div className="space-y-2">
                  {data.comparison.categories.map((c, i) => (
                    <div key={i} className="rounded-xl border border-gray-100 overflow-hidden">
                      <div className="bg-gray-50 px-3 py-1.5 text-xs font-semibold text-gray-700 border-b border-gray-100">
                        {c.name}
                      </div>
                      <div className={`grid ${gridCols} divide-x divide-gray-100`}>
                        {c.evaluations.map((ev, j) => (
                          <div key={j} className={`p-3 text-xs border ${TIER_STYLE[ev.tier] || ''}`}>
                            <span className="inline-block rounded-full px-1.5 text-xs font-bold mr-1.5">{ev.tier}</span>
                            <span>{ev.summary}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 강점 */}
              <div className={`grid gap-3 ${gridCols}`}>
                {data.comparison.pros.map((items, i) => (
                  <div key={i} className="rounded-xl border border-blue-100 bg-blue-50/40 p-3">
                    <p className="text-xs font-bold text-blue-700 mb-1.5">{String.fromCharCode(65 + i)} 강점</p>
                    <ul className="space-y-1">
                      {items.map((it, j) => (
                        <li key={j} className="text-xs text-gray-700 flex gap-1.5">
                          <span className="text-blue-600 shrink-0">•</span>
                          <span>{it}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>

              {/* 소문 (미확정) */}
              {data.comparison.rumors?.some(r => r?.length > 0) && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">🗣️ 카페·블로그 미확정 소문</h3>
                  <div className={`grid gap-3 ${gridCols}`}>
                    {data.comparison.rumors.map((list, i) => (
                      <div key={i} className="rounded-xl border border-amber-200 bg-amber-50/40 p-3">
                        <p className="text-xs font-bold text-amber-700 mb-1.5">{String.fromCharCode(65 + i)}</p>
                        {list && list.length > 0 ? (
                          <ul className="space-y-2">
                            {list.map((r, j) => (
                              <li key={j} className="text-xs">
                                <p className="font-semibold text-amber-800">📌 {r.topic}</p>
                                <p className="text-gray-700 mt-0.5">{r.detail}</p>
                                <p className="text-gray-400 mt-0.5 italic">— {r.source}</p>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-xs text-gray-400">확인된 소문 없음</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 추천 대상 */}
              <div className={`grid gap-3 ${gridCols}`}>
                {data.comparison.recommended_for.map((aud, i) => (
                  <div key={i} className="rounded-xl border border-gray-200 p-3">
                    <p className="text-xs font-semibold text-gray-500 mb-1">{String.fromCharCode(65 + i)} 추천 대상</p>
                    <p className="text-sm text-gray-800">{aud}</p>
                  </div>
                ))}
              </div>

              {/* 종합 */}
              <div className="rounded-xl bg-gray-50 border border-gray-200 p-4">
                <p className="text-xs font-bold text-gray-500 mb-2">📝 종합 분석</p>
                <p className="text-sm text-gray-800 leading-relaxed">{data.comparison.summary}</p>
              </div>

              <div className="text-center pt-2">
                <button onClick={reset} className="text-xs text-gray-400 hover:text-gray-600">
                  다른 대상으로 다시 비교
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
