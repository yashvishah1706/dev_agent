import { CheckCircle2, XCircle, Loader2, Clock, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { AgentState } from '../hooks/useJobStream'

const AGENT_LABELS: Record<string, string> = {
  repo_scanner:        'Repo Scanner',
  dependency_analyzer: 'Dependency Analyzer',
  environment_builder: 'Environment Builder',
  code_explainer:      'Code Explainer (AI)',
  test_runner:         'Test Runner',
}

interface Props {
  agents: Record<string, AgentState>
}

export function AgentPanel({ agents }: Props) {
  const allAgents = Object.keys(AGENT_LABELS)

  return (
    <div className="space-y-2">
      {allAgents.map((key) => {
        const agent = agents[key]
        const status = agent?.status ?? 'pending'
        return (
          <div
            key={key}
            className={clsx(
              'flex items-center gap-3 px-4 py-3 rounded-lg border transition-all',
              status === 'completed' && 'border-green-800 bg-green-950/40',
              status === 'running'   && 'border-brand-700 bg-brand-950/40',
              status === 'failed'    && 'border-red-800 bg-red-950/40',
              status === 'stalled'   && 'border-yellow-800 bg-yellow-950/40',
              status === 'pending'   && 'border-gray-800 bg-gray-900/40',
            )}
          >
            <StatusIcon status={status} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-200">{AGENT_LABELS[key]}</p>
              {agent?.error && (
                <p className="text-xs text-red-400 truncate">{agent.error}</p>
              )}
            </div>
            <span className={clsx(
              'badge text-xs',
              status === 'completed' && 'bg-green-900 text-green-300',
              status === 'running'   && 'bg-brand-900 text-brand-300',
              status === 'failed'    && 'bg-red-900 text-red-300',
              status === 'stalled'   && 'bg-yellow-900 text-yellow-300',
              status === 'pending'   && 'bg-gray-800 text-gray-400',
            )}>
              {status}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
  if (status === 'running')   return <Loader2 className="w-4 h-4 text-brand-400 animate-spin shrink-0" />
  if (status === 'failed')    return <XCircle className="w-4 h-4 text-red-400 shrink-0" />
  if (status === 'stalled')   return <AlertTriangle className="w-4 h-4 text-yellow-400 shrink-0" />
  return <Clock className="w-4 h-4 text-gray-600 shrink-0" />
}
