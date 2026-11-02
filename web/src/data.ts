import type { GEdge, GNode, Graph } from './types'

export interface Filters {
  types: { dlg: boolean; men: boolean; rec: boolean; arc: boolean; voc: boolean; fam: boolean }
  minW: number
  cats: Set<string>
}

export const TYPE_MINS = { dlg: 1, men: 2, rec: 1, arc: 1, voc: 1, fam: 1 }
export const TYPE_LABELS: Record<string, string> = {
  dlg: '对话', men: '提及', rec: '密录', arc: '档案', voc: '语音', fam: '亲属',
}

export interface AppState {
  graph: Graph
  nodes: Map<string, GNode>
  adj: Map<string, GEdge[]> // undirected adjacency
  filters: Filters
  mode: 'ego' | 'path'
  focus: string
  topK: number
  pathFrom: string
  pathTo: string
  colorBy: 'faction' | 'comm' | 'kind'
}

export async function loadGraph(): Promise<Graph> {
  const res = await fetch('./data/graph.json')
  return res.json()
}

export function buildAdjacency(graph: Graph): Map<string, GEdge[]> {
  const adj = new Map<string, GEdge[]>()
  for (const e of graph.edges) {
    if (!adj.has(e.a)) adj.set(e.a, [])
    if (!adj.has(e.b)) adj.set(e.b, [])
    adj.get(e.a)!.push(e)
    adj.get(e.b)!.push(e)
  }
  return adj
}

/** Display form of an evidence source path: last 2 segments, no .txt. */
export function srcShort(f: string): string {
  return f.split('/').slice(-2).join('/').replace(/\.txt$/, '')
}

export function edgeVisible(e: GEdge, f: Filters): boolean {
  if (e.w < f.minW) return false
  if (e.u.length > 0 && !e.u.some((u) => f.cats.has(catOfUnit(u)))) return false
  if (e.fam >= TYPE_MINS.fam && f.types.fam) return true
  if (e.dlg >= TYPE_MINS.dlg && f.types.dlg) return true
  if (e.mab + e.mba >= TYPE_MINS.men && f.types.men) return true
  if (e.rec >= TYPE_MINS.rec && f.types.rec) return true
  if (e.arc >= TYPE_MINS.arc && f.types.arc) return true
  if (e.voc >= TYPE_MINS.voc && f.types.voc) return true
  return false
}

export function catOfUnitCached(state: AppState): Map<number, string> {
  const m = new Map<number, string>()
  for (const u of state.graph.units) m.set(u.id, u.cat)
  return m
}
let unitCat: Map<number, string> | null = null
export function catOfUnit(u: number): string {
  return unitCat?.get(u) ?? ''
}
export function setUnitCat(m: Map<number, string>) {
  unitCat = m
}

export function edgeTypesOf(e: GEdge): string[] {
  const out: string[] = []
  if (e.dlg >= TYPE_MINS.dlg) out.push('dlg')
  if (e.mab + e.mba >= TYPE_MINS.men) out.push('men')
  if (e.rec >= TYPE_MINS.rec) out.push('rec')
  if (e.arc >= TYPE_MINS.arc) out.push('arc')
  if (e.voc >= TYPE_MINS.voc) out.push('voc')
  if (e.fam >= 1) out.push('fam')
  return out
}

/** Ego subgraph: BFS up to `degree` levels, top-K neighbors per node by weight. */
export function egoSubgraph(state: AppState): { nodes: Set<string>; edges: Set<GEdge> } {
  const nodes = new Set<string>([state.focus])
  const edges = new Set<GEdge>()
  let frontier = [state.focus]
  for (let d = 0; d < 1; d++) {
    const next: string[] = []
    const candidates = new Map<string, GEdge[]>()
    for (const id of frontier) {
      const list = (state.adj.get(id) ?? []).filter((e) => edgeVisible(e, state.filters))
      list.sort((x, y) => y.w - x.w)
      for (const e of list.slice(0, state.topK)) {
        const other = e.a === id ? e.b : e.a
        if (!candidates.has(other)) candidates.set(other, [])
        candidates.get(other)!.push(e)
      }
    }
    for (const [id, es] of candidates) {
      if (!nodes.has(id)) {
        nodes.add(id)
        next.push(id)
      }
      for (const e of es) edges.add(e)
    }
    frontier = next
  }
  // keep only edges between included nodes
  const finalEdges = new Set<GEdge>()
  for (const e of edges) {
    if (nodes.has(e.a) && nodes.has(e.b)) finalEdges.add(e)
  }
  return { nodes, edges: finalEdges }
}

/** Shortest path (fewest hops) on visible edges. Returns node ids or null. */
export function shortestPath(state: AppState, from: string, to: string): string[] | null {
  if (from === to) return [from]
  const prev = new Map<string, string>()
  const visited = new Set<string>([from])
  let queue = [from]
  while (queue.length) {
    const next: string[] = []
    for (const id of queue) {
      for (const e of state.adj.get(id) ?? []) {
        if (!edgeVisible(e, state.filters)) continue
        const other = e.a === id ? e.b : e.a
        if (visited.has(other)) continue
        visited.add(other)
        prev.set(other, id)
        if (other === to) {
          const path = [to]
          let cur = to
          while (cur !== from) {
            cur = prev.get(cur)!
            path.unshift(cur)
          }
          return path
        }
        next.push(other)
      }
    }
    queue = next
  }
  return null
}

export function findEdge(state: AppState, a: string, b: string): GEdge | undefined {
  for (const e of state.adj.get(a) ?? []) {
    if ((e.a === a && e.b === b) || (e.a === b && e.b === a)) return e
  }
  return undefined
}
