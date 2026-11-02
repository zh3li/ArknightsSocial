#!/usr/bin/env python3
"""Build typed weighted edges + evidence from scan.jsonl -> graph.json (+ ev/).

Edge types per unordered pair {a,b}:
  dlg   - A and B speak within K lines in the same scene
  m_ab  - A's dialogue text mentions B (directed)
  co    - A and B both speak in the same scene
  arc   - co-mentioned in 干员档案 text (directed, aggregated)
  fam   - same family group (families.yaml seed)

Outputs:
  web/public/data/graph.json             nodes + edges (no evidence)
  web/public/data/ev/pairs/{A␟B}.json   full evidence quotes per pair
  web/public/data/profiles.json          archive-derived profiles
"""
from __future__ import annotations

import itertools
import json
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

DLG_WINDOW = 5           # legacy; dlg is now consecutive-turn based
W = {"dlg": 1.0, "men": 1.0, "rec": 2.0, "arc": 3.0, "voc": 5.0, "fam": 60.0}
MIN_MENTION_ONLY = 2     # drop mention-only edges below this many mentions


class PairData:
    __slots__ = ("dlg", "m_ab", "m_ba", "rec", "arc", "voc", "fam",
                 "units", "files", "ev")

    def __init__(self):
        self.dlg = 0
        self.m_ab = 0
        self.m_ba = 0
        self.rec = 0
        self.arc = 0
        self.voc = 0
        self.fam = 0
        self.units: set[int] = set()
        self.files: set[str] = set()
        self.ev: dict[str, list] = defaultdict(list)

    def weight(self, a: str, b: str) -> float:
        men = self.m_ab + self.m_ba
        return (self.dlg * W["dlg"] + men * W["men"] + self.rec * W["rec"]
                + self.arc * W["arc"] + self.voc * W["voc"]
                + self.fam * W["fam"])


def add_ev(pd: PairData, kind: str, rec: dict, extra: dict | None = None):
    e = {"k": kind, "f": rec["f"], "n": rec["n"], "t": rec["t"][:120]}
    if rec.get("s"):
        e["s"] = rec["s"]
    if extra:
        e.update(extra)
    pd.ev[kind].append(e)


