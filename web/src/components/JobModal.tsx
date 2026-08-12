'use client'

import { useEffect } from 'react'
import type { Job } from '@/types/job'

interface Props {
  job: Job | null
  onClose: () => void
}

const BREAKDOWN_BARS = [
  { key: 'stack' as const, label: 'Stack match', max: 40, color: 'bg-indigo-500' },
  { key: 'seniority' as const, label: 'Seniority', max: 40, color: 'bg-purple-500' },
  { key: 'ai_bonus' as const, label: 'AI/GenAI bonus', max: 20, color: 'bg-emerald-500' },
  { key: 'recency' as const, label: 'Recency', max: 20, color: 'bg-sky-500' },
]

export function JobModal({ job, onClose }: Props) {
  useEffect(() => {
    if (!job) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [job, onClose])

  if (!job) return null

  const scoreColor =
    job.score >= 70 ? 'text-green-400' :
    job.score >= 40 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />
      <div className="relative z-10 w-full max-w-lg bg-gray-950 border-l border-gray-800 h-full overflow-y-auto flex flex-col">
        <div className="flex items-start justify-between gap-3 p-6 border-b border-gray-800">
          <div className="flex-1 min-w-0">
            <h2 id="modal-title" className="text-white font-semibold text-lg leading-tight">
              {job.title}
            </h2>
            <p className="text-gray-400 text-sm mt-0.5">{job.company}</p>
            {job.posted_at && (
              <p className="text-gray-600 text-xs mt-1">{job.posted_at}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xl leading-none flex-shrink-0"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="px-6 pt-5">
          <div className="flex items-baseline gap-2 mb-4">
            <span className={`text-4xl font-bold font-mono ${scoreColor}`}>
              {job.score.toFixed(0)}
            </span>
            <span className="text-gray-500 text-sm">/ 100</span>
          </div>

          {job.score_breakdown && (
            <div className="space-y-3 mb-6">
              {BREAKDOWN_BARS.map(({ key, label, max, color }) => {
                const value = job.score_breakdown![key]
                const displayValue = key === 'seniority' ? value + 20 : value
                const pct = Math.max(0, (displayValue / max) * 100)
                const isNeg = key === 'seniority' && value < 0
                return (
                  <div key={key}>
                    <div className="flex justify-between text-xs text-gray-400 mb-1">
                      <span>{label}</span>
                      <span className={isNeg ? 'text-red-400' : 'text-gray-300'}>
                        {value > 0 ? '+' : ''}{value.toFixed(1)}
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${isNeg ? 'bg-red-500' : color}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {job.skills.length > 0 && (
          <div className="px-6 mb-5">
            <h3 className="text-gray-400 text-xs font-semibold uppercase tracking-wider mb-2">Skills</h3>
            <div className="flex flex-wrap gap-1.5">
              {job.skills.map((s) => (
                <span key={s} className="bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">{s}</span>
              ))}
            </div>
          </div>
        )}

        {job.description && (
          <div className="px-6 mb-6 flex-1">
            <h3 className="text-gray-400 text-xs font-semibold uppercase tracking-wider mb-2">Description</h3>
            <div
              className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto pr-1"
              dangerouslySetInnerHTML={{ __html: job.description }}
            />
          </div>
        )}

        <div className="p-6 border-t border-gray-800 mt-auto">
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors"
          >
            Apply for this role
          </a>
        </div>
      </div>
    </div>
  )
}
