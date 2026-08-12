export interface ScoreBreakdown {
  stack: number
  seniority: number
  ai_bonus: number
  recency: number
}

export interface Job {
  score: number
  score_breakdown: ScoreBreakdown | null
  title: string
  company: string
  posted_at: string | null
  apply_url: string
  skills: string[]
  seniority: string | null
  description: string
}
