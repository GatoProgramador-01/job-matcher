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

    const btn = page.getByRole('button')
    await btn.click()

    // Button label changes to running state
    await expect(btn).toHaveText('Running pipeline…')
    await expect(btn).toBeDisabled()
  })

  test('pipeline status steps appear while running', async ({ page }) => {
    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: 'data: {"node":"fetch"}\n\ndata: {"done_node":"fetch"}\n\n',
      })
    })

    await page.getByRole('button').click()

    // PipelineStatus renders all 5 step labels
    for (const label of ['Fetching jobs', 'Filtering', 'AI extraction', 'Scoring', 'Ranking']) {
      await expect(page.getByText(label)).toBeVisible()
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

    await page.getByRole('button').click()
    await expect(page.getByText('HIRING_CAFE_URL not set')).toBeVisible()
    // Button returns to idle so user can retry
    await expect(page.getByRole('button', { name: 'Find matching jobs' })).toBeEnabled()
  })

  test('shows backend unreachable error when /api/run returns 502', async ({ page }) => {
    await page.route('/api/run', (route) =>
      route.fulfill({ status: 502, body: 'Backend error' })
    )

    await page.getByRole('button').click()
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

    await page.getByRole('button').click()

    await expect(page.getByText('Senior LangGraph Engineer')).toBeVisible()
    await expect(page.getByText('Acme AI')).toBeVisible()
    await expect(page.getByText('87')).toBeVisible()

    // Apply link has noopener noreferrer (security check)
    const applyLink = page.getByRole('link', { name: 'Apply →' })
    await expect(applyLink).toHaveAttribute('rel', 'noopener noreferrer')
    await expect(applyLink).toHaveAttribute('target', '_blank')

    // Score heading visible
    await expect(page.getByText('Top 1 matches')).toBeVisible()
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

    await page.getByRole('button').click()
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
})
