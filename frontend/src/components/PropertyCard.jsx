export default function PropertyCard({ property, selected, onClick }) {
  const price = (property.price / 10000).toFixed(1)
  const age = new Date().getFullYear() - property.built_year

  return (
    <div
      onClick={() => onClick(property)}
      className={`cursor-pointer rounded-xl border p-4 transition-all hover:shadow-md ${
        selected ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-white hover:border-blue-300'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-gray-900">{property.name}</p>
          <p className="truncate text-xs text-gray-500 mt-0.5">{property.address}</p>
        </div>
        <span className="shrink-0 text-lg font-bold text-blue-600">{price}억</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <Tag icon="🚇" label={`${property.nearest_subway}역 도보 ${property.walk_minutes}분`} />
        <Tag icon="🏢" label={`${property.units.toLocaleString()}세대`} />
        <Tag icon="📅" label={`${property.built_year}년 (${age}년차)`} />
        <Tag icon="📐" label={`${property.area_m2}㎡`} />
      </div>

      {property.bus_routes.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {property.bus_routes.map(r => (
            <span key={r} className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">
              🚌 {r}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Tag({ icon, label }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
      {icon} {label}
    </span>
  )
}
