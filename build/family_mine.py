#!/usr/bin/env python3
"""Report-only kinship miner: candidate blood-relation pairs from story text.

Scans scan.jsonl dialogue records for lines that contain BOTH a kinship term
and (speaker + mentioned character) or (two mentioned characters), then
aggregates candidate pairs with sample quotes for human review.

This produces build/data/family_mine_report.md — nothing is auto-applied.
Already-registered family pairs (families.yaml) are marked with ✓.
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

KIN_RE = re.compile(
    r"(姐姐|妹妹|哥哥|弟弟|兄长|胞姐|胞妹|胞弟|胞兄|父亲|母亲|爸爸|妈妈|"
    r"妻子|丈夫|叔父|伯父|姑母|姨母|舅舅|婶婶|侄女|侄子|外甥女|外甥|"
    r"孙女|孙子|外婆|外公|祖父|祖母|爷爷|奶奶|岳父|岳母|血亲|亲生)")
MIN_HITS = 3          # pair needs >= this many kinship co-occurrence lines
MAX_SAMPLES = 2


def main() -> None:
    graph = common.load_json(common.WEB_DATA / "graph.json")
    nodes = {n["id"] for n in graph["nodes"] if n.get("inGraph")}

    # registered family pairs (resolve members like graph.py does)
    fam_cfg = common.load_yaml(Path(__file__).resolve().parent / "families.yaml")
    names = common.load_json(common.BUILD_DATA / "names.json")

    def resolve_member(m: str) -> str:
        cur, seen = m, set()
        while cur in names["surfaces"] and cur not in seen:
            seen.add(cur)
            cur = names["surfaces"][cur]["can"]
        return cur

    registered = set()
    for grp in fam_cfg.get("families", []):
        members = sorted({resolve_member(m) for m in grp.get("members", [])}
                         & nodes)
        for a, b in itertools.combinations(members, 2):
            registered.add((a, b))

    pair_hits: Counter = Counter()
    pair_quotes: defaultdict = defaultdict(list)
    with open(common.BUILD_DATA / "scan.jsonl", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if not KIN_RE.search(rec["t"]):
                continue
            people = ([rec["s"]] if rec.get("s") else []) + rec.get("m", [])
            people = [p for p in people if p in nodes]
            for a, b in itertools.combinations(sorted(set(people)), 2):
                pair_hits[(a, b)] += 1
                if len(pair_quotes[(a, b)]) < MAX_SAMPLES:
                    pair_quotes[(a, b)].append(rec)


    rows = []
    for (a, b), n in pair_hits.most_common():
        if n < MIN_HITS or (a, b) in registered:
            continue
        rows.append((n, a, b))
    print(f"kinship candidates: {len(rows)} pairs (>= {MIN_HITS} hits, "
          f"excluding {len(registered)} registered)")

    out = ["# 亲缘候选挖掘报告（人工复审用，未自动应用）", "",
           f"规则：台词同时包含亲属称谓词与两个人物名，>= {MIN_HITS} 条记为候选。",
           "已登记的家庭对已剔除。方向（谁是姐姐/谁是妹妹）需人工判定。", "",
           f"共 {len(rows)} 对候选。", "",
           "| 人物A | 人物B | 命中 | 样例 |", "|---|---|---|---|"]
    for n, a, b in rows[:150]:
        q = pair_quotes[(a, b)][0]
        quote = q["t"][:40].replace("|", "\\|")
        fshort = q["f"].split("/")[-1]
        out.append(f"| {a} | {b} | {n} | 「{quote}」({q.get('s') or '旁白'}@{fshort}:{q['n']}) |")
    (common.BUILD_DATA / "family_mine_report.md").write_text(
        "\n".join(out) + "\n", encoding="utf-8")
    print("report -> build/data/family_mine_report.md")


if __name__ == "__main__":
    main()
