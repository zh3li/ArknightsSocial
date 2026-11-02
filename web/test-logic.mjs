// Logic tests: transpile src/data.ts with esbuild, run assertions in node.
import { build } from 'esbuild'
import { readFileSync, writeFileSync } from 'fs'

await build({
  entryPoints: ['src/data.ts'],
  bundle: true,
  format: 'esm',
  outfile: '/tmp/opencode/data.test.mjs',
})

const { loadTestData } = { loadTestData: null }
const mod = await import('/tmp/opencode/data.test.mjs')
const graph = JSON.parse(readFileSync('public/data/graph.json', 'utf8'))
const nodes = new Map(graph.nodes.map((n) => [n.id, n]))
const adj = mod.buildAdjacency(graph)
mod.setUnitCat(new Map(graph.units.map((u) => [u.id, u.cat])))

const state = {
  graph, nodes, adj,
  filters: {
    types: { dlg: true, men: true, rec: false, arc: false, voc: false, fam: true },
    minW: 0,
    cats: new Set(['主线', '支线', '故事集', '干员密录', '特殊']),
  },
  mode: 'ego', focus: '阿米娅', topK: 40,
  pathFrom: '塔露拉', pathTo: '阿米娅', colorBy: 'faction',
}

let pass = 0, fail = 0
const t = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok - ${name}`) }
  else { fail++; console.log(`FAIL - ${name} ${extra}`) }
}

console.log('graph loaded:', graph.nodes.length, 'nodes', graph.edges.length, 'edges')

// ego subgraph of 阿米娅
const ego = mod.egoSubgraph(state)
t('ego has focus', ego.nodes.has('阿米娅'))
t('ego size reasonable', ego.nodes.size >= 5 && ego.nodes.size <= 60, `got ${ego.nodes.size}`)
t('ego edges within nodes', [...ego.edges].every((e) => ego.nodes.has(e.a) && ego.nodes.has(e.b)))

// talulah ego contains key figures
state.focus = '塔露拉'
const tal = mod.egoSubgraph(state)
for (const who of ['阿米娅', '爱国者', '霜星', '陈']) {
  t(`talulah 1-ring includes ${who}`, tal.nodes.has(who))
}
state.focus = '阿米娅'

// shortest path talulah <-> amiya
const path = mod.shortestPath(state, '塔露拉', '阿米娅')
t('path talulah-amiya found', Array.isArray(path) && path[0] === '塔露拉' && path.at(-1) === '阿米娅',
  JSON.stringify(path))
t('path is short', !path || path.length <= 5, JSON.stringify(path))

// path between obscure pair
const p2 = mod.shortestPath(state, '银灰', '能天使')
t('path yineng found', Array.isArray(p2), JSON.stringify(p2))

// disconnected under heavy filters
state.filters.types = { dlg: false, men: false, rec: false, arc: false, voc: false, fam: false }
const p3 = mod.shortestPath(state, '塔露拉', '阿米娅')
t('no path when all types off', p3 === null, JSON.stringify(p3))
state.filters.types = { dlg: true, men: true, rec: false, arc: false, voc: false, fam: true }

// min weight filter (amiya's top ties are huge, so use 1000)
state.filters.minW = 1000
const heavy = mod.egoSubgraph(state)
t('heavy filter shrinks graph', heavy.edges.size < ego.edges.size, `${heavy.edges.size} vs ${ego.edges.size}`)
state.filters.minW = 0

// edge visibility function basics
const e0 = graph.edges[0]
t('edgeVisible true default', mod.edgeVisible(e0, state.filters))

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
