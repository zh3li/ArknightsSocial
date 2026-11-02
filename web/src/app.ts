import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { Evidence, GEdge, GNode, PairEvidence } from './types'
import {
  AppState, Filters, TYPE_LABELS, TYPE_MINS, buildAdjacency, catOfUnitCached,
  edgeTypesOf, egoSubgraph, findEdge, loadGraph, setUnitCat,
  shortestPath, srcShort,
} from './data'
import { buildFactionColors, commColor, DOCTOR_COLOR, factionColor, initColors, nodeColor as colorOf, setColorBy, PROFESSION_LABELS } from './palette'
import { renderPanel, renderRank, showEvidence, statusMsg } from './panels'

cytoscape.use(fcose)

const ALL_CATS = ['主线', '支线', '故事集', '干员密录', '特殊']

let state: AppState
let cy: any
let factionColors: Map<string, string>
const evCache = new Map<string, PairEvidence | null>()

async function fetchEvPair(a: string, b: string): Promise<PairEvidence | null> {
  const key = a < b ? `${a}␟${b}` : `${b}␟${a}`
  if (evCache.has(key)) return evCache.get(key)!
  try {
    const res = await fetch(`./data/ev/pairs/${encodeURIComponent(key)}.json`)
    if (!res.ok) throw new Error(String(res.status))
    const j: PairEvidence = await res.json()
    evCache.set(key, j)
    return j
  } catch {
    evCache.set(key, null)
    return null
  }
}

// ---------------------------------------------------------------------------
// per-view normalization: nodes/edges are sized relative to the visible
// subgraph (robust p5-p95 bounds), so every view shows full contrast.
let nodePct = (v: number) => 0.75
let edgePct = (v: number) => 0.75

function computeViewScales(nodes: Set<string>, edges: Set<GEdge>) {
  const mk = (vals: number[]) => {
    if (!vals.length) return () => 0.75
    vals.sort((a, b) => a - b)
    const lo = vals[Math.floor(0.05 * (vals.length - 1))]
    const hi = vals[Math.floor(0.95 * (vals.length - 1))]
    if (hi <= lo) return () => 0.75
    return (v: number) => Math.min(1, Math.max(0, (v - lo) / (hi - lo)))
  }
  nodePct = mk([...nodes].map((id) => state.nodes.get(id)!.wdeg ?? 0))
  edgePct = mk([...edges].map((e) => e.w))
}

function nodeSize(n: GNode): number {
  return 16 + nodePct(n.wdeg ?? 0) * 40
}

function cyNode(n: GNode, extra: Record<string, unknown> = {}) {
  const isDoc = n.id === '博士'
  let pos: { x: number; y: number } | undefined
  if (cy && cy.getElementById(n.id).nonempty()) {
    pos = cy.getElementById(n.id).position()
  } else if (n.pos) {
    pos = { x: n.pos[0], y: n.pos[1] }
  } else {
    // stats.py output missing: deterministic golden-angle spread so nodes
    // never start stacked at the origin; fcose refines from here.
    const i = simpleHash(n.id)
    pos = { x: 300 * Math.cos(i * 2.39996), y: 300 * Math.sin(i * 2.39996) }
  }
  return {
    group: 'nodes',
    data: {
      id: n.id, label: n.id, size: nodeSize(n), color: colorOf(n),
      shape: isDoc ? 'star' : 'ellipse',
      bw: isDoc ? 5 : 2,
      bc: isDoc ? '#ffd700' : '#3a4152',
      ...extra,
    },
    position: pos,
  }
}

function simpleHash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h % 100000
}

function cyEdge(e: GEdge) {
  const pct = edgePct(e.w)
  return {
    group: 'edges',
    data: {
      id: `${e.a}␟${e.b}`,
      source: e.a,
      target: e.b,
      weight: e.w,
      width: 1.5 + pct * 7.5,
      eop: 0.35 + pct * 0.4,
    },
  }
}

