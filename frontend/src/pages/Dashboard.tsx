import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Terminal, Github, LogOut, Play, CheckCircle2,
  XCircle, Clock, FileCode2, Package, Layers,
  TestTube2, Cpu, Copy, Check,
} from 'lucide-react'
import { analyzeRepo, listJobs } from '../api'
import { useJobStream } from '../hooks/useJobStream'
import { AgentPanel } from '../components/AgentPanel'
import { DependencyGraph } from '../components/DependencyGraph'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import clsx from 'clsx'

export default function Dashboard() {
  const navigate = useNavigate()
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [pastJobs, setPastJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'overview' | 'deps' | 'env' | 'explain' | 'tests'>('overview')
  const [copied, setCopied] = useState(false)

  const { data: stream } = useJobStream(activeJobId)

  useEffect(() => {
    listJobs().then((d) => setPastJobs(d.jobs || [])).catch(() => {})
  }, [])

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!repoUrl) return
    setLoading(true)
    setError('')
    try {
      const data = await analyzeRepo(repoUrl, branch)
      setActiveJobId(data.job_id)
      setActiveTab('overview')
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Failed to start analysis'
      if (err?.response?.status === 429) setError('Rate limit hit. Wait 60 seconds.')
      else setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const result = stream?.result
  const summary = result?.summary
  const isRunning = stream?.status === 'running'
  const isDone = stream?.status === 'completed'
  const isFailed = stream?.status === 'failed'

  const langData = result?.repo_scan?.languages
    ? Object.entries(result.repo_scan.languages).slice(0, 8).map(([name, count]) => ({ name, count }))
    : []

  const COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#818cf8', '#7c3aed', '#5b21b6', '#4c1d95']

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-1.5 bg-brand-600 rounded-lg">
            <Terminal className="w-5 h-5 text-white" />
          </div>
          <div>
            <span className="font-bold text-white">Dev Agent</span>
            <span className="ml-2 text-xs text-gray-500">Autonomous Developer Assistant</span>
          </div>
        </div>
        <button onClick={handleLogout} className="btn-ghost text-gray-400 hover:text-white">
          <LogOut className="w-4 h-4" />
          Logout
        </button>
      </header>

      <div className="flex-1 flex gap-0">
        {/* Sidebar */}
        <aside className="w-80 border-r border-gray-800 p-5 flex flex-col gap-5 overflow-y-auto">
          {/* Analyze form */}
          <form onSubmit={handleAnalyze} className="space-y-3">
            <p className="section-title">Analyze Repository</p>
            <div className="flex items-center gap-2 input pr-3">
              <Github className="w-4 h-4 text-gray-500 shrink-0" />
              <input
                className="flex-1 bg-transparent text-sm outline-none text-gray-100 placeholder-gray-500"
                placeholder="https://github.com/user/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                required
              />
            </div>
            <input
              className="input"
              placeholder="Branch (default: main)"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              type="submit"
              className="btn-primary w-full justify-center"
              disabled={loading || isRunning}
            >
              <Play className="w-4 h-4" />
              {loading ? 'Starting...' : isRunning ? 'Analyzing...' : 'Analyze'}
            </button>
          </form>

          {/* Active job agents */}
          {activeJobId && stream && (
            <div>
              <p className="section-title">Agent Pipeline</p>
              <AgentPanel agents={stream.agents} />
            </div>
          )}

          {/* Past jobs */}
          {pastJobs.length > 0 && (
            <div>
              <p className="section-title">Recent Jobs</p>
              <div className="space-y-1.5">
                {pastJobs.slice(0, 8).map((job) => (
                  <button
                    key={job.id}
                    onClick={() => setActiveJobId(job.id)}
                    className={clsx(
                      'w-full text-left px-3 py-2 rounded-lg text-xs transition-all',
                      activeJobId === job.id
                        ? 'bg-brand-900 text-brand-200 border border-brand-700'
                        : 'bg-gray-900 hover:bg-gray-800 text-gray-400 border border-gray-800'
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono">
                        {job.repo_url.replace('https://github.com/', '')}
                      </span>
                      <StatusDot status={job.status} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto">
          {!activeJobId ? (
            <EmptyState />
          ) : !result && !isFailed ? (
            <LoadingState status={stream?.status} />
          ) : isFailed ? (
            <ErrorState error={stream?.error} />
          ) : (
            <div className="p-6 space-y-6">
              {/* Summary bar */}
              {summary && (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  <StatCard icon={<FileCode2 className="w-4 h-4" />} label="Files" value={summary.total_files?.toLocaleString()} />
                  <StatCard icon={<Layers className="w-4 h-4" />} label="Lines" value={summary.total_lines?.toLocaleString()} />
                  <StatCard icon={<Package className="w-4 h-4" />} label="Deps" value={summary.total_dependencies} />
                  <StatCard icon={<Cpu className="w-4 h-4" />} label="Language" value={summary.primary_language} />
                  <StatCard icon={<CheckCircle2 className="w-4 h-4 text-green-400" />} label="Tests ✓" value={summary.tests_passed} color="green" />
                  <StatCard icon={<XCircle className="w-4 h-4 text-red-400" />} label="Tests ✗" value={summary.tests_failed} color="red" />
                </div>
              )}

              {/* Tabs */}
              <div className="flex gap-1 border-b border-gray-800">
                {(['overview', 'deps', 'env', 'explain', 'tests'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={clsx(
                      'px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
                      activeTab === tab
                        ? 'border-brand-500 text-white'
                        : 'border-transparent text-gray-500 hover:text-gray-300'
                    )}
                  >
                    {TAB_LABELS[tab]}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Language chart */}
                  {langData.length > 0 && (
                    <div className="card">
                      <p className="section-title">Language Breakdown</p>
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={langData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                          <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} />
                          <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} />
                          <Tooltip
                            contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                            labelStyle={{ color: '#f9fafb' }}
                          />
                          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                            {langData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* Dependency graph */}
                  {result?.repo_scan && (
                    <div className="card">
                      <p className="section-title">Codebase Graph</p>
                      <DependencyGraph
                        languages={result.repo_scan.languages ?? {}}
                        stack={result.repo_scan.detected_stack ?? []}
                        entryPoints={result.repo_scan.entry_points ?? []}
                      />
                    </div>
                  )}

                  {/* Stack */}
                  {summary?.stack?.length > 0 && (
                    <div className="card">
                      <p className="section-title">Detected Stack</p>
                      <div className="flex flex-wrap gap-2">
                        {summary.stack.map((s: string) => (
                          <span key={s} className="badge bg-brand-900 text-brand-300">{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'deps' && (
                <div className="card">
                  <p className="section-title">Dependencies</p>
                  <div className="space-y-1 max-h-[600px] overflow-y-auto">
                    {Object.entries(result?.dependencies?.dependencies ?? {}).map(([pkg, ver]: any) => (
                      <div key={pkg} className="flex justify-between items-center py-2 border-b border-gray-800 text-sm">
                        <span className="font-mono text-gray-200">{pkg}</span>
                        <span className="text-gray-500 font-mono text-xs">{ver}</span>
                      </div>
                    ))}
                    {Object.keys(result?.dependencies?.dependencies ?? {}).length === 0 && (
                      <p className="text-gray-500 text-sm">No dependencies found.</p>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'env' && (
                <div className="space-y-4">
                  {result?.environment?.dockerfile && (
                    <div className="card">
                      <div className="flex items-center justify-between mb-3">
                        <p className="section-title mb-0">Generated Dockerfile</p>
                        <button
                          className="btn-ghost text-xs"
                          onClick={() => copyToClipboard(result.environment.dockerfile)}
                        >
                          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                          {copied ? 'Copied!' : 'Copy'}
                        </button>
                      </div>
                      <pre className="bg-gray-950 rounded-lg p-4 text-xs font-mono text-green-300 overflow-x-auto whitespace-pre">
                        {result.environment.dockerfile}
                      </pre>
                    </div>
                  )}
                  {result?.environment?.run_command && (
                    <div className="card">
                      <p className="section-title">Run Command</p>
                      <code className="block bg-gray-950 rounded-lg p-4 text-sm font-mono text-orange-300">
                        {result.environment.run_command}
                      </code>
                    </div>
                  )}
                  {result?.environment?.setup_instructions?.length > 0 && (
                    <div className="card">
                      <p className="section-title">Setup Instructions</p>
                      <ol className="space-y-2">
                        {result.environment.setup_instructions.map((step: string, i: number) => (
                          <li key={i} className="text-sm text-gray-300 font-mono">{step}</li>
                        ))}
                      </ol>
                    </div>
                  )}
                  {result?.environment?.notes?.map((note: string, i: number) => (
                    <div key={i} className="card border-yellow-800/50 bg-yellow-950/20">
                      <p className="text-yellow-300 text-sm">⚠ {note}</p>
                    </div>
                  ))}
                </div>
              )}

              {activeTab === 'explain' && (
                <div className="card">
                  <p className="section-title">AI Architecture Explanation</p>
                  {result?.explanation?.architecture_explanation ? (
                    <div className="prose prose-invert prose-sm max-w-none">
                      <pre className="whitespace-pre-wrap text-sm text-gray-300 font-sans leading-relaxed">
                        {result.explanation.architecture_explanation}
                      </pre>
                    </div>
                  ) : result?.explanation?.error ? (
                    <p className="text-red-400 text-sm">{result.explanation.error}</p>
                  ) : (
                    <p className="text-gray-500 text-sm">No explanation available.</p>
                  )}
                </div>
              )}

              {activeTab === 'tests' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <StatCard icon={<TestTube2 className="w-4 h-4" />} label="Framework" value={result?.tests?.framework ?? 'None'} />
                    <StatCard icon={<CheckCircle2 className="w-4 h-4 text-green-400" />} label="Passed" value={result?.tests?.passed ?? 0} color="green" />
                    <StatCard icon={<XCircle className="w-4 h-4 text-red-400" />} label="Failed" value={result?.tests?.failed ?? 0} color="red" />
                  </div>
                  {result?.tests?.output && (
                    <div className="card">
                      <p className="section-title">Test Output</p>
                      <pre className="bg-gray-950 rounded-lg p-4 text-xs font-mono text-gray-300 overflow-x-auto max-h-96 overflow-y-auto whitespace-pre">
                        {result.tests.output}
                      </pre>
                    </div>
                  )}
                  {result?.tests?.timed_out && (
                    <div className="card border-yellow-800/50 bg-yellow-950/20">
                      <p className="text-yellow-300 text-sm">⚠ Tests timed out after 60 seconds.</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

const TAB_LABELS = {
  overview: 'Overview',
  deps:     'Dependencies',
  env:      'Environment',
  explain:  'AI Explanation',
  tests:    'Tests',
}

function StatCard({ icon, label, value, color }: any) {
  return (
    <div className="card flex flex-col gap-1">
      <div className={clsx('flex items-center gap-1.5 text-xs',
        color === 'green' ? 'text-green-400' : color === 'red' ? 'text-red-400' : 'text-gray-500'
      )}>
        {icon}
        <span>{label}</span>
      </div>
      <p className="text-lg font-bold text-white truncate">{value ?? '—'}</p>
    </div>
  )
}

function StatusDot({ status }: { status: string }) {
  return (
    <span className={clsx('w-2 h-2 rounded-full shrink-0',
      status === 'completed' ? 'bg-green-400' :
      status === 'running'   ? 'bg-brand-400 animate-pulse' :
      status === 'failed'    ? 'bg-red-400' : 'bg-gray-600'
    )} />
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center h-full gap-4 text-center p-12">
      <div className="p-4 bg-gray-900 rounded-2xl border border-gray-800">
        <Github className="w-10 h-10 text-gray-600" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-gray-300">No repo analyzed yet</h2>
        <p className="text-sm text-gray-600 mt-1">Paste a GitHub URL on the left and click Analyze</p>
      </div>
    </div>
  )
}

function LoadingState({ status }: { status?: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center h-full gap-4">
      <div className="relative">
        <div className="w-16 h-16 border-4 border-brand-900 rounded-full" />
        <div className="absolute inset-0 w-16 h-16 border-4 border-brand-500 rounded-full border-t-transparent animate-spin" />
      </div>
      <div className="text-center">
        <p className="text-gray-300 font-medium">Agents are working...</p>
        <p className="text-gray-600 text-sm mt-1">Watch the pipeline on the left</p>
      </div>
    </div>
  )
}

function ErrorState({ error }: { error?: string | null }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center h-full gap-4">
      <XCircle className="w-12 h-12 text-red-400" />
      <div className="text-center">
        <p className="text-gray-300 font-medium">Analysis failed</p>
        <p className="text-red-400 text-sm mt-1">{error ?? 'Unknown error'}</p>
      </div>
    </div>
  )
}
