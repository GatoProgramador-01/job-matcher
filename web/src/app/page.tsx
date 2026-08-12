'use client'

import { useState } from 'react'
import { JobCard } from '@/components/JobCard'
import { JobModal } from '@/components/JobModal'
import { PipelineStatus } from '@/components/PipelineStatus'
import { ScoreFilter } from '@/components/ScoreFilter'
import type { Job } from '@/types/job'

const JOBS_PER_PAGE = 8

interface TokenStats {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cache_hits: number
  cache_misses: number
  saved_tokens: number
  estimated_cost_usd: number
  estimated_saved_cost_usd: number
}

type Status = 'idle' | 'running' | 'done' | 'error'
type FilterValue = 'all' | 70 | 40

export default function Home() {
  const [status, setStatus] = useState<Status>('idle')
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [doneNodes, setDoneNodes] = useState<string[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const [tokenStats, setTokenStats] = useState<TokenStats | null>(null)
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [scoreFilter, setScoreFilter] = useState<FilterValue>('all')

  const filteredJobs = scoreFilter === 'all' ? jobs : jobs.filter((j) => j.score >= scoreFilter)
  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / JOBS_PER_PAGE))
  const visibleJobs = filteredJobs.slice(
    (currentPage - 1) * JOBS_PER_PAGE,
    currentPage * JOBS_PER_PAGE
  )

  function handleFilterChange(v: FilterValue) {
    setScoreFilter(v)
    setCurrentPage(1)
  }

  async function runMatcher() {
    setStatus('running')
    setActiveNode(null)
    setDoneNodes([])
    setJobs([])
    setError(null)
    setTokenStats(null)
    setCurrentPage(1)
    setScoreFilter('all')

    try {
      const resp = await fetch('/api/run', { method: 'POST' })
      if (!resp.ok || !resp.body) throw new Error('Backend unreachable')

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = JSON.parse(line.slice(6))
          if (data.error) {
            setError(data.error)
            setStatus('error')
            return
          }
          if (data.token_stats && Object.keys(data.token_stats).length > 0) {
            setTokenStats(data.token_stats)
          }
          if (data.node) setActiveNode(data.node)
          if (data.done_node) setDoneNodes((prev) => [...prev, data.done_node])
          if (data.jobs) {
            setJobs(data.jobs)
            setStatus('done')
            setActiveNode(null)
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
      setStatus('error')
    }
  }

  return (
    <main className="max-w-5xl mx-auto px-4 py-12">
      <div className="mb-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Job Matcher</h1>
          <p className="text-gray-400 mt-1">
            LangGraph + DeepSeek · MongoDB Storage & Cache · Top matches ranked for your profile
          </p>
        </div>
        {tokenStats && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 text-xs text-gray-300 flex flex-wrap gap-4">
            <div><span className="text-gray-500 block">LLM Cost</span><span className="font-semibold text-green-400">${tokenStats.estimated_cost_usd.toFixed(5)}</span></div>
            <div><span className="text-gray-500 block">Tokens Used</span><span className="font-semibold text-white">{tokenStats.total_tokens.toLocaleString()}</span></div>
            <div><span className="text-gray-500 block">Mongo Cache Hits</span><span className="font-semibold text-indigo-400">{tokenStats.cache_hits} jobs</span></div>
            <div><span className="text-gray-500 block">Saved Tokens</span><span className="font-semibold text-purple-400">{tokenStats.saved_tokens.toLocaleString()}</span></div>
          </div>
        )}
      </div>

      <div className="flex flex-col items-center gap-6 mb-10">
        <button
          onClick={runMatcher}
          disabled={status === 'running'}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold px-8 py-3 rounded-xl text-lg transition-colors"
        >
          {status === 'running' ? 'Running pipeline...' : 'Find matching jobs'}
        </button>
        {status === 'running' && <PipelineStatus activeNode={activeNode} doneNodes={doneNodes} />}
        {status === 'error' && <p className="text-red-400 text-sm">Error: {error}</p>}
      </div>

      {jobs.length > 0 && (
        <div>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
            <h2 className="text-lg font-semibold text-gray-300">
              {filteredJobs.length} of {jobs.length} matches
            </h2>
            <ScoreFilter value={scoreFilter} onChange={handleFilterChange} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {visibleJobs.map((job, i) => (
              <JobCard
                key={job.apply_url}
                job={job}
                rank={(currentPage - 1) * JOBS_PER_PAGE + i + 1}
                onSelect={setSelectedJob}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 mt-6">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors"
              >
                Previous
              </button>
              <span className="text-gray-400 text-sm">Page {currentPage} of {totalPages}</span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}

      <JobModal job={selectedJob} onClose={() => setSelectedJob(null)} />
    </main>
  )
}
