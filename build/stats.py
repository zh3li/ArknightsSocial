#!/usr/bin/env python3
"""Compute centrality + Louvain communities, merge into graph.json."""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import networkx as nx
import community as community_louvain

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def main() -> None:
    t0 = time.time()
    graph = common.load_json(common.WEB_DATA / "graph.json")
    nodes = {n["id"]: n for n in graph["nodes"]}

    G = nx.Graph()
    for e in graph["edges"]:
        G.add_edge(e["a"], e["b"], weight=e["w"])

    deg = dict(G.degree())
    strength = dict(G.degree(weight="weight"))
    # betweenness with distance = 1/weight (stronger tie = closer)
    dist = {(a, b): 1.0 / max(d["weight"], 0.01) for a, b, d in G.edges(data=True)}
    nx.set_edge_attributes(G, dist, "dist")
    btwn = nx.betweenness_centrality(G, weight="dist", normalized=True)
    part = community_louvain.best_partition(G, weight="weight", random_state=42)

    # name each community after its most-connected member (tie-break: lines, name)
    by_comm: dict[int, list[str]] = {}
    for nid, c in part.items():
        by_comm.setdefault(c, []).append(nid)
    comm_labels = {}
    for c, members in by_comm.items():
        rep = max(members, key=lambda m: (deg.get(m, 0),
                                          nodes[m].get("lines", 0),
                                          m))
        comm_labels[str(c)] = rep

    # deterministic global layout: per-community weighted spring, communities
    # packed on a Vogel (golden-angle) spiral sized by member count.
    # Stored as node["pos"] = [x, y]; the web full-network view uses a preset
    # layout with these coordinates instead of running fcose on ~1.2k nodes.
    golden = math.radians(137.508)
    pos_all: dict[str, list[float]] = {}
    area = 0.0
    for i, (c, members) in enumerate(
            sorted(by_comm.items(), key=lambda kv: -len(kv[1]))):
        sub = G.subgraph(members)
        if len(members) > 1:
            sp = nx.spring_layout(sub, weight="weight", seed=42,
                                  iterations=100)
        else:
            sp = {members[0]: [0.0, 0.0]}
        xs = [float(p[0]) for p in sp.values()]
        ys = [float(p[1]) for p in sp.values()]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        s = math.sqrt(len(members))          # community "radius"
        area += s * s
        r = 1.9 * math.sqrt(area)            # spiral radius grows with area
        theta = i * golden
        ox, oy = r * math.cos(theta), r * math.sin(theta)
        for nid, p in sp.items():
            pos_all[nid] = [
                round((float(p[0]) - cx) / span * 2 * s + ox, 1),
                round((float(p[1]) - cy) / span * 2 * s + oy, 1),
            ]

    # collision relaxation: push too-close pairs apart (hubs get more
    # clearance, scaled by degree); deterministic, few passes
    ids_l = sorted(pos_all)
    want = {nid: 1.0 + min(deg.get(nid, 0), 260) / 90.0 for nid in ids_l}
    for _ in range(24):
        moved = 0
        for i, a in enumerate(ids_l):
            pa = pos_all[a]
            for b in ids_l[i + 1:]:
                pb = pos_all[b]
                dx, dy = pa[0] - pb[0], pa[1] - pb[1]
                d2 = dx * dx + dy * dy
                need = want[a] + want[b]
                if d2 >= need * need * 0.25 or d2 < 1e-9:
                    continue
                d = math.sqrt(d2)
                push = (need * 0.5 - d) * 0.5
                ux, uy = dx / d, dy / d
                pos_all[a] = [pa[0] + ux * push, pa[1] + uy * push]
                pos_all[b] = [pb[0] - ux * push, pb[1] - uy * push]
                pa = pos_all[a]
                moved += 1
        if not moved:
            break

    for nid, n in nodes.items():
        n["deg"] = deg.get(nid, 0)
        n["wdeg"] = round(strength.get(nid, 0.0), 1)
        n["btwn"] = round(btwn.get(nid, 0.0), 6)
        n["comm"] = part.get(nid, -1)
        if nid in pos_all:
            n["pos"] = pos_all[nid]

    graph["meta"]["stats"] = {
        "communities": len(set(part.values())),
        "computed": time.strftime("%Y-%m-%d %H:%M"),
    }
    graph["meta"]["commLabels"] = comm_labels
    common.dump_json(graph, common.WEB_DATA / "graph.json")
    top = sorted(nodes.values(), key=lambda n: -n["deg"])[:10]
    print(f"stats done in {time.time()-t0:.1f}s, "
          f"{len(set(part.values()))} communities")
    print("top degree:", [(n['id'], n['deg']) for n in top])


if __name__ == "__main__":
    main()