// ---------------------------------------------------------------------------
function currentSubgraph() {
  if (state.mode === 'path') {
    const path = shortestPath(state, state.pathFrom, state.pathTo)
    if (!path) return { nodes: new Set<string>(), edges: new Set<GEdge>() }
    const nodes = new Set(path)
    const edges = new Set<GEdge>()
    for (let i = 0; i + 1 < path.length; i++) {
      const e = findEdge(state, path[i], path[i + 1])
      if (e) edges.add(e)
    }
    return { nodes, edges }
  }
  return egoSubgraph(state)
}

function renderPathPanel() {
  const el = document.getElementById('panelContent')!
  if (state.mode !== 'path') return
  const path = shortestPath(state, state.pathFrom, state.pathTo)
  if (!path) {
    el.innerHTML = `<div class="empty">在当前筛选条件下两人物之间没有路径。<br/>尝试放宽关系类型或筛选条件。</div>`
    return
  }
  let html = `<h3>关系路径 <small>${path.length} 人 · ${path.length - 1} 跳</small></h3><ol class="pathList">`
  for (const id of path) {
    const n = state.nodes.get(id)
    html += `<li data-node="${id}"><span class="dot" style="background:${colorOf(n!)}"></span>${id}</li>`
  }
  html += '</ol><div id="pathEvidence"></div>'
  el.innerHTML = html
  el.querySelectorAll<HTMLLIElement>('.pathList li').forEach((li) => {
    li.addEventListener('click', () => selectNode(li.dataset.node!))
  })
  // per-hop evidence
  const pe = el.querySelector('#pathEvidence')!
  for (let i = 0; i + 1 < path.length; i++) {
    const e = findEdge(state, path[i], path[i + 1])!
    const div = document.createElement('div')
    div.className = 'hop'
    div.innerHTML = `<b>${path[i]} ↔ ${path[i + 1]}</b> ` +
      edgeTypesOf(e).map((t) => `<span class="badge t-${t}">${TYPE_LABELS[t]}</span>`).join('') +
      ` <span class="muted">w=${e.w}</span><div class="evq" data-hop="${i}">加载证据…</div>`
    pe.appendChild(div)
    fetchEvPair(path[i], path[i + 1]).then((evs) => {
      renderEvq(div.querySelector('.evq')!, evs ?? undefined)
    })
  }
}

