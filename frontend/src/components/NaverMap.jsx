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
  // 준공된 단지는 진행 끝났으므로 별 제외
  const inProgress = p.redev_stage && p.redev_stage !== '준공'
  const star = inProgress
    ? `<div title="재건축: ${p.redev_stage}" style="position:absolute;right:-10px;top:-14px;z-index:5;
                  width:20px;height:20px;line-height:0;
                  filter:drop-shadow(0 1px 3px rgba(0,0,0,0.5));">
          <svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">
            <polygon points="12,2 15,9 22,9.5 17,14.5 18.5,22 12,18 5.5,22 7,14.5 2,9.5 9,9"
                     fill="#a855f7" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/>
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

const NaverMap = forwardRef(function NaverMap({ properties, selectedId, onMarkerClick, onBoundsChange }, ref) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markersRef = useRef([])   // [{marker, id}]
  const subwayLayerRef = useRef(null)
  const schoolLayerRef = useRef(null)
  const schoolDataRef = useRef(null)
  const [showSubway, setShowSubway] = useState(false)
  const [showSchool, setShowSchool] = useState(false)

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
      zoomControl: true,
      preferCanvas: true,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
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

  // 지하철 노선도
  useEffect(() => {
    if (!mapInstance.current) return
    subwayLayerRef.current?.remove()
    subwayLayerRef.current = null
    if (!showSubway) return

    const group = L.layerGroup()
    SUBWAY_LINES.forEach(line => {
      L.polyline(line.stations.map(([lat, lng]) => [lat, lng]), {
        color: line.color, weight: 3, opacity: 0.75,
      }).addTo(group)

      line.stations.forEach(([lat, lng, name]) => {
        const circle = L.circleMarker([lat, lng], {
          radius: 4,
          color: line.color,
          fillColor: '#fff',
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
      </div>

      {/* 노선 범례 */}
      {showSubway && (
        <div className="absolute top-24 right-3 z-[1000] rounded-xl border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow backdrop-blur-sm">
          {SUBWAY_LINES.map(line => (
            <div key={line.id} className="flex items-center gap-1.5 mb-0.5 last:mb-0">
              <span style={{ background: line.color }} className="inline-block h-2 w-4 rounded-full" />
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
