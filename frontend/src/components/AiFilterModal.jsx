import { useState, useRef } from 'react'
import CaptureButtons from './CaptureButtons'

function fmtPrice(m) {
  if (!m) return '-'
  if (m >= 10000) return `${(m / 10000).toFixed(1)}억`
  return `${m.toLocaleString()}만`
}

const EXAMPLES = [
  "내 예산은 12억이고 실거주만족도와 향후 성장성을 같이 고려하고있어. 역과는 가까워야하고 평지에 세대수는 300가구 이상이여야해",
  "예산 9억 이하 마포구·영등포구, 도보 7분 이내, 500세대 이상, 평지",
  "10억 안쪽 신축 위주, 50㎡대, 강서구·양천구에서 골라줘",
]

export default function AiFilterModal({ open, onClose, onSelectProperty, onLocateProperty }) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const captureRef = useRef(null)

  async function run() {
    if (!query.trim()) return
    setLoading(true); setData(null); setError(null)
    try {
      const res = await fetch('/api/ai-filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() }),
      })
      const json = await res.json()
      if (json.error) setError(json.error)
      else setData(json)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900">🤖 종합 AI 분석</h2>
            <p className="text-xs text-gray-400 mt-0.5">조건을 자연어로 입력하면 AI가 맞는 단지를 추려드립니다</p>
          </div>
          <div className="flex items-center gap-2">
            {data && <CaptureButtons targetRef={captureRef} filename={`AI추천_${query.slice(0,20)}.png`} />}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none ml-1">✕</button>
          </div>
        </div>

        {/* 입력 */}
        <div className="border-b border-gray-100 bg-gray-50 px-6 py-4 space-y-2">
          <textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="예: 내 예산은 12억이고 실거주만족도와 향후 성장성을 같이 고려하고있어. 역과는 가까워야하고 평지에 세대수는 300가구 이상이여야해"
            rows={3}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-400 resize-none"
          />
          <div className="flex items-center justify-between">
            <div className="flex flex-wrap gap-1">
              {EXAMPLES.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => setQuery(ex)}
                  className="text-[11px] text-gray-500 hover:text-blue-600 rounded-full border border-gray-200 px-2 py-0.5"
                >예시 {i + 1}</button>
              ))}
            </div>
            <button
              onClick={run}
              disabled={loading || !query.trim()}
              className="rounded-lg bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 px-4 py-2 text-sm font-semibold text-white"
            >
              {loading ? '분석 중...' : 'AI 추천 받기'}
            </button>
          </div>
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading && (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <div className="animate-spin text-3xl mb-2">🤖</div>
              <p className="text-sm">조건 파싱 + 단지 점수 산출 중...</p>
            </div>
          )}

          {error && (
            <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">⚠ {error}</div>
          )}

          {!loading && !data && !error && (
            <div className="text-center text-gray-400 py-16 text-sm">
              조건을 입력하고 추천을 시작하세요.
            </div>
          )}

          {data && (
            <div ref={captureRef} className="space-y-3 bg-white p-2">
              {/* 해석 */}
              <div className="rounded-xl bg-purple-50 border border-purple-200 px-4 py-3">
                <p className="text-xs font-bold text-purple-700 mb-1">🧠 AI가 이해한 조건</p>
                <p className="text-sm text-gray-800">{data.interpretation}</p>
                <p className="text-xs text-gray-500 mt-1.5">
                  조건 부합 {data.total_matched}개 단지 중 점수 상위 {data.results.length}개
                </p>
              </div>

              {/* 결과 리스트 */}
              {data.results.length === 0 ? (
                <p className="text-center text-sm text-gray-400 py-8">조건에 맞는 단지가 없습니다. 조건을 완화해보세요.</p>
              ) : (
                <div className="space-y-2">
                  {data.results.map((r, i) => (
                    <div
                      key={r.id}
                      className="rounded-xl border border-gray-200 hover:border-purple-300 hover:bg-purple-50/40 p-3 cursor-pointer transition-colors"
                      onClick={() => { onLocateProperty?.(r); onSelectProperty?.(r) }}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-baseline gap-1.5 min-w-0">
                          <span className="text-xs font-bold text-purple-600 shrink-0">#{i + 1}</span>
                          <p className="font-bold text-gray-900 text-sm truncate">{r.name}</p>
                          <span className="text-xs text-gray-400 shrink-0">{r.score}점</span>
                        </div>
                        <p className="text-sm font-bold text-blue-600 shrink-0">{fmtPrice(r.last_price)}</p>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">📍 {r.address}</p>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-gray-600 mt-1">
                        <span>🏢 {r.units > 0 ? `${r.units}세대` : '-'}</span>
                        <span>📅 {r.built_year > 0 ? `${r.built_year}년` : '-'}</span>
                        <span>📐 {r.area_m2}㎡</span>
                        {r.nearest_subway && <span>🚇 {r.nearest_subway}역 {r.walk_minutes}분</span>}
                        {r.slope > 0 && <span>⛰️ 경사 {Math.round(r.slope)}m</span>}
                        {r.land_share > 0 && <span>🟫 대지 {r.land_share.toFixed(1)}㎡</span>}
                      </div>
                      {r.reasons.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {r.reasons.map((reason, j) => (
                            <span key={j} className="text-[11px] rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-0.5">
                              ✓ {reason}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
