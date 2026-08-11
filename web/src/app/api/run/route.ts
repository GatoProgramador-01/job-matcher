import { NextRequest } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

export async function POST(_req: NextRequest) {
  const upstream = await fetch(`${BACKEND_URL}/api/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_path: 'profile.json' }),
  })

  if (!upstream.ok || !upstream.body) {
    return new Response('Backend error', { status: 502 })
  }

  const reader = upstream.body.getReader()
  const stream = new ReadableStream({
    async start(controller) {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          controller.enqueue(value)
        }
      } finally {
        controller.close()
      }
    },
    cancel() { reader.cancel() },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Accel-Buffering': 'no',
    },
  })
}
