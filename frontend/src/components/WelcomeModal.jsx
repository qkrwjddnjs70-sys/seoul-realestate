import { useEffect, useState } from 'react'

const STORAGE_KEY = 'welcome-dismissed-v1'

export default function WelcomeModal() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) setOpen(true)
  }, [])

  function close(remember = false) {
    if (remember) localStorage.setItem(STORAGE_KEY, '1')
    setOpen(false)
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 p-4"
      onClick={() => close(false)}
    >
      <div
        className="relative w-full max-w-sm rounded-2xl bg-white shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* 상단 그라데이션 헤더 */}
        <div className="bg-gradient-to-br from-blue-500 via-indigo-500 to-purple-600 px-6 py-5 text-white">
          <p className="text-2xl">🏙️</p>
          <h2 className="text-lg font-bold mt-2">서울 부동산 탐색</h2>
          <p className="text-xs text-blue-100 mt-1">실거래가·재건축·호재·매물을 한눈에</p>
        </div>

        {/* 본문 */}
        <div className="px-6 py-5 space-y-3">
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-3 text-sm">
            <div className="flex items-start gap-2">
              <span className="text-gray-400 shrink-0 w-12">만든이</span>
              <span className="text-gray-800 font-semibold">당산동 사는 박정원</span>
            </div>
            <div className="flex items-start gap-2 mt-2">
              <span className="text-gray-400 shrink-0 w-12">문의</span>
              <a
                href="mailto:qkrwjddnjs70@gmail.com"
                className="text-blue-600 hover:underline break-all"
              >
                qkrwjddnjs70@gmail.com
              </a>
            </div>
          </div>

          <p className="text-xs text-gray-500 leading-relaxed">
            데이터 출처: 국토부 실거래가, 서울시 정비사업, K-apt, 네이버 부동산, 카카오 지도.
            <br />
            제안·오류 제보·기능 요청 환영합니다.
          </p>
        </div>

        {/* 버튼 */}
        <div className="flex border-t border-gray-100">
          <button
            onClick={() => close(true)}
            className="flex-1 py-3 text-xs text-gray-500 hover:bg-gray-50 transition-colors"
          >
            다시 보지 않기
          </button>
          <button
            onClick={() => close(false)}
            className="flex-1 py-3 text-sm font-semibold text-blue-600 hover:bg-blue-50 transition-colors border-l border-gray-100"
          >
            시작하기
          </button>
        </div>
      </div>
    </div>
  )
}
