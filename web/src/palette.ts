import type { GNode } from './types'

const PALETTE = [
  '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
  '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080',
  '#e6beff', '#9a6324', '#fffac8', '#800000', '#aaffc3',
  '#808000', '#ffd8b1', '#000075', '#808080', '#ffffff',
  '#d4a017', '#7fffd4', '#ff7f50', '#87ceeb',
]

export const FACTION_FALLBACK = '#8a8f98'

/** The Doctor is the protagonist: a signature gold, identical in every color mode. */
export const DOCTOR_COLOR = '#ffd700'

export function buildFactionColors(nodes: GNode[]): Map<string, string> {
  const counts = new Map<string, number>()
  for (const n of nodes) {
    if (n.factionId) counts.set(n.factionId, (counts.get(n.factionId) ?? 0) + 1)
  }
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1])
  const colors = new Map<string, string>()
  sorted.forEach(([fid], i) => {
    colors.set(fid, i < PALETTE.length ? PALETTE[i] : FACTION_FALLBACK)
  })
  return colors
}

export function factionColor(factionColors: Map<string, string>, n: GNode): string {
  if (n.id === '博士') return DOCTOR_COLOR
  if (n.factionId) return factionColors.get(n.factionId) ?? FACTION_FALLBACK
  return n.isNpc ? '#c9a66b' : FACTION_FALLBACK
}

export function commColor(n: GNode): string {
  if (n.id === '博士') return DOCTOR_COLOR
  const c = ((n.comm ?? -1) % PALETTE.length + PALETTE.length) % PALETTE.length
  return PALETTE[c]
}

export function kindColor(n: GNode): string {
  if (n.id === '博士') return DOCTOR_COLOR
  if (n.isNpc) return '#e8a857'
  return '#64b5f6'
}

let factionColorsMap: Map<string, string> = new Map()
let currentColorBy: 'faction' | 'comm' | 'kind' = 'faction'

export function initColors(fc: Map<string, string>, colorBy: 'faction' | 'comm' | 'kind') {
  factionColorsMap = fc
  currentColorBy = colorBy
}

export function setColorBy(cb: 'faction' | 'comm' | 'kind') {
  currentColorBy = cb
}

export function nodeColor(n: GNode): string {
  if (currentColorBy === 'comm') return commColor(n)
  if (currentColorBy === 'kind') return kindColor(n)
  return factionColor(factionColorsMap, n)
}

export const PROFESSION_LABELS: Record<string, string> = {
  CASTER: '术师', MEDIC: '医疗', WARRIOR: '近卫', SNIPER: '狙击',
  TANK: '重装', SUPPORTER: '辅助', SPECIALIST: '特种', PIONEER: '先锋',
}
