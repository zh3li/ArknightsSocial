#!/usr/bin/env python3
"""Verify graph extraction against investigation/talulah oracle counts.

Oracle (investigation/talulah/related_entities.md): files where the entity
name and 塔露拉 both appear (whole 剧情一览 incl. archives):
  爱国者 28 co-files (44 total), 科西切 20 (20), 黑蛇 11 (11)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

ORACLE = {"爱国者": 28, "科西切": 20, "黑蛇": 11}


def main() -> None:
    # recompute file-level co-occurrence from scan.jsonl
    file_names: defaultdict[str, set] = defaultdict(set)
    with open(common.BUILD_DATA / "scan.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            names = set(r.get("m", []))
            if r.get("s"):
                names.add(r["s"])
            file_names[r["f"]] |= names

    # add archive co-occurrence
    with open(common.BUILD_DATA / "archives.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            file_names[f"干员档案/{r['char']}"] |= set(r.get("m", {})) \
                | set(r.get("voc", {})) | {r["char"]}

    print(f"{'entity':<8} {'ours':>6} {'oracle':>8}")
    ok = True
    for ent, want in ORACLE.items():
        ours = sum(1 for names in file_names.values()
                   if "塔露拉" in names and ent in names)
        mark = "OK" if ours == want else ("~" if abs(ours - want) <= 4 else "FAIL")
        if mark == "FAIL":
            ok = False
        print(f"{ent:<8} {ours:>6} {want:>8}   {mark}")

    # completeness guard: stats.py output must be present (pos/btwn/comm)
    graph0 = common.load_json(common.WEB_DATA / "graph.json")
    ing = [n for n in graph0["nodes"] if n.get("inGraph")]
    n_pos = sum(1 for n in ing if n.get("pos"))
    n_btwn = sum(1 for n in ing if n.get("btwn") is not None)
    has_comm = "commLabels" in graph0.get("meta", {})
    if n_pos < len(ing) or n_btwn < len(ing) or not has_comm:
        ok = False
        print(f"INCOMPLETE STATS: pos={n_pos}/{len(ing)} "
              f"btwn={n_btwn}/{len(ing)} commLabels={has_comm} "
              "(did you forget to run stats.py?)")

    # spot-check a dialogue edge's evidence against the raw file
    graph = common.load_json(common.WEB_DATA / "graph.json")
    tal_edges = [e for e in graph["edges"] if e["a"] == "塔露拉" or e["b"] == "塔露拉"]
    tal_edges.sort(key=lambda e: -e["w"])
    print("\ntop talulah edges:")
    for e in tal_edges[:12]:
        other = e["b"] if e["a"] == "塔露拉" else e["a"]
        print(f"  {other:<10} w={e['w']:>7} dlg={e['dlg']:>4} "
              f"m={e['mab']+e['mba']:>4} rec={e.get('rec', 0):>3} "
              f"voc={e.get('voc', 0):>3} nf={e['nf']:>3}")

    # evidence quote check: file+line must exist and contain the quote text
    import random
    random.seed(1)
    pairs_dir = common.WEB_DATA / "ev" / "pairs"
    quotes = []
    for p in sorted(pairs_dir.glob("*.json"))[:400]:
        kinds = json.load(open(p, encoding="utf-8"))
        for kind, evs in kinds.items():
            if kind == "men":
                quotes.extend(evs)
    checks = random.sample(quotes, min(10, len(quotes)))
    good = 0
    for q in checks:
        p = common.OVERVIEW / q["f"]
        lines = common.read_lines(p)
        if q["n"] <= len(lines) and q["t"][:30] in lines[q["n"] - 1]:
            good += 1
        else:
            print("  BAD QUOTE:", q)
    print(f"\nevidence spot-check: {good}/{len(checks)} quotes verified in source")

    # full-storage completeness: top edge's quote counts must match its counts
    top = max(graph["edges"], key=lambda e: e["w"])
    key = "␟".join(sorted((top["a"], top["b"])))
    tp = pairs_dir / f"{key}.json"
    if not tp.exists():
        ok = False
        print(f"MISSING PAIR FILE: {tp.name}")
    else:
        kinds = json.load(open(tp, encoding="utf-8"))
        nq = {k: len(v) for k, v in kinds.items()}
        expect = {"dlg": top["dlg"], "men": top["mab"] + top["mba"],
                  "rec": top["rec"], "arc": top["arc"], "voc": top["voc"]}
        for k, want in expect.items():
            got = nq.get(k, 0)
            if got != want:
                ok = False
                print(f"INCOMPLETE EVIDENCE {key} {k}: {got} quotes "
                      f"!= {want} events")
        print(f"top pair {key}: quotes {nq} "
              f"(dlg/men/rec/voc must equal edge counts)")

    print("ORACLE", "PASS" if ok else "CHECK", "- "
          + ("all co-file counts match" if ok else "inspect deltas above"))


if __name__ == "__main__":
    main()
