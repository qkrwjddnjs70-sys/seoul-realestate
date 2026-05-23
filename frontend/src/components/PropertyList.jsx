import PropertyCard from './PropertyCard'

export default function PropertyList({ properties, selectedId, onSelect, loading }) {
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400 text-sm">
        검색 중...
      </div>
    )
  }

  if (properties.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-gray-400">
        <p className="text-4xl mb-2">🔍</p>
        <p className="text-sm">조건에 맞는 매물이 없습니다</p>
        <p className="text-xs mt-1 text-gray-300">필터를 조정해보세요</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 overflow-y-auto p-4">
      {properties.map(p => (
        <PropertyCard
          key={p.id}
          property={p}
          selected={p.id === selectedId}
          onClick={onSelect}
        />
      ))}
    </div>
  )
}
