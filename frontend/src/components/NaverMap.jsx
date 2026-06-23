import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { SUBWAY_LINES } from '../data/subwayLines'

function priceColor(manwon) {
  if (manwon >= 150000) return { bg: '#dc2626', border: '#fca5a5' }
  if (manwon >= 100000) return { bg: '#ea580c', border: '#fdba74' }
  if (manwon >= 60000)  return { bg: '#ca8a04', border: '#fde68a' }
  return { bg: '#16a34a', border: '#86efac' }
}

function formatPrice(manwon) {
  if (manwon >= 10000) return `${(manwon / 10000).toFixed(1)}억`
  return `${manwon.toLocaleString()}만`
}

function createMarkerIcon(p, isSelected) {
  const { bg, border } = priceColor(p.price)
  const outline = isSelected ? '#fff' : border
  const scale = isSelected ? 'scale(1.2)' : 'scale(1)'
  // 재건축 별: 정보몽땅(보라) 우선, AI추정만(주황). 준공은 제외
  const official = p.redev_stage && p.redev_stage !== '준공'
  const aiOnly = !p.redev_stage && p.redev_ai_stage && p.redev_ai_stage !== '준공'
  const starColor = official ? '#a855f7' : (aiOnly ? '#f59e0b' : null)
  const starTitle = official ? `재건축: ${p.redev_stage}` : `재건축 추정(AI): ${p.redev_ai_stage}`
  const star = starColor
    ? `<div title="${starTitle}" style="position:absolute;right:-10px;top:-14px;z-index:5;
                  width:20px;height:20px;line-height:0;
                  filter:drop-shadow(0 1px 3px rgba(0,0,0,0.5));">
          <svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">
            <polygon points="12,2 15,9 22,9.5 17,14.5 18.5,22 12,18 5.5,22 7,14.5 2,9.5 9,9"
                     fill="${starColor}" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/>
          </svg>
       </div>`
    : ''
  return L.divIcon({
    html: `
      <div style="position:relative;display:inline-block;line-height:0;transform:${scale};transform-origin:center bottom;">
        ${star}
        <div style="position:absolute;left:50%;top:-6px;transform:translateX(-50%);width:0;height:0;
                    border-left:10px solid transparent;border-right:10px solid transparent;
                    border-bottom:9px solid ${outline};z-index:1;"></div>
        <div style="position:absolute;left:50%;top:-4px;transform:translateX(-50%);width:0;height:0;
                    border-left:8px solid transparent;border-right:8px solid transparent;
                    border-bottom:7px solid ${bg};z-index:2;"></div>
        <div style="background:${bg};color:#fff;padding:3px 8px;font-size:11px;font-weight:700;
                    white-space:nowrap;border:2px solid ${outline};border-radius:0 0 5px 5px;
                    box-shadow:0 2px 6px rgba(0,0,0,0.3);line-height:1;">${formatPrice(p.price)}</div>
      </div>`,
    className: '',
    iconAnchor: [28, 22],
  })
}

const SCHOOL_STYLE = {
  '초': { color: '#2563eb', label: '초' },
  '중': { color: '#16a34a', label: '중' },
  '고': { color: '#ea580c', label: '고' },
}

// 노후도 → 색 (빨강=노후 후보 / 초록=신축)
function nohuColor(r) {
  if (r >= 70) return '#dc2626'
  if (r >= 60) return '#ea580c'
  if (r >= 45) return '#ca8a04'
  return '#16a34a'
}

