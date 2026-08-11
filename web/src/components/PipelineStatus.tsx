const NODES = ['fetch', 'filter', 'extract', 'score', 'rank'] as const
type NodeName = typeof NODES[number]

const NODE_LABELS: Record<NodeName, string> = {
  fetch: 'Fetching jobs',
  filter: 'Filtering',
  extract: 'AI extraction',
  score: 'Scoring',
  rank: 'Ranking',
}

interface Props {
  activeNode: string | null
  doneNodes: string[]
}

export function PipelineStatus({ activeNode, doneNodes }: Props) {
  return (
    <div className="flex items-center gap-2 py-4">
      {NODES.map((node, i) => {
        const done = doneNodes.includes(node)
        const active = activeNode === node
        return (
          <div key={node} className="flex items-center gap-2">
            <div className="flex flex-col items-center gap-1">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all
                ${done ? 'bg-green-500 text-white' : active ? 'bg-indigo-500 text-white animate-pulse' : 'bg-gray-800 text-gray-500'}`}>
                {done ? '✓' : i + 1}
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">{NODE_LABELS[node]}</span>
            </div>
            {i < NODES.length - 1 && (
              <div className={`h-0.5 w-8 mb-4 transition-colors ${done ? 'bg-green-500' : 'bg-gray-800'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}
