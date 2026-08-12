type FilterValue = 'all' | 70 | 40

interface Props {
  value: FilterValue
  onChange: (v: FilterValue) => void
}

const OPTIONS: { label: string; value: FilterValue }[] = [
  { label: 'All', value: 'all' },
  { label: '≥70', value: 70 },
  { label: '≥40', value: 40 },
]

export function ScoreFilter({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-gray-500 text-sm">Score:</span>
      <div className="flex rounded-lg overflow-hidden border border-gray-700">
        {OPTIONS.map((opt) => (
          <button
            key={String(opt.value)}
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1.5 text-sm font-medium transition-colors
              ${value === opt.value
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-900 text-gray-400 hover:bg-gray-800'
              }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}
