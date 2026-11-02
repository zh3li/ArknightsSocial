#!/usr/bin/env python3
"""Import external alias tables through the agreed safety funnel.

Sources (vendored under build/vendor/):
  - ak-guess alias_zh_CN.json  (MIT, lie5860)  — player slang, strict subset
  - PRTS wiki 角色真名 wikitext  (CC BY-NC-SA)  — official real names

Funnel (as user-approved 2026-10-10):
  accept alias->canonical only if:
    - single target; target in node registry; alias != target
    - alias not already a manual seed / different character / excluded
    - alias is not a role word (generic patterns + review blacklist)
    - alias has >=1 speaker line in the corpus (grounding)
  review list (never auto-applied): role/title words with corpus presence
  rejected: everything else, with reasons in the report

Direction flip: if the alias has MORE speaker lines than the target name,
the alias becomes the canonical (story-preferred) and the target's registry
metadata (charId/faction/...) transfers to it.

Outputs:
  build/data/aliases_imported.json   {alias: {can, src, lines, flip}}
  build/data/alias_import_report.md  review report
  web/public/data/aliases.json       published table (machine-readable)
  ALIASES.md                         published table (human-readable)
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"

# Role/title words the user explicitly ruled out of auto-merge,
# plus ref-stripped newcomers not present in the approved table (2026-10-10):
#   雅儿 — 将进酒 NPC 与耶拉的侍女长化身撞名，归属存疑
#   特雷弗·弗里斯顿 — Friston-3 的人类前世（转制关系），未获批准
REVIEW_EXTRA = {"奶奶", "面包", "老板", "审判官", "三队长", "二队长",
                "雅儿", "特雷弗·弗里斯顿"}


def clean_markup(s: str) -> str:
    s = re.sub(r"\{\{=\}\}", "=", s)
    s = re.sub(r"\{\{popup\|[^|]*\|图标\s*=\s*(.*?)\|内容=.*?\}\}", r"\1", s)
    s = re.sub(r"\{\{[Cc]olor\|[^|]*\|", "", s)
    s = s.replace("}}", "")
    s = re.sub(r"\{\{ja\|", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"<span[^>]*>|</span>|<del>|</del>|<big>|</big>", "", s)
    s = re.sub(r"<br\s*/?>", " → ", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s, flags=re.S)
    s = re.sub(r"\{\{mdi\|[^}]*\}\}", "", s)
    return s.strip()


def parse_prts(wikitext: str) -> list[tuple[str, str]]:
    wt = re.sub(r"<!--.*?-->", "", wikitext, flags=re.S)
    out: list[tuple[str, str]] = []
    for r in [x for x in wt.split("\n|-") if "{{干员头像|" in x]:
        cells = r.split("||")
        if len(cells) < 3:
            continue
        m = re.match(r"\{\{干员头像\|([^}]+)\}\}", cells[0].strip().lstrip("|"))
        if not m:
            continue
        codename = clean_markup(cells[1])
        for var in re.split(r"[→⟶/]+", clean_markup(cells[2])):
            var = var.strip(" \u3000·")
            if not var or len(var) < 2:
                continue
            for c in ([var] if "·" not in var else [var, var.split("·")[0]]):
                c = c.strip('“”"')
                if len(c) >= 2:
                    out.append((c, codename))
    return out


def parse_akguess(d: list) -> list[tuple[str, str]]:
    out = []
    for item in d:
        pat = item["regexp"]
        if re.search(r"[\.\*\[\]\(\)\?\+\{\}\^]", pat):
            continue
        if len(item["values"]) != 1:
            continue
        for alt in pat.split("|"):
            if len(alt.strip()) >= 2:
                out.append((alt.strip(), item["values"][0]))
    return out


def main() -> None:
    # Evaluate against the BASE registry (pre-import) to avoid the stale
    # feedback loop where demoted targets vanish on re-runs.
    os.environ["ARK_RESOLVE_BASE"] = "1"
    from resolve import build_resolver
    base = build_resolver()
    base_json = base.to_json()
    os.environ.pop("ARK_RESOLVE_BASE", None)

    names = base_json
    extra = common.load_json(common.BUILD_DATA / "nodes_extra.json")
    cfg = common.load_yaml(HERE / "aliases.yaml")
    manual = {k: v for k, v in cfg["aliases"].items()
              if isinstance(k, str) and isinstance(v, str)}
    generic_patterns = cfg.get("generic_patterns", [])
    generic_extra = set(cfg.get("generic_extra", []))
    excluded = set(cfg.get("exclude", []))
    ambiguous = set(cfg.get("ambiguous", {}))
    known_canon = set(names["characters"]) | set(extra)
    surfaces = names["surfaces"]

    hist_path = common.BUILD_DATA / "speaker_hist.json"
    if hist_path.exists():
        hist = Counter({k: v for k, v in common.load_json(hist_path).items()})
    else:
        hist = Counter()
        for path, rel, cat, chapter in common.iter_story_files():
            if cat == "干员档案":
                continue
            for line in common.read_lines(path):
                m = common.SPEAKER_RE.match(line.strip())
                if m and m.group(1):
                    hist[m.group(1).rstrip("？？?")] += 1

    def is_roleword(s: str) -> bool:
        return s in generic_extra or any(p in s for p in generic_patterns)

    ak_raw = common.load_json(VENDOR / "ak-guess_alias_zh_CN.json")
    pr_wt = common.load_json(VENDOR / "prts_realnames_wikitext.json")["wikitext"]

    cand: dict[str, dict] = {}
    for a, c in parse_prts(pr_wt):
        cand.setdefault(a, {"canon": set(), "src": set()})
        cand[a]["canon"].add(c)
        cand[a]["src"].add("PRTS")
    for a, c in parse_akguess(ak_raw):
        cand.setdefault(a, {"canon": set(), "src": set()})
        cand[a]["canon"].add(c)
        cand[a]["src"].add("akg")

    accepted: dict[str, dict] = {}
    review: list[tuple] = []
    rejected: Counter = Counter()
    rej_detail: list[tuple] = []

    for alias, info in sorted(cand.items()):
        tgts = info["canon"] & known_canon
        src = "+".join(sorted(info["src"]))
        if not tgts:
            rejected["目标不在节点表"] += 1
            continue
        if len(tgts) != 1:
            rejected["多目标"] += 1
            rej_detail.append((alias, "多目标"))
            continue
        tgt = next(iter(tgts))
        if alias == tgt:
            rejected["即本名"] += 1
            continue
        if alias in manual:
            rejected["已有手工种子"] += 1
            continue
        if alias in surfaces and surfaces[alias]["can"] != tgt:
            rejected["与他人冲突"] += 1
            rej_detail.append((alias, f"已注册为{surfaces[alias]['can']}"))
            continue
        if alias in excluded or alias in ambiguous:
            rejected["剔除/存疑"] += 1
            continue
        if is_roleword(alias) or alias in REVIEW_EXTRA:
            review.append((alias, tgt, src, hist.get(alias, 0)))
            continue
        lines = hist.get(alias, 0)
        if lines == 0:
            rejected["语料无台词"] += 1
            continue
        flip = lines > hist.get(tgt, 0)
        accepted[alias] = {"can": tgt, "src": src, "lines": lines, "flip": flip}

    common.dump_json(accepted, common.BUILD_DATA / "aliases_imported.json")

    # ------------------------------------------------------------------
    # published alias table: manual seeds + imported + promoted NPCs notes
    # ------------------------------------------------------------------
    pub = []
    for alias, info in accepted.items():
        can = alias if info["flip"] else info["can"]
        pub.append({"alias": alias, "canonical": can, "target": info["can"],
                    "source": info["src"], "speakerLines": info["lines"]})
    for surface, can in sorted(manual.items()):
        pub.append({"alias": surface, "canonical": can, "target": can,
                    "source": "manual", "speakerLines": hist.get(surface, 0)})
    pub.sort(key=lambda x: (-x["speakerLines"], x["alias"]))
    common.dump_json({
        "note": "别名→标准人物名 对照表；canonical 为图中节点名",
        "count": len(pub),
        "aliases": pub,
    }, common.WEB_DATA / "aliases.json")

    lines_out = [
        "# 人物别名对照表",
        "",
        "> 由 `build/import_aliases.py` 自动生成，请勿手改。",
        "> 来源: manual(手工种子) / PRTS(prts.wiki 角色真名, CC BY-NC-SA) / "
        "akg([lie5860/ak-guess](https://github.com/lie5860/ak-guess), MIT)",
        "",
        f"共 {len(pub)} 条。`canonical` 为关系图中的节点名。",
        "",
        "| 别名 | 节点名 | 原代号 | 来源 | 台词数 |",
        "|---|---|---|---|---|",
    ]
    for p in pub:
        lines_out.append(
            f"| {p['alias']} | {p['canonical']} | {p['target']} "
            f"| {p['source']} | {p['speakerLines']} |")
    (common.PROJECT_ROOT / "ALIASES.md").write_text("\n".join(lines_out) + "\n",
                                                    encoding="utf-8")

    # ------------------------------------------------------------------
    # review report
    # ------------------------------------------------------------------
    rep = [
        "# 外部别名导入报告", "",
        f"- 候选总数: {len(cand)}",
        f"- 接受: {len(accepted)}  复审: {len(review)}  拒绝: {dict(rejected)}",
        "", "## 接受（已并入）", "",
        "| 别名 | 并入 | 来源 | 台词 | 反向 |", "|---|---|---|---|---|",
    ]
    for a, i in sorted(accepted.items(), key=lambda x: -x[1]["lines"]):
        rep.append(f"| {a} | {i['can']} | {i['src']} | {i['lines']} "
                   f"| {'是' if i['flip'] else ''} |")
    rep += ["", "## 人工复审候选（未并入）", "",
            "| 别名 | 候选 | 来源 | 台词 |", "|---|---|---|---|"]
    for a, t, s, l in sorted(review, key=lambda x: -x[3]):
        rep.append(f"| {a} | {t} | {s} | {l} |")
    rep += ["", "## 冲突/多目标拒绝明细", ""]
    for a, w in rej_detail:
        rep.append(f"- {a} [{w}]")
    (common.BUILD_DATA / "alias_import_report.md").write_text(
        "\n".join(rep) + "\n", encoding="utf-8")

    print(f"accepted={len(accepted)} review={len(review)} rejected={dict(rejected)}")
    print(f"published table: {len(pub)} rows -> web/public/data/aliases.json, ALIASES.md")


if __name__ == "__main__":
    main()
