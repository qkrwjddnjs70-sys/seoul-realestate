import { useEffect, useState } from 'react'
import axios from 'axios'

const LABEL = {
  hojae:   '호재',
  compare: '비교',
  filter:  'AI분석',
}

/**
 * 남은 AI 사용 횟수를 작게 표시
 * - 마운트 시 1회 fetch
 * - refreshKey가 바뀌면 다시 fetch (AI 호출 후 부모가 trigger)
 */
export default function UsageBadge({ refreshKey = 0 }) {
  const [usage, setUsage] = useState(null)

  useEffect(() => {
    axios.get('/api/usage').then(r => setUsage(r.data)).catch(() => {})
  }, [refreshKey])

  // null 이거나 빈 객체면 한도 비활성 — 배지 숨김
  if (!usage || Object.keys(usage).length === 0) return null

  return (
    <div className="absolute top-3 right-3 z-[1100] flex gap-1 text-[10px] bg-white/90 backdrop-blur-sm rounded-full shadow-md border border-gray-200 px-2 py-1">
      {Object.entries(usage).map(([k, v]) => {
        const low = v.remaining <= Math.max(1, v.limit * 0.2)
        return (
          <span
            key={k}
            className={`px-1.5 rounded-full font-semibold ${
              v.remaining === 0
                ? 'bg-red-100 text-red-700'
                : low
                ? 'bg-amber-100 text-amber-700'
                : 'bg-gray-50 text-gray-600'
            }`}
            title={`${LABEL[k]} 오늘 ${v.used}/${v.limit} 사용`}
          >
            {LABEL[k]} {v.remaining}
          </span>
        )
      })}
    </div>
  )
}
