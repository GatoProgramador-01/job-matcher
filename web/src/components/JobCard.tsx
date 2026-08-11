interface Job {
  score: number
  title: string
  company: string
  posted_at: string
  apply_url: string
  skills: string[]
  seniority: string | null
}

export function JobCard({ job, rank }: { job: Job; rank: number }) {
  const scoreColor =
    job.score >= 70 ? 'text-green-400' :
    job.score >= 40 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-3 hover:border-gray-600 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-gray-500 text-sm font-mono">
          #{rank}
        </div>
        <span className={`text-2xl font-bold font-mono ${scoreColor}`}>
          {job.score.toFixed(0)}
        </span>
      </div>

      <div>
        <h3 className="font-semibold text-white text-base leading-tight">{job.title}</h3>
        <p className="text-gray-400 text-sm mt-0.5">{job.company}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {job.skills.slice(0, 5).map((s) => (
          <span key={s} className="bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">
            {s}
          </span>
        ))}
      </div>

      <div className="flex items-center justify-between mt-auto pt-2 border-t border-gray-800">
        <span className="text-gray-500 text-xs">{job.posted_at ?? 'unknown date'}</span>
        <a
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
        >
          Apply
        </a>
      </div>
    </div>
  )
}