function renderEvq(el: HTMLElement, evs: Record<string, Evidence[]> | undefined) {
  if (!evs) {
    el.innerHTML = '<span class="muted">无引用样本</span>'
    return
  }
  const parts: string[] = []
  for (const [kind, list] of Object.entries(evs)) {
    for (const q of list.slice(0, 2)) {
      const fShort = srcShort(q.f)
      parts.push(
        `<div class="quote"><span class="badge t-${kind}">${TYPE_LABELS[kind] ?? kind}</span>` +
        `<span class="qt">「${escapeHtml(q.t)}」</span>` +
        `<span class="src">${escapeHtml(q.s ?? '')} · ${escapeHtml(fShort)}:${q.n}</span></div>`)
    }
  }
  el.innerHTML = parts.join('') || '<span class="muted">无</span>'
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// ---------------------------------------------------------------------------
function redraw(keepPositions = true) {
  const { nodes, edges } = currentSubgraph()
  const nodeIds = new Set(nodes)
  const edgeIds = new Set([...edges].map((e) => `${e.a}␟${e.b}`))
  computeViewScales(nodes, edges)

  // remove stale
  cy.elements((el: any) => {
    if (el.isEdge()) return !edgeIds.has(el.id())
    return !nodeIds.has(el.id())
  }).remove()
  // add new
  const addN = [...nodes].filter((id) => !cy.getElementById(id).nonempty())
  if (addN.length) {
    cy.add(addN.map((id) => cyNode(state.nodes.get(id)!)))
  }
  const addE = [...edges].filter((e) => !cy.getElementById(`${e.a}␟${e.b}`).nonempty())
  if (addE.length) cy.add(addE.map(cyEdge))
  // restyle (sizes/colors may change with mode)
  cy.batch(() => {
    cy.nodes().forEach((n: any) => {
      const gn = state.nodes.get(n.id())!
      n.data('size', nodeSize(gn))
      n.data('color', colorOf(gn))
    })
    cy.edges().forEach((el: any) => {
      const w = el.data('weight') as number
      el.data('width', 1.5 + edgePct(w) * 7.5)
      el.data('eop', 0.35 + edgePct(w) * 0.4)
    })
  })

  runLayout(!keepPositions || state.mode === 'path')
  updateStatus(nodes.size, edges.size)
  renderLegend()
  startDoctorPulse()
  if (state.mode === 'path') renderPathPanel()
}

/** 博士: gentle border pulse — the only animated node on canvas. */
let doctorPulseTimer: ReturnType<typeof setTimeout> | null = null
function startDoctorPulse() {
  if (doctorPulseTimer) clearTimeout(doctorPulseTimer)
  const doc = cy.getElementById('博士')
  if (doc.empty()) return
  const step = (wide: boolean) => {
    const el = cy.getElementById('博士')
    if (el.empty()) return
    el.animate(
      { style: { 'border-width': wide ? 6 : 3 } },
      { duration: 1200, easing: 'ease-in-out' },
    )
    doctorPulseTimer = setTimeout(() => step(!wide), 1250)
  }
  step(true)
}

function runLayout(fresh: boolean) {
  if (fresh) {
    const preset = state.mode === 'path' ? { name: 'breadthfirst', directed: true, roots: [state.pathFrom], spacing: 60, animate: true } : {
      name: 'fcose',
      animate: true,
      animationDuration: 500,
      quality: 'default',
      nodeSeparation: 90,
      idealEdgeLength: 70,
  padding: 60,
    }
    cy.layout(preset).run()
  } else {
    cy.layout({ name: 'fcose', randomize: false, animate: true, animationDuration: 400, padding: 60 }).run()
  }
}

function updateStatus(n: number, e: number) {
  document.getElementById('statCounts')!.textContent = `${n} 人物 · ${e} 关系`
}

function renderLegend() {
  const el = document.getElementById('legendBody')!
  const items: string[] = []
  if (state.colorBy === 'faction') {
    const counts = new Map<string, { c: string; n: number }>()
    const byFaction = new Map<string, GNode[]>()
    for (const gn of state.graph.nodes) {
      if (!gn.faction) continue
      // probe for the swatch must not be 博士 (whose color is the signature gold)
      if (gn.id !== '博士' && !byFaction.has(gn.faction)) byFaction.set(gn.faction, [gn])
      counts.set(gn.faction, counts.get(gn.faction) ?? { c: '#8a8f98', n: 0 })
      counts.get(gn.faction)!.n++
    }
    for (const [name, probe] of byFaction) counts.get(name)!.c = factionColor(factionColors, probe[0])
    const top = [...counts.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 12)
    for (const [name, { c }] of top) items.push(`<div><span class="dot" style="background:${c}"></span>${escapeHtml(name)}</div>`)
    items.push('<div><span class="dot" style="background:#c9a66b"></span>无势力NPC</div>')
    items.push(`<div><span class="dot star" style="background:${DOCTOR_COLOR}"></span>博士</div>`)
  } else if (state.colorBy === 'comm') {
    const used = new Map<number, number>()
    for (const gn of state.graph.nodes) used.set(gn.comm, (used.get(gn.comm) ?? 0) + 1)
    const top = [...used.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12)
    for (const [c] of top) {
      const probe = state.graph.nodes.find((n) => n.comm === c && n.id !== '博士')!
      const label = state.graph.meta.commLabels?.[String(c)]
      items.push(`<div><span class="dot" style="background:${commColor(probe)}"></span>${escapeHtml(label ? `${label}组` : `社群 ${c}`)}</div>`)
    }
    items.push(`<div><span class="dot star" style="background:${DOCTOR_COLOR}"></span>博士</div>`)
  } else {
    items.push('<div><span class="dot" style="background:#64b5f6"></span>干员</div>')
    items.push('<div><span class="dot" style="background:#e8a857"></span>NPC</div>')
    items.push(`<div><span class="dot star" style="background:${DOCTOR_COLOR}"></span>博士</div>`)
  }
  el.innerHTML = items.join('')
}

// ---------------------------------------------------------------------------
function selectNode(id: string) {
  const n = state.nodes.get(id)
  if (!n) return
  cy.getElementById(id).select()
  renderPanel(state, id, fetchEvPair, () => redraw(), (target) => {
    // jump to another node
    setFocus(target)
  })
}

function setFocus(id: string) {
  state.focus = id
  state.mode = 'ego'
  updateModeButtons()
  redraw(false)
  renderPanel(state, id, fetchEvPair, () => redraw(), setFocus)
}

function updateModeButtons() {
  document.querySelectorAll<HTMLButtonElement>('#modes button').forEach((b) => {
    b.classList.toggle('active', b.dataset.mode === state.mode)
  })
  document.getElementById('egoCtrls')!.style.display = state.mode === 'ego' ? '' : 'none'
}

// ---------------------------------------------------------------------------
function buildControls() {
  // type checkboxes
  const tc = document.getElementById('typeChecks')!
  tc.innerHTML = Object.keys(TYPE_LABELS)
    .map((t) => `<label class="check"><input type="checkbox" data-type="${t}" ${state.filters.types[t as keyof Filters['types']] ? 'checked' : ''}/> ${TYPE_LABELS[t]}</label>`)
    .join('')
  tc.querySelectorAll<HTMLInputElement>('input').forEach((cb) => {
    cb.addEventListener('change', () => {
      state.filters.types[cb.dataset.type as keyof Filters['types']] = cb.checked
      redraw(false)
    })
  })

  // categories
  const cc = document.getElementById('catChecks')!
  cc.innerHTML = ALL_CATS.map((c) => `<label class="check"><input type="checkbox" data-cat="${c}" checked/> ${c}</label>`).join('')
  cc.querySelectorAll<HTMLInputElement>('input').forEach((cb) => {
    cb.addEventListener('change', () => {
      if (cb.checked) state.filters.cats.add(cb.dataset.cat!)
      else state.filters.cats.delete(cb.dataset.cat!)
      redraw(false)
    })
  })

  // min weight
  const minW = document.getElementById('minW') as HTMLInputElement
  minW.max = String(Math.min(300, Math.round(state.graph.edges[0]?.w ?? 100)))
  minW.value = '0'
  document.getElementById('minWVal')!.textContent = '0'
  minW.addEventListener('input', () => {
    state.filters.minW = Number(minW.value)
    document.getElementById('minWVal')!.textContent = minW.value
    redraw(false)
  })

  const topK = document.getElementById('topK') as HTMLInputElement
  topK.addEventListener('input', () => {
    state.topK = Number(topK.value)
    document.getElementById('topKVal')!.textContent = topK.value
    redraw(false)
  })

  document.getElementById('colorBy')!.addEventListener('change', (ev) => {
    state.colorBy = (ev.target as HTMLSelectElement).value as AppState['colorBy']
    setColorBy(state.colorBy)
    redraw(false)
  })

  // modes
  document.querySelectorAll<HTMLButtonElement>('#modes button').forEach((b) => {
    b.addEventListener('click', () => {
      state.mode = b.dataset.mode as AppState['mode']
      updateModeButtons()
      if (state.mode === 'path') {
        renderPathSetup()
      } else {
        redraw(true)
        renderPanel(state, state.focus, fetchEvPair, () => redraw(), setFocus)
      }
    })
  })

  // search
  const search = document.getElementById('search') as HTMLInputElement
  const dl = document.getElementById('nodelist')!
  const topNames = [...state.graph.nodes].sort((a, b) => b.wdeg - a.wdeg).slice(0, 800)
  dl.innerHTML = topNames.map((n) => `<option value="${escapeHtml(n.id)}">${escapeHtml(n.faction ?? (n.isNpc ? 'NPC' : ''))}</option>`).join('')
  const go = () => {
    const v = search.value.trim()
    if (v && state.nodes.has(v)) setFocus(v)
    else if (v) {
      // substring match
      const hit = state.graph.nodes.find((n) => n.id.includes(v) || n.aliases.some((a) => a.includes(v)))
      if (hit) setFocus(hit.id)
      else statusMsg('未找到人物：' + v)
    }
  }
  document.getElementById('btnGo')!.addEventListener('click', go)
  search.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') go()
  })

  // rankings
  document.getElementById('btnRank')!.addEventListener('click', () => {
    document.getElementById('rankModal')!.classList.remove('hidden')
    renderRank(state, setFocus, fetchEvPair)
  })
  document.getElementById('btnRankClose')!.addEventListener('click', () => {
    document.getElementById('rankModal')!.classList.add('hidden')
  })
  document.getElementById('rankMetric')!.addEventListener('change', () => renderRank(state, setFocus, fetchEvPair))
  document.getElementById('btnPairClose')!.addEventListener('click', () => {
    document.getElementById('pairModal')!.classList.add('hidden')
  })
}

