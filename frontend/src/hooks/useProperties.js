import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'

const API = '/api/properties'

export function useProperties(filters, bounds) {
  const [properties, setProperties] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef(null)

  const fetchProperties = useCallback(async (f, b) => {
    setLoading(true)
    try {
      const params = {}
      if (f.maxWalkMinutes != null) params.max_walk_minutes = f.maxWalkMinutes
      if (f.minUnits != null)       params.min_units        = f.minUnits
      if (f.maxUnits != null)       params.max_units        = f.maxUnits
      if (f.minPrice != null)       params.min_price        = f.minPrice
      if (f.maxPrice != null)       params.max_price        = f.maxPrice
      if (f.minBuiltYear != null)   params.min_built_year   = f.minBuiltYear
      if (f.maxBuiltYear != null)   params.max_built_year   = f.maxBuiltYear
      if (f.subwayStation)          params.subway_station   = f.subwayStation
      if (f.aptName)                params.apt_name         = f.aptName
      if (f.hojaes?.length)         params.hojaes           = f.hojaes.join(',')
      if (f.maxTimeGangnam != null)     params.max_time_gangnam     = f.maxTimeGangnam
      if (f.maxTimeYeouido != null)     params.max_time_yeouido     = f.maxTimeYeouido
      if (f.maxTimeGwanghwamun != null) params.max_time_gwanghwamun = f.maxTimeGwanghwamun
      if (f.maxTimeSiccheong != null)   params.max_time_siccheong   = f.maxTimeSiccheong
      if (f.maxTimeHongdae != null)     params.max_time_hongdae     = f.maxTimeHongdae
      if (f.lawdCds?.length)            params.lawd_cd              = f.lawdCds.join(',')
      if (f.dongs?.length)              params.dong                 = f.dongs.join(',')
      if (f.areaBands?.length)          params.area_bands           = f.areaBands.join(',')
      if (f.redevStages?.length)        params.redev_stages         = f.redevStages.join(',')

      // 구/동 선택 시 bounds 필터 생략
      const useBounds = b && !(f.lawdCds?.length) && !(f.dongs?.length)

      // 지도 뷰포트 bounds + 중심 좌표 → 서버에 전달 (구 선택 시 생략)
      if (useBounds) {
        params.lat_min = b.south
        params.lat_max = b.north
        params.lng_min = b.west
        params.lng_max = b.east
        params.lat_center = (b.south + b.north) / 2
        params.lng_center = (b.west + b.east) / 2
        params.bounds_size = b.east - b.west   // 경도 범위 크기
      }

      const res = await axios.get(API, { params })
      setProperties(res.data.items)
      setTotal(res.data.total)
    } catch (e) {
      console.error('매물 조회 실패', e)
    } finally {
      setLoading(false)
    }
  }, [])

  // 필터 변경 시 즉시 재조회
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      fetchProperties(filters, bounds)
    }, 100)
  }, [filters, fetchProperties]) // eslint-disable-line react-hooks/exhaustive-deps

  // bounds 변경 시 300ms 디바운스 후 재조회
  useEffect(() => {
    if (!bounds) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      fetchProperties(filters, bounds)
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [bounds, fetchProperties]) // eslint-disable-line react-hooks/exhaustive-deps

  return { properties, total, loading }
}
