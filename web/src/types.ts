export interface GNode {
  id: string
  charId?: string
  faction?: string
  factionId?: string
  star?: number
  profession?: string
  appellation?: string
  isNpc: boolean
  lines: number
  nfiles: number
  mentioned: number
  aliases: string[]
  inGraph: boolean
  deg: number
  wdeg: number
  btwn: number
  comm: number
  pos?: [number, number]
}

export interface GEdge {
  a: string
  b: string
  dlg: number
  mab: number
  mba: number
  rec: number
  arc: number
  voc: number
  fam: number
  nf: number
  w: number
  u: number[]
}

export interface Unit {
  id: number
  cat: string
  chapter: string
  name: string
}

export interface Graph {
  meta: { built: string; nodes: number; edges: number; weights: Record<string, number>; stats?: { communities?: number }; commLabels?: Record<string, string> }
  units: Unit[]
  nodes: GNode[]
  edges: GEdge[]
}

export interface Evidence {
  k: string
  f: string
  n: number
  t: string
  s?: string
  o?: string
  on?: number
  ot?: string
}

export type PairEvidence = Record<string, Evidence[]>