const NaverMap = forwardRef(function NaverMap({ properties, redevZones = [], selectedId, onMarkerClick, onBoundsChange }, ref) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markersRef = useRef([])   // [{marker, id}]
  const zoneLayerRef = useRef(null)   // 정비사업 구역 마커 레이어
  const subwayLayerRef = useRef(null)
  const schoolLayerRef = useRef(null)
  const schoolDataRef = useRef(null)
  const nohuLayerRef = useRef(null)
  const nohuDataRef = useRef(null)
  const [showSubway, setShowSubway] = useState(false)
  const [showSchool, setShowSchool] = useState(false)
  const [showNohu, setShowNohu] = useState(false)

  // 부모에서 flyTo / fitTo 호출 가능하도록 노출
  useImperativeHandle(ref, () => ({
    flyTo(lat, lng, zoom = 13) {
      mapInstance.current?.flyTo([lat, lng], zoom, { duration: 0.8 })
    },
    fitTo(points) {
      if (!mapInstance.current || !points || !points.length) return
      if (points.length === 1) {
        mapInstance.current.flyTo([points[0].lat, points[0].lng], 16, { duration: 0.8 })
        return
      }
      const bounds = L.latLngBounds(points.map(p => [p.lat, p.lng]))
      mapInstance.current.flyToBounds(bounds, {
        padding: [60, 60], maxZoom: 15, duration: 0.8,
      })
    },
  }))

  // 지도 초기화 (한 번만)
  useEffect(() => {
    if (mapInstance.current) return

    mapInstance.current = L.map(mapRef.current, {
      center: [37.5326, 127.0246],
      zoom: 12,
      minZoom: 6,                // 한반도 전체 정도까지 줌아웃 허용
      maxZoom: 19,
      zoomControl: true,
      preferCanvas: true,
      // 모바일 핀치줌 명시
      touchZoom: true,
      tap: true,
      tapTolerance: 15,
      bounceAtZoomLimits: false,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
      minZoom: 6,
    }).addTo(mapInstance.current)

    let boundsTimer = null
    const emitBounds = () => {
      clearTimeout(boundsTimer)
      boundsTimer = setTimeout(() => {
        const b = mapInstance.current.getBounds()
        if (onBoundsChange) onBoundsChange({
          north: b.getNorth(), south: b.getSouth(),
          east:  b.getEast(),  west:  b.getWest(),
        })
      }, 50)
    }

    mapInstance.current.on('moveend', emitBounds)
    mapInstance.current.on('zoomend', emitBounds)
    mapInstance.current.whenReady(emitBounds)

    return () => {
      clearTimeout(boundsTimer)
      mapInstance.current?.remove()
      mapInstance.current = null
    }
  }, [onBoundsChange])

  // 마커 갱신 (properties 또는 selectedId 변경 시)
  useEffect(() => {
    if (!mapInstance.current) return

    // 기존 마커 제거
    markersRef.current.forEach(({ marker }) => marker.remove())
    markersRef.current = []

    // 새 마커 추가 (서버에서 이미 뷰포트 필터링 완료 → 전부 지도에 추가)
    markersRef.current = properties.map(p => {
      const isSelected = p.id === selectedId
      const marker = L.marker([p.lat, p.lng], {
        icon: createMarkerIcon(p, isSelected),
        zIndexOffset: isSelected ? 1000 : 0,
      })
      marker.on('click', () => onMarkerClick(p))
      marker.addTo(mapInstance.current)
      return { marker, id: p.id }
    })
  }, [properties, selectedId, onMarkerClick])

  // 정비사업 구역 마커 (검색 결과)
  useEffect(() => {
    if (!mapInstance.current) return
    zoneLayerRef.current?.remove()
    zoneLayerRef.current = null
    if (!redevZones.length) return
    const group = L.layerGroup()
    redevZones.forEach(z => {
      const isRedev = (z.type || '').includes('재건축')
      const color = isRedev ? '#7c3aed' : '#dc2626'  // 재건축 보라 / 재개발 빨강
      const shortNm = z.name.length > 14 ? z.name.slice(0, 14) + '…' : z.name
      const unitsBadge = z.units
        ? `<span style="color:${color};font-weight:800;margin-left:5px;">${z.units.toLocaleString()}세대</span>`
        : ''
      const icon = L.divIcon({
        className: '',
        html: `<div style="position:relative;transform:translate(-50%,-100%);white-space:nowrap;display:flex;flex-direction:column;align-items:center;">
            <div style="font-size:34px;line-height:1;filter:drop-shadow(0 2px 3px rgba(0,0,0,.45));">🏗️</div>
            <div style="background:#fff;color:#111;font-size:12px;font-weight:700;padding:3px 9px;margin-top:-2px;
                        border-radius:12px;border:2px solid ${color};box-shadow:0 2px 6px rgba(0,0,0,.3);">
              ${shortNm}${unitsBadge}
            </div>
            <div style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;
                        border-top:6px solid ${color};"></div>
          </div>`,
        iconSize: [0, 0],
      })
      const m = L.marker([z.lat, z.lng], { icon, zIndexOffset: 2000 })
      m.bindPopup(
        `<div style="font-size:12px;line-height:1.6">
           <b>${z.name}</b><br/>
           <span style="color:#666">${z.type} · ${z.stage}</span><br/>
           ${z.units ? `<span style="color:${color};font-weight:700">${z.units.toLocaleString()}세대 예정</span><br/>` : ''}
           <span style="color:#999">${z.gu} ${z.jibun || ''}</span>
         </div>`)
      m.addTo(group)
    })
    group.addTo(mapInstance.current)
    zoneLayerRef.current = group
  }, [redevZones])

  // 지하철 노선도
  useEffect(() => {
    if (!mapInstance.current) return
    subwayLayerRef.current?.remove()
    subwayLayerRef.current = null
    if (!showSubway) return

    const group = L.layerGroup()
    SUBWAY_LINES.forEach(line => {
      const isDashed = line.dashed   // 착공·예정 노선
      L.polyline(line.stations.map(([lat, lng]) => [lat, lng]), {
        color: line.color,
        weight: isDashed ? 4 : 3,
        opacity: isDashed ? 0.9 : 0.75,
        dashArray: isDashed ? '10, 8' : null,
      }).addTo(group)

      line.stations.forEach(([lat, lng, name]) => {
        const circle = L.circleMarker([lat, lng], {
          radius: 4,
          color: line.color,
          fillColor: isDashed ? line.color : '#fff',
          fillOpacity: 1,
          weight: 2,
        })
        if (name) {
          circle.bindTooltip(name, {
            permanent: true,
            direction: 'top',
            offset: [0, -6],
            className: 'subway-label',
          })
        }
        circle.addTo(group)
      })
    })
    group.addTo(mapInstance.current)
    subwayLayerRef.current = group
  }, [showSubway])

  // 학교 표시
  useEffect(() => {
    if (!mapInstance.current) return
    schoolLayerRef.current?.remove()
    schoolLayerRef.current = null
    if (!showSchool) return

    const render = (schools) => {
      const group = L.layerGroup()
      schools.forEach(s => {
        const style = SCHOOL_STYLE[s.kind] ?? { color: '#6b7280', label: '?' }
        const marker = L.marker([s.lat, s.lng], {
          icon: L.divIcon({
            html: `<div style="background:${style.color};color:#fff;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.4);">${style.label}</div>`,
            className: '',
            iconAnchor: [9, 9],
          }),
        })
        marker.bindTooltip(s.name, {
          direction: 'top', offset: [0, -10], className: 'subway-label',
        })
        marker.addTo(group)
      })
      group.addTo(mapInstance.current)
      schoolLayerRef.current = group
    }

    if (schoolDataRef.current) {
      render(schoolDataRef.current)
    } else {
      fetch('/api/schools')
        .then(r => r.json())
        .then(d => { schoolDataRef.current = d.schools ?? []; if (showSchool) render(schoolDataRef.current) })
        .catch(() => {})
    }
  }, [showSchool])

  // 노후도 / 재개발 예측 레이어 (동별 원)
  useEffect(() => {
    if (!mapInstance.current) return
    nohuLayerRef.current?.remove()
    nohuLayerRef.current = null
    if (!showNohu) return

    const render = (dongs) => {
      const group = L.layerGroup()
      dongs.forEach(d => {
        if (!d.lat || !d.lng) return
        const color = nohuColor(d.nohu)
        const radius = Math.min(38, 10 + Math.sqrt(d.buildings))   // 건물 수 ∝ 크기
        const isCand = d.verdict === '후보'
        const circle = L.circleMarker([d.lat, d.lng], {
          radius, color: '#fff', weight: isCand ? 3 : 1.5,
          fillColor: color, fillOpacity: 0.55,
        })
        circle.bindTooltip(
          `<div style="text-align:center;font-weight:700;font-size:11px;color:#111">${d.dong}<br/>${d.nohu}%</div>`,
          { permanent: true, direction: 'center', className: 'nohu-label' })
        const badge = isCand
          ? `<span style="color:#dc2626;font-weight:800">🎯 재개발 후보 (미지정)</span>`
          : d.verdict === '진행중'
            ? `<span style="color:#7c3aed;font-weight:700">정비구역 진행/지정</span>`
            : d.verdict === '경계'
              ? `<span style="color:#ca8a04;font-weight:700">경계</span>`
              : `<span style="color:#16a34a;font-weight:700">신축 위주</span>`
        circle.bindPopup(
          `<div style="font-size:12px;line-height:1.7">
             <b>${d.dong}</b> · ${d.kind}<br/>
             노후도 <b style="color:${color}">${d.nohu}%</b> (건물 ${d.buildings.toLocaleString()}채 중 ${d.old.toLocaleString()}채 노후)<br/>
             평균 연식 <b>${d.avg_age}년</b><br/>
             ${badge}
           </div>`)
        circle.addTo(group)
      })
      group.addTo(mapInstance.current)
      nohuLayerRef.current = group
    }

    if (nohuDataRef.current) {
      render(nohuDataRef.current)
    } else {
      fetch('/api/redev-predict')
        .then(r => r.json())
        .then(d => { nohuDataRef.current = d.dongs ?? []; if (showNohu) render(nohuDataRef.current) })
        .catch(() => {})
    }
  }, [showNohu])

  return (
    <div className="relative h-full w-full">
      <div ref={mapRef} className="h-full w-full" />

      {/* 토글 버튼들 */}
      <div className="absolute top-3 right-3 z-[1000] flex flex-col items-end gap-1.5">
        <button
          onClick={() => setShowSubway(v => !v)}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold shadow transition-all border ${
            showSubway
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300'
          }`}
        >
          🚇 노선도 {showSubway ? 'ON' : 'OFF'}
        </button>
        <button
          onClick={() => setShowSchool(v => !v)}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold shadow transition-all border ${
            showSchool
              ? 'bg-emerald-600 text-white border-emerald-600'
              : 'bg-white text-gray-600 border-gray-200 hover:border-emerald-300'
          }`}
        >
          🏫 학교 {showSchool ? 'ON' : 'OFF'}
        </button>
        <button
          onClick={() => setShowNohu(v => !v)}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold shadow transition-all border ${
            showNohu
              ? 'bg-rose-600 text-white border-rose-600'
              : 'bg-white text-gray-600 border-gray-200 hover:border-rose-300'
          }`}
        >
          🏚️ 노후도 {showNohu ? 'ON' : 'OFF'}
        </button>
      </div>

      {/* 노선 범례 */}
      {showSubway && (
        <div className="absolute top-24 right-3 z-[1000] rounded-xl border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow backdrop-blur-sm">
          {SUBWAY_LINES.map(line => (
            <div key={line.id} className="flex items-center gap-1.5 mb-0.5 last:mb-0">
              {line.dashed ? (
                <span className="inline-block h-2 w-4 rounded-full"
                      style={{ background: `repeating-linear-gradient(90deg, ${line.color} 0 3px, transparent 3px 5px)` }} />
              ) : (
                <span style={{ background: line.color }} className="inline-block h-2 w-4 rounded-full" />
              )}
              <span className="text-gray-700">{line.name}</span>
            </div>
          ))}
        </div>
      )}

      {/* 학교 범례 */}
      {showSchool && (
        <div className="absolute right-3 z-[1000] rounded-xl border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow backdrop-blur-sm"
             style={{ top: showSubway ? '13.5rem' : '6rem' }}>
          {[
            { color: '#2563eb', label: '초등학교' },
            { color: '#16a34a', label: '중학교' },
            { color: '#ea580c', label: '고등학교' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-1.5 mb-0.5 last:mb-0">
              <span style={{ background: color }} className="inline-block h-3 w-3 rounded-full" />
              <span className="text-gray-700">{label}</span>
            </div>
          ))}
        </div>
      )}

      {/* 노후도 범례 */}
      {showNohu && (
        <div className="absolute right-3 z-[1000] rounded-xl border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow backdrop-blur-sm"
             style={{ top: showSubway ? '20rem' : (showSchool ? '12rem' : '6rem') }}>
          <p className="mb-1.5 font-semibold text-gray-600">🏚️ 노후도 (동별)</p>
          {[
            { color: '#dc2626', label: '70%+ 매우노후' },
            { color: '#ea580c', label: '60~70% 후보권' },
            { color: '#ca8a04', label: '45~60% 경계' },
            { color: '#16a34a', label: '~45% 신축' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-1.5 mb-0.5 last:mb-0">
              <span style={{ background: color }} className="inline-block h-2.5 w-2.5 rounded-full" />
              <span className="text-gray-700">{label}</span>
            </div>
          ))}
          <p className="mt-1.5 pt-1.5 border-t border-gray-100 text-[11px] text-gray-400">흰 굵은테 = 미지정 후보 🎯</p>
        </div>
      )}

      {/* 가격 범례 */}
      <div className="absolute bottom-14 left-3 z-[1000] rounded-xl border border-gray-200 bg-white/90 px-3 py-2 text-xs shadow backdrop-blur-sm">
        <p className="mb-1.5 font-semibold text-gray-600">가격 범례</p>
        {[
          { color: '#dc2626', label: '15~20억' },
          { color: '#ea580c', label: '10~15억' },
          { color: '#ca8a04', label: '6~10억' },
          { color: '#16a34a', label: '~6억' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5 mb-0.5">
            <span style={{ background: color }} className="inline-block h-2.5 w-2.5 rounded-full" />
            <span className="text-gray-600">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
})

export default NaverMap
