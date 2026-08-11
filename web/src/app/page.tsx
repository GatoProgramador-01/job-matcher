'use client'

import { useState } from 'react'
import { JobCard } from '@/components/JobCard'
import { PipelineStatus } from '@/components/PipelineStatus'

interface Job {
  score: number
  title: string
  company: string
  posted_at: string
  apply_url: string
  skills: string[]
  seniority: string | null
}

type Status = 'idle' | 'running' | 'done' | 'error'

export default function Home() {
  const [status, setStatus] = useState<Status>('idle')
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [doneNodes, setDoneNodes] = useState<string[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)

  async function runMatcher() {
    setStatus('running')
    setActiveNode(null)
    setDoneNodes([])
    setJobs([])
    setError(null)

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
          if (data.node) setActiveNode(data.node)
          if (data.done_node) setDoneNodes(prev => [...prev, data.done_node])
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
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white">Job Matcher</h1>
        <p className="text-gray-400 mt-1">
          LangGraph + DeepSeek · hiring.cafe · top 10 jobs ranked for your profile
        </p>
      </div>

      <div className="flex flex-col items-center gap-6 mb-10">
        <button
          onClick={runMatcher}
          disabled={status === 'running'}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed
            text-white font-semibold px-8 py-3 rounded-xl text-lg transition-colors"
        >
          {status === 'running' ? 'Running pipeline...' : 'Find matching jobs'}
        </button>

        {status === 'running' && (
          <PipelineStatus activeNode={activeNode} doneNodes={doneNodes} />
        )}

        {status === 'error' && (
          <p className="text-red-400 text-sm">Error: {error}</p>
        )}
      </div>

      {jobs.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-300 mb-4">
            Top {jobs.length} matches
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {jobs.map((job, i) => (
              <JobCard key={job.apply_url} job={job} rank={i + 1} />
            ))}
          </div>
        </div>
      )}
    </main>
  )
}
