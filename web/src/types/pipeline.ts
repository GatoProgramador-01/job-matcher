export type NodeStatus = 'pending' | 'running' | 'done' | 'error'

export interface PipelineNode {
  id: string
  label: string
  status: NodeStatus
  summary: string | null
}

export interface ExtractProgress {
  done: number
  total: number
}

export interface PipelineRun {
  nodes: PipelineNode[]
  currentJobTitle: string | null
  currentJobSkills: string[]
  extractProgress: ExtractProgress
  totalTokens: number
  totalCost: number
}

export function makePipelineRun(): PipelineRun {
  return {
    nodes: [
      { id: 'fetch',   label: 'Fetch',   status: 'pending', summary: null },
      { id: 'filter',  label: 'Filter',  status: 'pending', summary: null },
      { id: 'extract', label: 'Extract', status: 'pending', summary: null },
      { id: 'score',   label: 'Score',   status: 'pending', summary: null },
      { id: 'rank',    label: 'Rank',    status: 'pending', summary: null },
    ],
    currentJobTitle: null,
    currentJobSkills: [],
    extractProgress: { done: 0, total: 0 },
    totalTokens: 0,
    totalCost: 0,
  }
}
