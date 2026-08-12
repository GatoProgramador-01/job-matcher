import { test, expect } from '@playwright/test'

test.describe('Job Matcher home page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('renders title, subtitle, and button', async ({ page }) => {
    await expect(page).toHaveTitle('Job Matcher')
    await expect(page.getByRole('heading', { name: 'Job Matcher' })).toBeVisible()
    await expect(page.getByText('LangGraph + DeepSeek')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Find matching jobs' })).toBeVisible()
  })

  test('button is enabled in idle state', async ({ page }) => {
    const btn = page.getByRole('button', { name: 'Find matching jobs' })
    await expect(btn).toBeEnabled()
  })

  test('button disables and shows running label while pipeline runs', async ({ page }) => {
    // Mock the SSE stream so the test never needs a real backend
    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        // Emit a single node event then leave stream open briefly
        body: 'data: {"node":"fetch"}\n\ndata: {"done_node":"fetch"}\n\n',
      })
    })

    const btn = page.getByRole('button', { name: /Find matching jobs|Running pipeline/ })
    await btn.click()

    // Button label changes to running state
    await expect(page.getByRole('button', { name: /Running pipeline/ })).toHaveText('Running pipeline...')
    await expect(page.getByRole('button', { name: /Running pipeline/ })).toBeDisabled()
  })

  test('pipeline status steps appear while running', async ({ page }) => {
    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: 'data: {"node":"fetch"}\n\ndata: {"done_node":"fetch"}\n\n',
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()

    // PipelineProgress renders all 5 node labels
    const progress = page.locator('[data-testid="pipeline-progress"]')
    for (const label of ['Fetch', 'Filter', 'Extract', 'Score', 'Rank']) {
      await expect(progress.getByText(label)).toBeVisible()
    }
  })

  test('shows error message when backend returns error event', async ({ page }) => {
    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: 'data: {"error":"HIRING_CAFE_URL not set"}\n\n',
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.getByText('HIRING_CAFE_URL not set')).toBeVisible()
    // Button returns to idle so user can retry
    await expect(page.getByRole('button', { name: 'Find matching jobs' })).toBeEnabled()
  })

  test('shows backend unreachable error when /api/run returns 502', async ({ page }) => {
    await page.route('/api/run', (route) =>
      route.fulfill({ status: 502, body: 'Backend error' })
    )

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.getByText('Backend unreachable')).toBeVisible()
  })

  test('renders job cards when pipeline completes', async ({ page }) => {
    const jobs = [
      {
        score: 87,
        title: 'Senior LangGraph Engineer',
        company: 'Acme AI',
        posted_at: '2026-08-10',
        apply_url: 'https://example.com/apply',
        skills: ['Python', 'LangGraph', 'FastAPI'],
        seniority: 'senior',
      },
    ]

    await page.route('/api/run', async (route) => {
      const events = [
        `data: {"node":"fetch"}\n\n`,
        `data: {"done_node":"fetch"}\n\n`,
        `data: {"node":"rank"}\n\n`,
        `data: {"done_node":"rank","jobs":${JSON.stringify(jobs)}}\n\n`,
      ].join('')

      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: events,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()

    await expect(page.getByText('Senior LangGraph Engineer')).toBeVisible()
    await expect(page.getByText('Acme AI')).toBeVisible()
    await expect(page.getByText('87')).toBeVisible()

    // Apply link has noopener noreferrer (security check)
    const applyLink = page.getByRole('link', { name: 'Apply' })
    await expect(applyLink).toHaveAttribute('rel', 'noopener noreferrer')
    await expect(applyLink).toHaveAttribute('target', '_blank')

    // Score heading visible
    await expect(page.getByText('1 of 1 matches')).toBeVisible()
  })

  test('score color: green for ≥70, yellow for ≥40, red for <40', async ({ page }) => {
    const makeJob = (score: number, title: string) => ({
      score, title, company: 'Co', posted_at: null,
      apply_url: 'https://example.com', skills: [], seniority: null,
    })

    await page.route('/api/run', async (route) => {
      const jobs = [makeJob(85, 'High Score'), makeJob(50, 'Mid Score'), makeJob(20, 'Low Score')]
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify(jobs)}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.getByText('High Score')).toBeVisible()

    // Green score
    const greenScore = page.locator('.text-green-400').first()
    await expect(greenScore).toBeVisible()

    // Yellow score
    const yellowScore = page.locator('.text-yellow-400').first()
    await expect(yellowScore).toBeVisible()

    // Red score
    const redScore = page.locator('.text-red-400').first()
    await expect(redScore).toBeVisible()
  })

  test.skip('real pipeline run (requires DEEPSEEK_API_KEY)', async ({ page }) => {
    test.setTimeout(120_000)
    await page.goto('/')
    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.locator('.text-green-400, .text-yellow-400, .text-red-400').first())
      .toBeVisible({ timeout: 90_000 })
  })

  test('clicking a job card opens the detail modal', async ({ page }) => {
    const job = {
      score: 87,
      score_breakdown: { stack: 30, seniority: 20, ai_bonus: 20, recency: 17 },
      title: 'Senior LangGraph Engineer',
      company: 'Acme AI',
      posted_at: '2026-08-10',
      apply_url: 'https://example.com/apply/1',
      skills: ['Python', 'LangGraph', 'FastAPI'],
      seniority: 'senior',
      description: 'Build LLM-powered multi-agent systems.',
    }

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify([job])}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.getByText('Senior LangGraph Engineer')).toBeVisible()

    // The card is role=button — click it
    await page.getByRole('button', { name: /Senior LangGraph Engineer/ }).click()

    // Modal appears with dialog role
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText('Build LLM-powered multi-agent systems.')).toBeVisible()
    await expect(page.getByText('Stack match')).toBeVisible()
  })

  test('modal closes when close button is clicked', async ({ page }) => {
    const job = {
      score: 75,
      score_breakdown: { stack: 25, seniority: 20, ai_bonus: 10, recency: 20 },
      title: 'Backend Developer',
      company: 'Co',
      posted_at: null,
      apply_url: 'https://example.com/apply/2',
      skills: ['Python'],
      seniority: 'mid',
      description: 'Python backend role.',
    }

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify([job])}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await page.getByRole('button', { name: /Backend Developer/ }).click()
    await expect(page.getByRole('dialog')).toBeVisible()

    // Close via the × button
    await page.getByRole('button', { name: 'Close' }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('score filter hides jobs below threshold', async ({ page }) => {
    const makeJob = (score: number, title: string, idx: number) => ({
      score,
      score_breakdown: { stack: score * 0.4, seniority: 10, ai_bonus: 5, recency: 5 },
      title,
      company: 'Co',
      posted_at: null,
      apply_url: `https://example.com/apply/${idx}`,
      skills: [],
      seniority: null,
      description: '',
    })

    const jobs = [makeJob(85, 'High Score Job', 1), makeJob(30, 'Low Score Job', 2)]

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify(jobs)}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.getByText('High Score Job')).toBeVisible()
    await expect(page.getByText('Low Score Job')).toBeVisible()

    // Apply ≥70 filter
    await page.getByRole('button', { name: '≥70' }).click()

    await expect(page.getByText('High Score Job')).toBeVisible()
    await expect(page.getByText('Low Score Job')).not.toBeVisible()
  })

  test('pagination shows next page', async ({ page }) => {
    const jobs = Array.from({ length: 10 }, (_, i) => ({
      score: 70 + i,
      score_breakdown: { stack: 20, seniority: 20, ai_bonus: 15, recency: 15 },
      title: `Job ${i + 1}`,
      company: 'Co',
      posted_at: null,
      apply_url: `https://example.com/apply/${i + 1}`,
      skills: [],
      seniority: null,
      description: '',
    }))

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify(jobs)}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()

    await expect(page.getByText('Job 1', { exact: true })).toBeVisible()
    await expect(page.getByText('Job 10', { exact: true })).not.toBeVisible()
    await expect(page.getByText('Page 1 of 2')).toBeVisible()

    await page.getByRole('button', { name: 'Next', exact: true }).click()

    await expect(page.getByText('Job 10', { exact: true })).toBeVisible()
    await expect(page.getByText('Job 1', { exact: true })).not.toBeVisible()
    await expect(page.getByText('Page 2 of 2')).toBeVisible()

    await page.getByRole('button', { name: 'Previous', exact: true }).click()
    await expect(page.getByText('Page 1 of 2')).toBeVisible()
  })

  test('pipeline shows progress card when node_start received', async ({ page }) => {
    await page.route('/api/run', async (route) => {
      const body = [
        'data: {"node":"fetch","total":0}\n\n',
        'data: {"done_node":"fetch","token_stats":{}}\n\n',
      ].join('')
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body,
      })
    })

    await page.click('button:has-text("Find matching jobs")')
    await expect(page.locator('[data-testid="pipeline-progress"]')).toBeVisible()
  })

  test('extract progress bar advances on job_progress events', async ({ page }) => {
    const events = [
      'data: {"node":"extract","total":10}\n\n',
      'data: {"type":"job_progress","index":1,"total":10,"title":"Senior Dev @ Acme","skills":["Python","FastAPI"],"tokens":300,"cost":0.0003,"cached":false}\n\n',
      'data: {"type":"job_progress","index":2,"total":10,"title":"Mid Dev @ Beta","skills":["Go"],"tokens":280,"cost":0.00028,"cached":false}\n\n',
      'data: {"type":"job_progress","index":3,"total":10,"title":"Junior Dev @ Gamma","skills":["Java"],"tokens":270,"cost":0.00027,"cached":false}\n\n',
    ].join('')

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: events,
      })
    })

    await page.click('button:has-text("Find matching jobs")')
    await expect(page.locator('[data-testid="pipeline-progress"]')).toBeVisible()
    await expect(page.locator('text=3/10').first()).toBeVisible()
    await expect(page.locator('text=Junior Dev @ Gamma')).toBeVisible()
  })

  test('token counter updates on job_progress events', async ({ page }) => {
    const events = [
      'data: {"node":"extract","total":5}\n\n',
      'data: {"type":"job_progress","index":1,"total":5,"title":"Dev A","skills":[],"tokens":200,"cost":0.0002,"cached":false}\n\n',
      'data: {"type":"job_progress","index":2,"total":5,"title":"Dev B","skills":[],"tokens":200,"cost":0.0002,"cached":false}\n\n',
    ].join('')

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: events,
      })
    })

    await page.click('button:has-text("Find matching jobs")')
    await expect(page.locator('[data-testid="pipeline-progress"]')).toBeVisible()
    // 200 + 200 = 400 tokens
    await expect(page.locator('text=400')).toBeVisible()
  })

  test('progress card disappears and job cards appear on done', async ({ page }) => {
    const mockJob = {
      score: 82.5,
      score_breakdown: { stack: 40, seniority: 15, ai_bonus: 20, recency: 7.5 },
      title: 'Senior Engineer',
      company: 'TechCorp',
      posted_at: '2026-08-10',
      apply_url: 'https://techcorp.com/jobs/1',
      skills: ['Python', 'FastAPI'],
      seniority: 'senior',
      description: 'A great role.',
    }

    const events = [
      'data: {"node":"rank","total":0}\n\n',
      `data: {"done_node":"rank","jobs":[${JSON.stringify(mockJob)}],"token_stats":{"total_tokens":1200,"cache_hits":2,"cache_misses":3,"estimated_cost_usd":0.00145,"prompt_tokens":900,"completion_tokens":300,"saved_tokens":1100,"estimated_saved_cost_usd":0.00040}}\n\n`,
    ].join('')

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: events,
      })
    })

    await page.click('button:has-text("Find matching jobs")')
    await expect(page.locator('[data-testid="pipeline-progress"]')).not.toBeVisible()
    await expect(page.locator('text=Senior Engineer')).toBeVisible()
  })
})