def main() -> None:
    t0 = time.time()
    names = common.load_json(common.BUILD_DATA / "names.json")
    extra_nodes = common.load_json(common.BUILD_DATA / "nodes_extra.json")
    units = common.load_json(common.BUILD_DATA / "units.json")
    profiles = common.load_json(common.BUILD_DATA / "profiles.json")

    # ---- node registry ----------------------------------------------------
    nodes: dict[str, dict] = {}
    alias_of: dict[str, list[str]] = defaultdict(list)
    for canon, meta in names["characters"].items():
        nodes[canon] = {"id": canon, **{k: v for k, v in meta.items() if v is not None}}
    for surface, s in names["surfaces"].items():
        if surface != s["can"]:
            alias_of[s["can"]].append(surface)
    for canon, meta in extra_nodes.items():
        nodes[canon] = {"id": canon, "isNpc": True, "lines": meta.get("lines", 0)}

    # ---- stream scan.jsonl ------------------------------------------------
    pairs: dict[tuple[str, str], PairData] = defaultdict(PairData)
    node_lines: Counter[str] = Counter()
    node_files: defaultdict[str, set] = defaultdict(set)
    node_mentioned: Counter[str] = Counter()
    name_in_file: defaultdict[str, set] = defaultdict(set)   # file -> set(canon) for co-file stats

    cur_file = None
    scene_spk: dict[int, list] = {}      # scene -> [(line_no, canon)]
    scene_seen: set[tuple[int, str]] = set()

    def flush_file():
        is_rec = cur_file.startswith("干员密录/")
        for scene, spk in scene_spk.items():
            # dialogue adjacency: consecutive speaker turns only (strict).
            # Same-speaker runs collapse naturally; narration between turns
            # does not break adjacency (speaker-event sequence is used).
            # Events inside 干员密录 files count as 密录 (rec) instead of dlg.
            for i in range(len(spk) - 1):
                n1, c1 = spk[i]
                n2, c2 = spk[i + 1]
                if c1 == c2:
                    continue
                key = (c1, c2) if c1 < c2 else (c2, c1)
                pd = pairs[key]
                if is_rec:
                    pd.rec += 1
                else:
                    pd.dlg += 1
                pd.files.add(cur_file)
                pd.units.add(cur_unit)
                add_ev(pd, "rec" if is_rec else "dlg",
                       {"f": cur_file, "n": n2, "t": line_texts.get(n2, ""),
                        "s": c2},
                       {"o": c1, "on": n1,
                        "ot": line_texts.get(n1, "")[:120]})

    line_texts: dict[int, str] = {}
    cur_unit = 0

    with open(common.BUILD_DATA / "scan.jsonl", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["f"] != cur_file:
                if cur_file is not None:
                    flush_file()
                cur_file = rec["f"]
                cur_unit = rec["u"]
                scene_spk = {}
                scene_seen = set()
                line_texts = {}
            s = rec.get("s")
            if s:
                node_lines[s] += 1
                node_files[s].add(rec["f"])
                scene_spk.setdefault(rec["sc"], []).append((rec["n"], s))
                scene_seen.add((rec["sc"], s))
                line_texts[rec["n"]] = rec["t"]
            name_in_file[rec["f"]].update(rec.get("m", []))
            if s:
                name_in_file[rec["f"]].add(s)
            for t in rec.get("m", []):
                node_mentioned[t] += 1
                name_in_file[rec["f"]].add(t)
                if s and s != t:
                    key = (s, t) if s < t else (t, s)
                    pd = pairs[key]
                    if rec["f"].startswith("干员密录/"):
                        pd.rec += 1
                    elif s < t:
                        pd.m_ab += 1
                    else:
                        pd.m_ba += 1
                    pd.files.add(rec["f"])
                    pd.units.add(rec["u"])
                    add_ev(pd, "rec" if rec["f"].startswith("干员密录/")
                           else "men", rec)
    if cur_file is not None:
        flush_file()

    # ---- archives + voice lines -------------------------------------------
    arc_p = common.BUILD_DATA / "archives.jsonl"
    if arc_p.exists():
        with open(arc_p, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                owner = rec["char"]
                for target, cnt in rec.get("m", {}).items():
                    if owner == target or target not in nodes:
                        continue
                    key = (owner, target) if owner < target else (target, owner)
                    pd = pairs[key]
                    pd.arc += cnt
                    pd.files.add(f"干员档案/{owner}")
                for target, samples in rec.get("ev", {}).items():
                    if owner == target or target not in nodes:
                        continue
                    key = (owner, target) if owner < target else (target, owner)
                    pd = pairs[key]
                    for smp in samples:
                        add_ev(pd, "arc",
                               {"f": f"干员档案/{owner}", "n": smp["n"],
                                "t": smp["t"]},
                               {"o": target})
                for target, cnt in rec.get("voc", {}).items():
                    if owner == target or target not in nodes:
                        continue
                    key = (owner, target) if owner < target else (target, owner)
                    pd = pairs[key]
                    pd.voc += cnt
                    pd.files.add(f"干员语音/{owner}")
                for target, samples in rec.get("vev", {}).items():
                    if owner == target or target not in nodes:
                        continue
                    key = (owner, target) if owner < target else (target, owner)
                    pd = pairs[key]
                    for smp in samples:
                        add_ev(pd, "voc",
                               {"f": f"干员语音/{owner}", "n": smp["n"],
                                "t": smp["t"]},
                               {"o": target})

    # ---- families ---------------------------------------------------------
    # Members are resolved through the alias surface-map so renamed canonicals
    # (初雪→恩雅, 崖心→恩希亚 after story-preferred flips) still match nodes.
    fam_cfg = common.load_yaml(Path(__file__).resolve().parent / "families.yaml")

    def resolve_member(m: str) -> str:
        cur, seen = m, set()
        while cur in names["surfaces"] and cur not in seen:
            seen.add(cur)
            cur = names["surfaces"][cur]["can"]
        return cur

    for grp in fam_cfg.get("families", []):
        raw = grp.get("members", [])
        resolved = [resolve_member(m) for m in raw]
        members = sorted({m for m in resolved if m in nodes})
        dropped = [m for m, r in zip(raw, resolved) if r not in nodes]
        if dropped:
            print(f"  fam[{grp.get('name')}] 跳过未入库成员: {dropped}")
        for a, b in itertools.combinations(members, 2):
            key = (a, b)
            pd = pairs[key]
            pd.fam = 1
            pd.files.add(f"亲属/{grp['name']}")

    # ---- emit edges -------------------------------------------------------
    edges = []
    ev_store: dict[str, dict[str, list]] = {}
    for (a, b), pd in pairs.items():
        if a not in nodes or b not in nodes:
            continue
        if (pd.fam == 0 and pd.dlg == 0 and pd.arc == 0
                and pd.rec == 0 and pd.voc == 0):
            if (pd.m_ab + pd.m_ba) < MIN_MENTION_ONLY:
                continue
        e = {
            "a": a, "b": b,
            "dlg": pd.dlg, "mab": pd.m_ab, "mba": pd.m_ba,
            "rec": pd.rec, "arc": pd.arc, "voc": pd.voc, "fam": pd.fam,
            "nf": len(pd.files),
            "w": round(pd.weight(a, b), 2),
            "u": sorted(pd.units),
            "fu": min(pd.units) if pd.units else 99,
        }
        edges.append(e)
        key = f"{a}␟{b}"
        if pd.ev:
            ev_store[key] = dict(pd.ev)

    # drop edges touching isolated stats-only nodes later in stats.py
    used = {e["a"] for e in edges} | {e["b"] for e in edges}
    node_out = []
    for canon, n in nodes.items():
        node_out.append({
            "id": canon,
            "charId": n.get("charId"),
            "faction": n.get("faction"),
            "factionId": n.get("factionId"),
            "star": n.get("star"),
            "profession": n.get("profession"),
            "appellation": n.get("appellation"),
            "isNpc": bool(n.get("isNpc")),
            "lines": node_lines.get(canon, 0),
            "nfiles": len(node_files.get(canon, ())),
            "mentioned": node_mentioned.get(canon, 0),
            "aliases": alias_of.get(canon, [])[:8],
            "inGraph": canon in used,
        })

    edges.sort(key=lambda e: -e["w"])
    graph = {
        "meta": {
            "built": time.strftime("%Y-%m-%d %H:%M"),
            "nodes": len(node_out),
            "edges": len(edges),
            "weights": W,
        },
        "units": units,
        "nodes": node_out,
        "edges": edges,
    }
    common.dump_json(graph, common.WEB_DATA / "graph.json")
    common.dump_json(profiles, common.WEB_DATA / "profiles.json")

    # per-pair evidence files: ev/pairs/{A␟B}.json (full quotes, no sampling)
    ev_dir = common.WEB_DATA / "ev"
    pairs_dir = ev_dir / "pairs"
    if ev_dir.exists():
        for p in ev_dir.glob("*.json"):
            p.unlink()
        if pairs_dir.exists():
            shutil.rmtree(pairs_dir)
    pairs_dir.mkdir(parents=True, exist_ok=True)
    for key, evs in ev_store.items():
        safe = key.replace("/", "_")
        common.dump_json(evs, pairs_dir / f"{safe}.json")

    print(f"graph: {len(node_out)} nodes, {len(edges)} edges "
          f"in {time.time()-t0:.1f}s")
    print(f"ev pair files: {len(ev_store)}")


if __name__ == "__main__":
    main()
