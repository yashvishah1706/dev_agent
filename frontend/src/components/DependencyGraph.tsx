import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  BackgroundVariant,
} from 'reactflow'
import 'reactflow/dist/style.css'

interface Props {
  languages: Record<string, number>
  stack: string[]
  entryPoints: string[]
}

export function DependencyGraph({ languages, stack, entryPoints }: Props) {
  const nodes: Node[] = []
  const edges: Edge[] = []

  // Center node — the project
  nodes.push({
    id: 'root',
    position: { x: 300, y: 200 },
    data: { label: '📦 Project' },
    style: {
      background: '#4f46e5',
      color: '#fff',
      border: '1px solid #6366f1',
      borderRadius: 8,
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 13,
      fontWeight: 500,
      padding: '8px 16px',
    },
  })

  // Language nodes
  const langs = Object.entries(languages).slice(0, 6)
  langs.forEach(([lang, count], i) => {
    const angle = (i / langs.length) * 2 * Math.PI - Math.PI / 2
    const r = 180
    const x = 300 + r * Math.cos(angle)
    const y = 200 + r * Math.sin(angle)
    const id = `lang-${i}`
    nodes.push({
      id,
      position: { x, y },
      data: { label: `${lang}\n${count} files` },
      style: {
        background: '#1e1b4b',
        color: '#a5b4fc',
        border: '1px solid #312e81',
        borderRadius: 8,
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        padding: '6px 12px',
        whiteSpace: 'pre',
        textAlign: 'center' as const,
      },
    })
    edges.push({
      id: `e-root-${id}`,
      source: 'root',
      target: id,
      style: { stroke: '#4338ca', strokeWidth: 1.5 },
      animated: false,
    })
  })

  // Stack nodes
  stack.slice(0, 4).forEach((s, i) => {
    const id = `stack-${i}`
    nodes.push({
      id,
      position: { x: 60 + i * 160, y: 420 },
      data: { label: `🔧 ${s}` },
      style: {
        background: '#064e3b',
        color: '#6ee7b7',
        border: '1px solid #065f46',
        borderRadius: 8,
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        padding: '6px 12px',
      },
    })
    edges.push({
      id: `e-root-${id}`,
      source: 'root',
      target: id,
      style: { stroke: '#065f46', strokeWidth: 1, strokeDasharray: '4 2' },
    })
  })

  // Entry point nodes
  entryPoints.slice(0, 3).forEach((ep, i) => {
    const id = `ep-${i}`
    const short = ep.split('/').pop() ?? ep
    nodes.push({
      id,
      position: { x: 100 + i * 200, y: 20 },
      data: { label: `▶ ${short}` },
      style: {
        background: '#1c1917',
        color: '#fb923c',
        border: '1px solid #78350f',
        borderRadius: 8,
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        padding: '6px 12px',
      },
    })
    edges.push({
      id: `e-ep-${id}`,
      source: id,
      target: 'root',
      style: { stroke: '#92400e', strokeWidth: 1.5 },
      markerEnd: { type: 'arrowclosed' as any, color: '#92400e' },
    })
  })

  return (
    <div style={{ height: 480 }} className="rounded-xl overflow-hidden border border-gray-800">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        attributionPosition="bottom-right"
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1f2937" />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={() => '#4f46e5'}
          maskColor="rgba(0,0,0,0.6)"
          style={{ background: '#111827' }}
        />
      </ReactFlow>
    </div>
  )
}
