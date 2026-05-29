import html2canvas from 'html2canvas'

/**
 * DOM 노드를 canvas로 캡처
 */
async function _capture(el) {
  if (!el) throw new Error('no element')
  // 스크롤 영역 전체를 캡처: 임시로 overflow 해제 + max-height 제거
  const original = {
    overflow:  el.style.overflow,
    maxHeight: el.style.maxHeight,
    height:    el.style.height,
  }
  el.style.overflow  = 'visible'
  el.style.maxHeight = 'none'
  el.style.height    = 'auto'
  try {
    return await html2canvas(el, {
      backgroundColor: '#ffffff',
      scale: 2,
      useCORS: true,
      logging: false,
      width:        el.scrollWidth,
      height:       el.scrollHeight,
      windowWidth:  el.scrollWidth,
      windowHeight: el.scrollHeight,
    })
  } finally {
    el.style.overflow  = original.overflow
    el.style.maxHeight = original.maxHeight
    el.style.height    = original.height
  }
}

/**
 * 캡처 → 클립보드 복사 (메신저·카톡에 Ctrl+V로 붙여넣기 가능)
 */
export async function copyImageToClipboard(el) {
  const canvas = await _capture(el)
  return new Promise((resolve, reject) => {
    canvas.toBlob(async (blob) => {
      if (!blob) return reject('blob 생성 실패')
      try {
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob }),
        ])
        resolve(true)
      } catch (e) {
        reject(e)
      }
    }, 'image/png')
  })
}

/**
 * 캡처 → PNG 파일 다운로드
 */
export async function downloadImage(el, filename = 'capture.png') {
  const canvas = await _capture(el)
  const url = canvas.toDataURL('image/png')
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
