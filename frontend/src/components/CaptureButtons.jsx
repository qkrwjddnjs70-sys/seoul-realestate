import { useState } from 'react'
import { copyImageToClipboard, downloadImage } from '../utils/captureImage'

export default function CaptureButtons({ targetRef, filename = 'capture.png' }) {
  const [status, setStatus] = useState('')

  async function copy() {
    setStatus('복사 중...')
    try {
      await copyImageToClipboard(targetRef.current)
      setStatus('✓ 복사됨')
    } catch (e) {
      setStatus('복사 실패 — 다운로드로 시도')
    }
    setTimeout(() => setStatus(''), 2000)
  }

  async function download() {
    setStatus('생성 중...')
    try {
      await downloadImage(targetRef.current, filename)
      setStatus('✓ 다운로드')
    } catch {
      setStatus('실패')
    }
    setTimeout(() => setStatus(''), 2000)
  }

  return (
    <div className="flex items-center gap-1">
      {status && <span className="text-xs text-gray-500 mr-1">{status}</span>}
      <button
        onClick={copy}
        title="이미지 복사 (Ctrl+V로 메신저에 붙여넣기)"
        className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
      >📋 복사</button>
      <button
        onClick={download}
        title="PNG 다운로드"
        className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
      >⬇ 저장</button>
    </div>
  )
}
