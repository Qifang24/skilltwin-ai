import type { GraphNode } from '@/types/graph'
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from '@/types/graph'

interface CompetencyTreeProps {
  tree: GraphNode[]
  selectedId: string | null
  onSelect: (nodeId: string) => void
}

function DiagramNode({ node, selectedId, onSelect }: { node: GraphNode; selectedId: string | null; onSelect: (nodeId: string) => void }) {
  const isSelected = node.id === selectedId
  const isLeaf = node.children.length === 0

  return (
    <section className={`competency-diagram__branch competency-diagram__branch--${node.node_type}`}>
      <button type="button" className={`competency-diagram__node competency-diagram__node--${node.node_type}${isSelected ? ' is-selected' : ''}`} onClick={() => onSelect(node.id)} title={node.name}>
        <span className="competency-diagram__marker" />
        <span>{node.name}</span>
        {node.edited_by_human && <small>已修订</small>}
      </button>
      {!isLeaf && (
        <div className="competency-diagram__children">
          {node.children.map((child) => <DiagramNode key={child.id} node={child} selectedId={selectedId} onSelect={onSelect} />)}
        </div>
      )}
    </section>
  )
}

export function CompetencyTree({ tree, selectedId, onSelect }: CompetencyTreeProps) {
  return <div className="competency-diagram" role="tree" aria-label="岗位能力图谱">{tree.map((root) => <DiagramNode key={root.id} node={root} selectedId={selectedId} onSelect={onSelect} />)}</div>
}

export function TreeLegend() {
  const types = ['job', 'competency', 'competency_unit', 'skill_point', 'knowledge_point'] as const
  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12 }}>
      {types.map((type) => <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: NODE_TYPE_COLORS[type], display: 'inline-block' }} />{NODE_TYPE_LABELS[type]}</span>)}
      <span style={{ color: 'rgba(0,0,0,0.45)' }}>✎ 表示经教师修订</span>
    </div>
  )
}
