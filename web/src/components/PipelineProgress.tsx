import type { PipelineRun } from '@/types/pipeline'

interface Props {
  run: PipelineRun
}

function NodeIcon({ status }: { status: string }) {
  if (status === 'done') {
    return (
      <span className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center text-white text-xs font-bold shrink-0">
        ✓
      </span>
    )
  }
  if (status === 'running') {
    return (
      <span className="w-6 h-6 rounded-full bg-indigo-500 flex items-center justify-center shrink-0 animate-pulse">
        <span className="w-2 h-2 rounded-full bg-white" />
      </span>
    )
  }
  return (
    <span className="w-6 h-6 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center shrink-0" />
  )
}

export function PipelineProgress({ run }: Props) {
  const { nodes, currentJobTitle, currentJobSkills, extractProgress, totalTokens, totalCost } = run
  const extractNode = nodes.find((n) => n.id === 'extract')
  const showBar = extractNode?.status === 'running' && extractProgress.total > 0
  const barPct = showBar
    ? Math.round((extractProgress.done / extractProgress.total) * 100)
    : 0

  return (
    <div
      data-testid="pipeline-progress"
      className="w-full max-w-lg mx-auto bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4"
    >
      <p className="text-sm font-semibold text-gray-300 tracking-wide">Pipeline en progreso</p>

      <div className="space-y-3">
        {nodes.map((node) => (
          <div key={node.id}>
            <div className="flex items-center gap-3">
              <NodeIcon status={node.status} />
              <span
                className={`text-sm font-medium ${
                  node.status === 'done'
                    ? 'text-green-400'
                    : node.status === 'running'
                    ? 'text-indigo-300'
                    : 'text-gray-600'
                }`}
              >
                {node.label}
              </span>
              {node.summary && (
                <span className="text-xs text-gray-500 ml-auto truncate max-w-[200px]">
                  {node.summary}
                </span>
              )}
              {node.id === 'extract' && node.status === 'running' && extractProgress.total > 0 && (
                <span className="text-xs text-gray-500 ml-auto">
                  {extractProgress.done}/{extractProgress.total}
                </span>
              )}
            </div>

            {/* Progress bar — only for extract node while running */}
            {node.id === 'extract' && showBar && (
              <div className="ml-9 mt-2 space-y-1">
                <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                    style={{ width: `${barPct}%` }}
                  />
                </div>
                {currentJobTitle && (
                  <p className="text-xs text-gray-500 truncate">{currentJobTitle}</p>
                )}
                {currentJobSkills.length > 0 && (
                  <p className="text-xs text-gray-600 truncate">
                    {currentJobSkills.slice(0, 4).join(' · ')}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Token metrics bar */}
      <div className="border-t border-gray-800 pt-3 flex gap-5 text-xs text-gray-500">
        <span>
          Tokens: <span className="text-gray-300 font-medium">{totalTokens.toLocaleString()}</span>
        </span>
        <span>
          Costo: <span className="text-green-400 font-medium">${totalCost.toFixed(5)}</span>
        </span>
        {extractProgress.total > 0 && (
          <span>
            Jobs:{' '}
            <span className="text-indigo-300 font-medium">
              {extractProgress.done}/{extractProgress.total}
            </span>
          </span>
        )}
      </div>
    </div>
  )
}
