import html2canvas from 'html2canvas'

/**
 * DOM 노드를 canvas로 캡처
 */
async function _capture(el) {
  if (!el) throw new Error('no element')

  // 캡처 대상 + 스크롤을 만드는 모든 조상(overflow auto/hidden/scroll)의
  // 제약을 임시로 풀어 전체(가로·세로)가 캡처되게 한다.
  const touched = []
  function relax(node, isTarget) {
    if (!node || node === document.body) return
    const cs = getComputedStyle(node)
    const needs =
      isTarget ||
      ['auto', 'scroll', 'hidden'].includes(cs.overflow) ||
      ['auto', 'scroll', 'hidden'].includes(cs.overflowX) ||
      ['auto', 'scroll', 'hidden'].includes(cs.overflowY)
    if (needs) {
      touched.push({
        node,
        overflow: node.style.overflow,
        overflowX: node.style.overflowX,
        overflowY: node.style.overflowY,
        maxHeight: node.style.maxHeight,
        maxWidth: node.style.maxWidth,
        height: node.style.height,
        width: node.style.width,
      })
      node.style.overflow = 'visible'
      node.style.overflowX = 'visible'
      node.style.overflowY = 'visible'
      node.style.maxHeight = 'none'
      node.style.maxWidth = 'none'
      node.style.height = 'auto'
      if (isTarget) node.style.width = node.scrollWidth + 'px'
    }
  }

  // 대상 + 조상 8단계까지 relax
  relax(el, true)
  let p = el.parentElement, depth = 0
  while (p && depth < 8) { relax(p, false); p = p.parentElement; depth++ }

  // 레이아웃 반영 대기
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))

  const w = el.scrollWidth
  const h = el.scrollHeight
  try {
    return await html2canvas(el, {
      backgroundColor: '#ffffff',
      scale: 2,
      useCORS: true,
      logging: false,
      width: w,
      height: h,
      windowWidth: w,
      windowHeight: h,
    })
  } finally {
    for (const t of touched) {
      t.node.style.overflow = t.overflow
      t.node.style.overflowX = t.overflowX
      t.node.style.overflowY = t.overflowY
      t.node.style.maxHeight = t.maxHeight
      t.node.style.maxWidth = t.maxWidth
      t.node.style.height = t.height
      t.node.style.width = t.width
    }
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
