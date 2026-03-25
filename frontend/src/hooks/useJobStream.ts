import { useEffect, useRef, useState } from 'react'

export interface AgentState {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stalled'
  last_heartbeat: string | null
  error: string | null
}

export interface JobStream {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  agents: Record<string, AgentState>
  result: any | null
  error: string | null
}

export function useJobStream(jobId: string | null) {
  const [data, setData] = useState<JobStream | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!jobId) return
    const token = localStorage.getItem('token')
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    const url = `${protocol}://${host}/api/v1/ws/jobs/${jobId}?token=${token}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onmessage = (e) => {
      try { setData(JSON.parse(e.data)) } catch {}
    }
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    return () => { ws.close() }
  }, [jobId])

  return { data, connected }
}
