import type { Evidence, GEdge, PairEvidence } from './types'
import type { AppState } from './data'
import { TYPE_LABELS, edgeTypesOf, findEdge, srcShort } from './data'
import { PROFESSION_LABELS, nodeColor as colorOfFor } from './palette'

type FetchEvPair = (a: string, b: string) => Promise<PairEvidence | null>

const profilesCache = new Map<string, any>()

async function fetchProfile(id: string): Promise<any | null> {
  if (profilesCache.has(id)) return profilesCache.get(id)
  try {
    const res = await fetch('./data/profiles.json')
    const all = await res.json()
    Object.keys(all).forEach((k) => profilesCache.set(k, all[k]))
    return profilesCache.get(id) ?? null
  } catch {
    return null
  }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** Evidence table row parts: badge kind, content html, source html, search text. */
type EvPart = { kind: string; content: string; src: string; text: string }

function evidenceParts(evs: Record<string, Evidence[]>): EvPart[] {
  const parts: EvPart[] = []
  for (const [kind, list] of Object.entries(evs)) {
    for (const q of list) {
      const fShort = srcShort(q.f)
      if ((kind === 'dlg' || kind === 'rec') && q.ot != null && q.o != null) {
        parts.push({
          kind,
          content:
            `<div class="dline a"><span class="who">${escapeHtml(q.o)}</span>「${escapeHtml(q.ot)}」</div>` +
            `<div class="dline b"><span class="who">${escapeHtml(q.s ?? '')}</span>「${escapeHtml(q.t)}」</div>`,
          src: `${escapeHtml(fShort)}:${q.on ?? q.n}→${q.n}`,
          text: `${q.t} ${q.ot ?? ''} ${q.s ?? ''} ${q.o ?? ''} ${q.f}`.toLowerCase(),
        })
      } else {
        const who = q.s ?? (q.o ? `→${q.o}` : '')
        parts.push({
          kind,
          content:
            `<span class="qt">${who ? `<span class="who">${escapeHtml(who)}</span>` : ''}「${escapeHtml(q.t)}」</span>`,
          src: `${escapeHtml(fShort)}:${q.n}`,
          text: `${q.t} ${q.s ?? ''} ${q.o ?? ''} ${q.f}`.toLowerCase(),
        })
      }
    }
  }
  return parts
}

function evRow(p: EvPart): string {
  return `<div class="evrow"><span class="badge t-${p.kind}">${TYPE_LABELS[p.kind] ?? p.kind}</span>` +
    `<div class="evcontent">${p.content}</div>` +
    `<span class="evsrc">${p.src}</span></div>`
}

/** Type count chips for an edge (only non-zero). */
function pairChips(e: GEdge): [string, number][] {
  return ([
    ['dlg', e.dlg], ['men', e.mab + e.mba], ['rec', e.rec],
    ['arc', e.arc], ['voc', e.voc], ['fam', e.fam],
  ] as [string, number][]).filter(([, v]) => v > 0)
}

/** Open the dedicated pair-evidence modal for one edge. */
const PAIR_CARD_LABELS: Record<string, string> = {
  dlg: '共同对话', men: '相互提及', rec: '密录互动',
  arc: '档案提及', voc: '语音提及',
}

export async function openPairModal(
  state: AppState, e: GEdge, fetchEv: FetchEvPair, jump: (id: string) => void,
) {
  const modal = document.getElementById('pairModal')!
  const body = document.getElementById('pairBody')!
  const ca = colorOfFor(state.nodes.get(e.a)!)
  const cb = colorOfFor(state.nodes.get(e.b)!)
  const cards = pairChips(e).map(([t, v]) =>
    `<button class="pcard t-${t}" data-kind="${t}" title="点击只显示该类型引用，再点恢复全部">` +
    `<b>${v}</b><span>${PAIR_CARD_LABELS[t] ?? TYPE_LABELS[t]}</span></button>`).join('')
  body.innerHTML = `
    <div class="pairtitle">
      <span class="dot big" style="background:${ca}"></span>
      <button class="plink" data-id="${escapeHtml(e.a)}">${escapeHtml(e.a)}</button>
      <span class="px">↔</span>
      <button class="plink" data-id="${escapeHtml(e.b)}">${escapeHtml(e.b)}</button>
      <span class="dot big" style="background:${cb}"></span>
    </div>
    <div class="pcards">
      ${cards}
      <div class="pcard weight"><b>${e.w}</b><span>综合权重</span></div>
    </div>
    <div class="pairbtns">
      <button data-id="${escapeHtml(e.a)}">查看 ${escapeHtml(e.a)} 的关系网 →</button>
      <button data-id="${escapeHtml(e.b)}">查看 ${escapeHtml(e.b)} 的关系网 →</button>
    </div>
    <div class="pairsec evtools">
      <input class="evsearch" type="text" placeholder="搜索引用 / 人物 / 文件…">
      <span class="evcount"></span>
    </div>
    <div class="evtable">
      <div class="evhead"><span>类型</span><span>引用</span><span>来源</span></div>
      <div class="evbody"><span class="muted">加载引用…</span></div>
    </div>
    <div class="evpager hidden">
      <button class="pgbtn prev">‹ 上一页</button>
      <span class="pginfo"></span>
      <button class="pgbtn next">下一页 ›</button>
    </div>`
  modal.classList.remove('hidden')
  const evs = await fetchEv(e.a, e.b)
  const parts: EvPart[] = evs ? evidenceParts(evs) : []

  const evbody = body.querySelector('.evbody') as HTMLElement
  const evcount = body.querySelector('.evcount') as HTMLElement
  const pager = body.querySelector('.evpager') as HTMLElement
  const pginfo = body.querySelector('.pginfo') as HTMLElement
  const prevBtn = body.querySelector('.pgbtn.prev') as HTMLButtonElement
  const nextBtn = body.querySelector('.pgbtn.next') as HTMLButtonElement
  const search = body.querySelector('.evsearch') as HTMLInputElement

  let solo: string | null = null
  let query = ''
  let page = 1
  const SHOW_ALL = 30

  const filtered = () => parts.filter((p) =>
    (!solo || p.kind === solo) && (!query || p.text.includes(query)))

  const measurePageSize = (n: number) => {
    if (n <= SHOW_ALL) return Math.max(n, 1)
    const h = evbody.clientHeight
    return Math.max(10, Math.min(40, Math.floor((h - 4) / 72) || 10))
  }

  const render = () => {
    if (modal.classList.contains('hidden')) return
    const list = filtered()
    const pageSize = measurePageSize(list.length)
    const pages = Math.max(1, Math.ceil(list.length / pageSize))
    if (page > pages) page = pages
    const slice = list.slice((page - 1) * pageSize, page * pageSize)
    evbody.innerHTML = parts.length === 0
      ? '<span class="muted">无引用样本</span>'
      : slice.length ? slice.map(evRow).join('')
        : '<span class="muted">无匹配引用</span>'
    evcount.textContent = (solo || query) && parts.length
      ? `共 ${parts.length} 条 · 筛选后 ${list.length} 条`
      : `共 ${parts.length} 条`
    pager.classList.toggle('hidden', pages <= 1)
    pginfo.textContent = `第 ${page} / ${pages} 页`
    prevBtn.disabled = page <= 1
    nextBtn.disabled = page >= pages
  }
  render()

  // adaptive page size on window resize
  onPairResize = render

  search.addEventListener('input', () => {
    query = search.value.trim().toLowerCase()
    page = 1
    render()
  })
  prevBtn.addEventListener('click', () => { page -= 1; render() })
  nextBtn.addEventListener('click', () => { page += 1; render() })

  // stat cards: click = show only that kind; click again = show all
  body.querySelectorAll('.pcard[data-kind]').forEach((c) => {
    c.addEventListener('click', () => {
      const kind = (c as HTMLElement).dataset.kind!
      solo = solo === kind ? null : kind
      page = 1
      body.querySelectorAll('.pcard[data-kind]').forEach((x) =>
        x.classList.toggle('active', (x as HTMLElement).dataset.kind === solo))
      render()
    })
  })
  // name links + view-network buttons both jump
  body.querySelectorAll('[data-id]').forEach((b) => {
    b.addEventListener('click', () => {
      modal.classList.add('hidden')
      onPairResize = null
      jump((b as HTMLElement).dataset.id!)
    })
  })
}

/** re-render hook for the open pair modal on window resize */
let onPairResize: (() => void) | null = null
window.addEventListener('resize', () => {
  if (!document.getElementById('pairModal')!.classList.contains('hidden') && onPairResize) {
    onPairResize()
  }
})

export function statusMsg(msg: string) {
  const el = document.getElementById('statCounts')!
  const old = el.textContent
  el.textContent = msg
  setTimeout(() => (el.textContent = old), 2500)
}

export async function renderPanel(
  state: AppState,
  id: string,
  fetchEvPair: FetchEvPair,
  refresh: () => void,
  jump: (id: string) => void,
) {
  const el = document.getElementById('panelContent')!
  const n = state.nodes.get(id)
  if (!n) {
    el.innerHTML = '<div class="empty">未选择人物</div>'
    return
  }

  const color = colorOfFor(n)
  const badges: string[] = []
  if (n.faction) badges.push(`<span class="badge" style="background:${color}22;color:${color}">${escapeHtml(n.faction)}</span>`)
  badges.push(n.isNpc ? '<span class="badge npc">NPC</span>' : '<span class="badge op">干员</span>')
  if (n.star) badges.push(`<span class="badge">${'★'.repeat(Math.min(n.star, 6))}</span>`)
  if (n.profession && PROFESSION_LABELS[n.profession])
    badges.push(`<span class="badge">${PROFESSION_LABELS[n.profession]}</span>`)

  const edges = (state.adj.get(id) ?? []).slice().sort((a, b) => b.w - a.w)
  let html = `
    <div class="phead">
      <h2><span class="dot big" style="background:${color}"></span>${escapeHtml(id)}</h2>
      <div class="badges">${badges.join('')}</div>
      ${n.appellation ? `<div class="muted">${escapeHtml(n.appellation)}</div>` : ''}
      ${n.aliases.length ? `<div class="muted">别名：${n.aliases.map(escapeHtml).join(' · ')}</div>` : ''}
    </div>
    <div class="pstats">
      <div><b>${n.lines}</b><span>台词行</span></div>
      <div><b>${n.nfiles}</b><span>出场文件</span></div>
      <div><b>${n.mentioned}</b><span>被提及</span></div>
      <div><b>${n.deg}</b><span>关联人物</span></div>
      <div><b>${Math.round(n.btwn * 1000)}</b><span>中介性‰</span></div>
    </div>
    <div class="pbtns">
      <button id="btnCenter">以此为中心</button>
    </div>
    <div class="pprofile" id="pprofile"></div>
    <h3>关系列表 <small>${edges.length}</small></h3>
    <div class="reltable" id="reltable"></div>`

  el.innerHTML = html

  document.getElementById('btnCenter')!.addEventListener('click', () => jump(id))

  // profile
  fetchProfile(id).then((p) => {
    const box = document.getElementById('pprofile')
    if (!box) return
    if (!p) {
      box.innerHTML = ''
      return
    }
    const rows: string[] = []
    for (const k of ['代号', '性别', '出身地', '生日', '种族', '身高', '战斗经验']) {
      if (p[k]) rows.push(`<div><span>${k}</span><b>${escapeHtml(p[k])}</b></div>`)
    }
    let inner = rows.join('')
    if (p['履历']) inner += `<p class="cv">${escapeHtml(p['履历'])}</p>`
    box.innerHTML = inner
  })

  // relations table (evidence fetched per pair on first expand)
  const table = document.getElementById('reltable')!
  for (const e of edges.slice(0, 200)) {
    const other = e.a === id ? e.b : e.a
    const gn = state.nodes.get(other)
    const types = edgeTypesOf(e)
    const row = document.createElement('div')
    row.className = 'relrow'
    row.innerHTML = `
      <span class="dot" style="background:${gn ? colorOfFor(gn) : '#888'}"></span>
      <span class="rname">${escapeHtml(other)}</span>
      <span class="rtypes">${types.map((t) => `<i class="t-${t}" title="${TYPE_LABELS[t]}">${TYPE_LABELS[t]}</i>`).join('')}</span>
      <span class="rw">${e.w}</span>`
    row.title = '单击查看关系对详情 · 双击跳转其关系网'
    row.addEventListener('click', () => openPairModal(state, e, fetchEvPair, jump))
    row.addEventListener('dblclick', () => jump(other))
    table.append(row)
  }
  if (edges.length > 200) {
    const more = document.createElement('div')
    more.className = 'muted more'
    more.textContent = `…仅显示前 200 / ${edges.length} 条（按权重排序）`
    table.appendChild(more)
  }
}

export function renderRank(
  state: AppState,
  jump: (id: string) => void,
  fetchEv: FetchEvPair,
) {
  const metric = (document.getElementById('rankMetric') as HTMLSelectElement).value as
    'deg' | 'wdeg' | 'btwn' | 'lines' | 'mentioned' | 'pair'
  const body = document.getElementById('rankBody')!

  if (metric === 'pair') {
    const edges = state.graph.edges.slice().sort((a, b) => b.w - a.w).slice(0, 60)
    body.innerHTML = edges.map((e, i) => {
      const types = edgeTypesOf(e)
      return `<div class="rankrow pairs" data-idx="${i}">
        <span class="rk">${i + 1}</span>
        <span class="rname">${escapeHtml(e.a)} <span class="px">↔</span> ${escapeHtml(e.b)}</span>
        <span class="rtypes">${types.map((t) =>
          `<i class="t-${t}" title="${TYPE_LABELS[t]}">${TYPE_LABELS[t]}</i>`).join('')}</span>
        <b>${e.w}</b></div>`
    }).join('')
    body.querySelectorAll('.rankrow').forEach((r) => {
      r.addEventListener('click', () => {
        document.getElementById('rankModal')!.classList.add('hidden')
        const e = edges[Number((r as HTMLElement).dataset.idx)]
        if (e) openPairModal(state, e, fetchEv, jump)
      })
    })
    return
  }

  const nodes = state.graph.nodes.filter((n) => n.inGraph)
  nodes.sort((a, b) => (b[metric] as number) - (a[metric] as number))
  body.innerHTML = nodes.slice(0, 60)
    .map((n, i) => {
      const v = metric === 'btwn' ? n.btwn.toFixed(4) : n[metric]
      return `<div class="rankrow${n.id === '博士' ? ' doc' : ''}" data-id="${escapeHtml(n.id)}">
        <span class="rk">${i + 1}</span>
        <span class="dot${n.id === '博士' ? ' star' : ''}" style="background:${colorOfFor(n)}"></span>
        <span class="rname">${escapeHtml(n.id)}</span>
        <span class="muted">${escapeHtml(n.faction ?? (n.isNpc ? 'NPC' : ''))}</span>
        <b>${v}</b></div>`
    })
    .join('')
  body.querySelectorAll('.rankrow').forEach((r) => {
    r.addEventListener('click', () => {
      document.getElementById('rankModal')!.classList.add('hidden')
      jump((r as HTMLElement).dataset.id!)
    })
  })
}

// unused export placeholder to keep import symmetry
export function showEvidence(_e: GEdge) {}
