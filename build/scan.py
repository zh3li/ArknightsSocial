#!/usr/bin/env python3
"""Corpus scan: speakers, scenes, mentions across all story text.

Two passes:
  1) speaker histogram -> promote frequent unknown NPCs as canonical nodes
  2) full scan with Aho-Corasick mention detection -> build/data/scan.jsonl

Also scans 干员档案 for archive-mentions (archives.jsonl) and profiles
(profiles.json).  Write build/data/nodes_extra.json for promoted NPCs.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import ahocorasick

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from resolve import load_resolver

MIN_NPC_LINES = 30          # unknown speaker promotion threshold
MARKER_RE = re.compile(r"^\((灰幕|旁白)\)$")
BRANCH_RE = re.compile(r"^分支\d+：")
SCENE_SPLIT_BLANKS = 2      # >=2 consecutive blank lines also split scenes


# ---------------------------------------------------------------------------
def build_units() -> list[dict]:
    """Story units (chapters) in timeline order."""
    seen: dict[tuple[str, str], int] = {}
    units: list[dict] = []
    for _, rel, cat, chapter in common.iter_story_files():
        key = (cat, chapter)
        if key in seen:
            continue
        if cat in common.FLAT_CATEGORIES:
            name = cat
        else:
            name = f"{cat}/{chapter}"
        seen[key] = len(units)
        units.append({"id": len(units), "cat": cat, "chapter": chapter, "name": name})
    # order: by category order then chapter numeric
    units.sort(key=lambda u: (common.CATEGORY_ORDER.get(u["cat"], 99),
                              common.chapter_sort_key(u["chapter"] or u["cat"])))
    for i, u in enumerate(units):
        u["id"] = i
    return units


def unit_index(units) -> dict[tuple[str, str], int]:
    return {(u["cat"], u["chapter"]): u["id"] for u in units}


# ---------------------------------------------------------------------------
class MentionAutomaton:
    """Aho-Corasick over all character surfaces (len>=2) + blocker words.

    Blockers (mention_blockers in aliases.yaml) are frequent common words
    that contain a character name (维多利亚 ⊃ 多利). They consume the span
    via leftmost-longest matching but emit no mention (canonical None).
    """

    def __init__(self, surfaces: dict[str, dict], blockers: list[str] | None = None):
        self.auto = ahocorasick.Automaton()
        for surface, s in surfaces.items():
            if len(surface) < 2:
                continue
            self.auto.add_word(surface, (surface, s["can"]))
        for b in blockers or []:
            if len(b) >= 2:
                self.auto.add_word(b, (b, None))
        self.auto.make_automaton()

    def mentions(self, text: str, exclude: set[str]) -> list[str]:
        """Leftmost-longest non-overlapping matches -> unique canonicals."""
        matches = [(end, val) for end, val in self.auto.iter(text)]
        # pyahocorasick yields (end_index, value) with end inclusive
        matches.sort(key=lambda x: (x[0] - len(x[1][0]), -x[0]))  # start, longest
        out: list[str] = []
        last_end = -1
        for end, (surface, can) in matches:
            start = end - len(surface) + 1
            if start <= last_end:
                continue
            last_end = end
            if can is None or can in exclude:
                continue
            out.append(can)
        # dedup keep order
        seen, ded = set(), []
        for c in out:
            if c not in seen:
                seen.add(c)
                ded.append(c)
        return ded

    def contains_canonicals(self, name: str) -> set[str]:
        return {val[1] for _, val in self.auto.iter(name) if val[1] is not None}


# ---------------------------------------------------------------------------
def fast_resolve(name, resolver, auto, generic_extra, generic_patterns):
    """resolve() with automaton-backed contains-rule (C speed)."""
    uncertain = False
    n = name.strip()
    if len(n) > 1 and n[-1] in "？？?":
        n = n[:-1]
        uncertain = True
    if not n or set(n) <= set("？？?"):
        return "", "unknown", True
    s = resolver.surfaces.get(n)
    if s:
        return s["can"], s["tier"], uncertain
    if n in resolver.ambiguous:
        return n, "ambiguous", uncertain
    hits = auto.contains_canonicals(n)
    if len(hits) == 1:
        return hits.pop(), "derived", uncertain
    if n in generic_extra or any(p in n for p in generic_patterns):
        return n, "generic", uncertain
    return n, "unknown", uncertain


# ---------------------------------------------------------------------------
def pass1_speakers(resolver, auto, generic_extra, generic_patterns):
    """Histogram of raw speakers; return Counter."""
    hist: Counter[str] = Counter()
    for path, rel, cat, chapter in common.iter_story_files():
        if cat == "干员档案":
            continue
        for line in common.read_lines(path):
            m = common.SPEAKER_RE.match(line.strip())
            if m and m.group(1):
                hist[m.group(1)] += 1
    return hist


def promote_npcs(hist, resolver, auto, generic_extra, generic_patterns):
    """Frequent unknown speakers become canonical NPC nodes (accumulate)."""
    promoted: dict[str, dict] = {}
    cfg = common.load_yaml(Path(__file__).resolve().parent / "aliases.yaml")
    seed = set(cfg.get("npc_seed", []))
    excluded = set(cfg.get("exclude", []))
    acc: Counter[str] = Counter()
    for raw, n_lines in hist.items():
        can, tier, unc = fast_resolve(raw, resolver, auto, generic_extra,
                                      generic_patterns)
        if tier == "unknown" and can:
            acc[can] += n_lines
    for can, total in acc.items():
        if can in excluded:
            continue
        if total >= MIN_NPC_LINES or can in seed:
            promoted[can] = {"isNpc": True, "lines": total}
    # seeds that never speak (mention-only entities) still become nodes
    for can in seed - set(promoted):
        if can not in excluded:
            promoted[can] = {"isNpc": True, "lines": acc.get(can, 0)}
    return promoted


# ---------------------------------------------------------------------------
def pass2_scan(resolver, auto, generic_extra, generic_patterns, units, uidx,
               promoted):
    out = open(common.BUILD_DATA / "scan.jsonl", "w", encoding="utf-8")
    t0 = time.time()
    n_rec = 0
    stats = Counter()
    for path, rel, cat, chapter in common.iter_story_files():
        if cat == "干员档案":
            continue
        unit = uidx[(cat, chapter)]
        lines = common.read_lines(path)
        scene = 0
        blanks = 0
        for i, raw_line in enumerate(lines):
            if i == 0:
                continue  # file title
            stripped = raw_line.strip()
            if not stripped:
                blanks += 1
                if blanks == SCENE_SPLIT_BLANKS:
                    scene += 1
                continue
            blanks = 0
            if MARKER_RE.match(stripped):
                scene += 1
                continue
            if stripped.startswith("选项：") or BRANCH_RE.match(stripped):
                continue

            m = common.SPEAKER_RE.match(stripped)
            can = text = None
            raw_speaker = ""
            uncertain = False
            if m:
                raw_speaker = m.group(1)
                text = m.group(2).strip()
                can, tier, uncertain = fast_resolve(
                    raw_speaker, resolver, auto, generic_extra, generic_patterns)
                if tier in ("generic", "ambiguous") or not can:
                    can = None          # no node, but text may mention others
                elif tier == "unknown":
                    if can in promoted:
                        pass            # promoted NPC
                    else:
                        can = None      # one-off unknown: no node
            else:
                text = stripped         # narration line

            if not text:
                continue
            exclude = {can} if can else set()
            # also exclude speaker's own aliases
            mentions = auto.mentions(text, exclude)
            if can is None and not mentions:
                continue
            rec = {
                "f": rel, "u": unit, "n": i + 1, "sc": scene,
                "s": can, "r": raw_speaker if raw_speaker else None,
                "q": 1 if uncertain else 0, "t": text,
            }
            if mentions:
                rec["m"] = mentions
            out.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
            n_rec += 1
            if can:
                stats["speaker_lines"] += 1
            if mentions:
                stats["mention_lines"] += 1
    out.close()
    print(f"pass2: {n_rec} records in {time.time()-t0:.1f}s, {dict(stats)}")


# ---------------------------------------------------------------------------
def scan_archives(resolver, auto, generic_extra, generic_patterns):
    """干员档案: mention counts per owner + voice-line mentions + profiles.

    Output records (archives.jsonl):
      {"char": owner, "m": {target: cnt},
       "ev":  {target: [{"n": line, "t": sentence}]},   # archive evidence
       "voc": {target: cnt},                             # voice-line counts
       "vev": {target: [{"n": line, "t": sentence}]}}    # voice evidence
    """
    arc_dir = common.OVERVIEW / "干员档案"
    npc_map = common.load_yaml(Path(__file__).resolve().parent / "aliases.yaml") \
        ["aliases"].get("npc_map", {})
    out = open(common.BUILD_DATA / "archives.jsonl", "w", encoding="utf-8")
    profiles: dict[str, dict] = {}
    FIELD_RE = re.compile(r"^【([^】]+)】(.*)")
    VOICE_RE = re.compile(r"^\d+\.干员语音")
    SENT_SPLIT = "。！？；"

    # canonical -> known surfaces, to locate names inside long lines
    surf_by_can: dict[str, list[str]] = {}
    for surface, info in resolver.surfaces.items():
        surf_by_can.setdefault(info["can"], []).append(surface)
    for lst in surf_by_can.values():
        lst.sort(key=len, reverse=True)

    def sentence_around(text: str, can: str, width: int = 120) -> str:
        idx = -1
        for sf in surf_by_can.get(can, ()):
            i = text.find(sf)
            if i >= 0 and (idx < 0 or i < idx):
                idx = i
        if idx < 0:
            return text[:width].strip()
        L = 0
        for i in range(idx, -1, -1):
            if text[i] in SENT_SPLIT:
                L = i + 1
                break
        R = len(text)
        for i in range(idx, len(text)):
            if text[i] in SENT_SPLIT:
                R = i + 1
                break
        s = text[L:R].strip()
        if len(s) <= width:
            return s
        rel = max(0, idx - L - 30)
        return s[rel:rel + width]

    for p in sorted(arc_dir.glob("*.txt")):
        m = re.match(r"^(?P<disp>.+)_(?P<cid>(?:char|npc)_\w+)$", p.stem)
        if not m:
            continue
        disp, cid = m.group("disp"), m.group("cid")
        if cid.startswith("npc_"):
            disp = npc_map.get(cid, disp)
        disp = re.sub(r"[（(][^）)]*[）)]", "", disp).strip() or disp
        lines = common.read_lines(p)
        # split archive body / voice section
        v0 = len(lines)
        for i, ln in enumerate(lines):
            if VOICE_RE.match(ln.strip()):
                v0 = i + 1
                break
        body = lines[:v0]
        voice = lines[v0:]

        # archive mentions + evidence
        counts: Counter[str] = Counter()
        ev: dict[str, list] = {}
        for i, ln in enumerate(body):
            s = ln.strip()
            if not s:
                continue
            for can in auto.mentions(s, {disp}):
                counts[can] += 1
                ev.setdefault(can, []).append(
                    {"n": i + 1, "t": sentence_around(s, can)})

        # voice mentions + evidence: blocks separated by blank lines,
        # alternating label / text after the section header
        blocks: list[tuple[int, list[str]]] = []
        cur: list[str] = []
        start = 0
        for i, ln in enumerate(voice):
            if ln.strip():
                if not cur:
                    start = i
                cur.append(ln.strip())
            elif cur:
                blocks.append((start, cur))
                cur = []
        if cur:
            blocks.append((start, cur))
        voc: Counter[str] = Counter()
        vev: dict[str, list] = {}
        for bi, (start, blines) in enumerate(blocks):
            if bi % 2 == 0:      # label block (「交谈1」 etc.)
                continue
            text = "".join(blines)
            for can in auto.mentions(text, {disp}):
                voc[can] += 1
                vev.setdefault(can, []).append(
                    {"n": v0 + start + 1, "t": sentence_around(text, can)})
        rec_out: dict = {"char": disp}
        if counts:
            rec_out["m"] = dict(counts.most_common())
            rec_out["ev"] = ev
        if voc:
            rec_out["voc"] = dict(voc.most_common())
            rec_out["vev"] = vev
        if len(rec_out) > 1:
            out.write(json.dumps(rec_out, ensure_ascii=False,
                                 separators=(",", ":")) + "\n")

        # profile: fields from 基础档案 + 客观履历 paragraph
        prof: dict = {}
        try:
            i0 = next(i for i, ln in enumerate(body) if "基础档案" in ln)
        except StopIteration:
            i0 = None
        if i0 is not None:
            for ln in body[i0 + 1:]:
                s = ln.strip()
                if not s:
                    if prof:
                        break
                    continue
                fm = FIELD_RE.match(s)
                if fm:
                    prof[fm.group(1)] = fm.group(2).strip()
                elif "档案资料" in s or "临床诊断" in s or "综合体检" in s:
                    break
        try:
            j0 = next(i for i, ln in enumerate(body) if "客观履历" in ln)
            para: list[str] = []
            for ln in body[j0 + 1:]:
                s = ln.strip()
                if not s:
                    if para:
                        break
                    continue
                if s.startswith("【") or "档案资料" in s:
                    break
                para.append(s)
            prof["履历"] = "".join(para)[:400]
        except StopIteration:
            pass
        if prof:
            profiles[disp] = prof
    out.close()
    common.dump_json(profiles, common.BUILD_DATA / "profiles.json")
    print(f"archives: {len(profiles)} profiles")


# ---------------------------------------------------------------------------
def main() -> None:
    resolver = load_resolver()
    cfg = common.load_yaml(Path(__file__).resolve().parent / "aliases.yaml")
    blockers = cfg.get("mention_blockers", [])
    auto = MentionAutomaton(resolver.surfaces, blockers)
    generic_extra = resolver.generic_extra
    generic_patterns = resolver.generic_patterns

    units = build_units()
    common.dump_json(units, common.BUILD_DATA / "units.json")
    print(f"units: {len(units)}")
    uidx = unit_index(units)

    print("pass1: speaker histogram ...")
    hist = pass1_speakers(resolver, auto, generic_extra, generic_patterns)
    common.dump_json(dict(hist), common.BUILD_DATA / "speaker_hist.json")
    print(f"pass1: {len(hist)} raw speakers, "
          f"{sum(hist.values())} speaker lines")

    promoted = promote_npcs(hist, resolver, auto, generic_extra, generic_patterns)
    common.dump_json(promoted, common.BUILD_DATA / "nodes_extra.json")
    print(f"promoted NPC nodes: {len(promoted)}")

    # rebuild automaton including promoted NPC names as surfaces
    surfaces = dict(resolver.surfaces)
    for can in promoted:
        surfaces.setdefault(can, {"can": can, "tier": "identity"})
    auto = MentionAutomaton(surfaces, blockers)

    print("pass2: full scan ...")
    pass2_scan(resolver, auto, generic_extra, generic_patterns, units, uidx,
               promoted)

    print("archives ...")
    scan_archives(resolver, auto, generic_extra, generic_patterns)


if __name__ == "__main__":
    main()
