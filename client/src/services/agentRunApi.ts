import { API_BASE_URL } from './api'

export interface AgentActionRequest {
  action: string
  params?: Record<string, unknown>
  confirm?: boolean
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(
      (errorData as { detail?: string }).detail || `Agent request failed: ${response.status}`
    )
  }

  return (await response.json()) as T
}

export async function runAgentLoop<T = Record<string, unknown>>(
  payload: Record<string, unknown>
): Promise<T> {
  return requestJson<T>(`${API_BASE_URL}/agent/run-loop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function resumeAgentSession<T = Record<string, unknown>>(
  payload: Record<string, unknown>
): Promise<T> {
  return requestJson<T>(`${API_BASE_URL}/agent/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function resumeAgentFromTimelineEvent<T = Record<string, unknown>>(
  payload: Record<string, unknown>
): Promise<T> {
  return requestJson<T>(`${API_BASE_URL}/agent/resume-from-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function executeAgentAction<T = Record<string, unknown>>(
  payload: AgentActionRequest
): Promise<T> {
  return requestJson<T>(`${API_BASE_URL}/agent/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