function renderPathSetup() {
  const el = document.getElementById('panelContent')!
  const opt = (sel: string) =>
    `<input id="${sel}" list="nodelist" placeholder="人物…" value="${sel === 'pathA' ? escapeHtml(state.pathFrom) : escapeHtml(state.pathTo)}"/>`
  el.innerHTML = `
    <h3>关系路径</h3>
    <p class="muted">寻找两个角色之间的最短关联链（按当前筛选条件），并展示每一步的证据。</p>
    <div class="pathForm">
      <label>起点 ${opt('pathA')}</label>
      <label>终点 ${opt('pathB')}</label>
      <button id="btnPath">查找路径</button>
    </div>
    <div id="pathResult"></div>`
  document.getElementById('btnPath')!.addEventListener('click', () => {
    const a = (document.getElementById('pathA') as HTMLInputElement).value.trim()
    const b = (document.getElementById('pathB') as HTMLInputElement).value.trim()
    if (state.nodes.has(a)) state.pathFrom = a
    if (state.nodes.has(b)) state.pathTo = b
    redraw(true)
    renderPathPanel()
  })
}

// ---------------------------------------------------------------------------
async function main() {
  const graph = await loadGraph()
  const nodes = new Map(graph.nodes.map((n) => [n.id, n]))
  const adj = buildAdjacency(graph)
  setUnitCat(catOfUnitCached({ graph, nodes, adj } as AppState))

  state = {
    graph,
    nodes,
    adj,
    filters: {
      types: { dlg: true, men: true, rec: true, arc: true, voc: true, fam: true },
      minW: 0,
      cats: new Set(ALL_CATS),
    },
    mode: 'ego',
    focus: '阿米娅',
    topK: 40,
    pathFrom: '塔露拉',
    pathTo: '阿米娅',
    colorBy: 'faction',
  }
  factionColors = buildFactionColors(graph.nodes)
  initColors(factionColors, state.colorBy)

  document.getElementById('boot')?.remove()

  cy = cytoscape({
    container: document.getElementById('canvas'),
    wheelSensitivity: 0.25,
    hideEdgesOnViewport: true,
    textureOnViewport: true,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': 'data(color)',
          'width': 'data(size)',
          'height': 'data(size)',
          'shape': 'data(shape)' as any,
          'label': 'data(label)',
          'font-size': (el: any) => Math.max(9, Math.min(el.data('size') * 0.45, 16)),
          'color': '#e8eaf0',
          'text-valign': 'bottom',
          'text-margin-y': 6,
          'text-outline-color': '#141822',
          'text-outline-width': 2.5,
          'border-width': 'data(bw)',
          'border-color': 'data(bc)',
        },
      },
      {
        selector: 'node:selected',
        style: { 'border-width': 4, 'border-color': '#ffd54f' },
      },
      {
        selector: 'edge',
        style: {
          'width': 'data(width)',
          'line-color': '#3d4457',
          'opacity': 'data(eop)' as any,
          'curve-style': 'haystack',
          'haystack-radius': 0.4,
        },
      },
      {
        selector: 'edge.highlight',
        style: { 'line-color': '#ffd54f', 'opacity': 1, 'width': 5, 'z-index': 10 },
      },
    ],
    elements: [],
  })

  cy.on('tap', 'node', (ev: any) => {
    selectNode(ev.target.id())
  })
  cy.on('dblclick', 'node', (ev: any) => {
    setFocus(ev.target.id())
  })

  buildControls()
  document.getElementById('statBuilt')!.textContent =
    `构建于 ${graph.meta.built} · ${graph.meta.stats?.communities ?? '?'} 个社群`

  redraw(true)
  renderPanel(state, state.focus, fetchEvPair, () => redraw(), setFocus)
}

main()
