#!/usr/bin/env python3
"""Name resolution: build surface->canonical table from game tables + manual seeds.

Writes build/data/names.json used by scan.py.
Also importable:  from resolve import load_resolver
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


# ---------------------------------------------------------------------------
class Resolver:
    def __init__(self):
        self.characters: dict[str, dict] = {}   # canonical -> meta
        self.surfaces: dict[str, dict] = {}     # surface -> {can, tier}
        self.ambiguous: dict[str, dict] = {}
        self.generic_patterns: list[str] = []
        self.generic_extra: set[str] = set()
        self._long_surfaces: list[str] = []     # len>=2, for contains-rule

    # -- registration ------------------------------------------------------
    def add_character(self, canonical: str, meta: dict | None = None):
        if canonical not in self.characters:
            self.characters[canonical] = meta or {}
        elif meta:
            cur = self.characters[canonical]
            for k, v in meta.items():
                if v is not None and not cur.get(k):
                    cur[k] = v
        if canonical not in self.surfaces:
            self.surfaces[canonical] = {"can": canonical, "tier": "identity"}
            self._long_surfaces.append(canonical)

    def add_alias(self, surface: str, canonical: str, tier: str = "identity"):
        self.add_character(canonical)
        if surface in self.surfaces:
            if self.surfaces[surface]["can"] != canonical:
                print(f"  ! alias conflict: {surface} -> "
                      f"{self.surfaces[surface]['can']} vs {canonical}")
                return
            return
        self.surfaces[surface] = {"can": canonical, "tier": tier}
        if len(surface) >= 2 and surface not in self._long_surfaces:
            self._long_surfaces.append(surface)

    # -- lookup ------------------------------------------------------------
    def resolve(self, raw: str) -> tuple[str, str, bool]:
        """Return (canonical_or_raw, tier, uncertain).

        tier: identity | derived | generic | ambiguous | unknown
        """
        uncertain = False
        name = raw.strip()
        if len(name) > 1 and name[-1] in "？？?":
            name = name[:-1]
            uncertain = True
        if not name or set(name) <= set("？？?"):
            return "", "unknown", True

        if name in self.surfaces:
            s = self.surfaces[name]
            return s["can"], s["tier"], uncertain
        if name in self.ambiguous:
            return name, "ambiguous", uncertain
        # contains-rule: unknown surface embedding exactly one known name
        # (before generic check: "审判官艾丽妮" -> 艾丽妮)
        hits = set()
        for s in self._long_surfaces:
            if s in name:
                hits.add(self.surfaces[s]["can"])
        if len(hits) == 1:
            return hits.pop(), "derived", uncertain
        if name in self.generic_extra:
            return name, "generic", uncertain
        if any(p in name for p in self.generic_patterns):
            return name, "generic", uncertain
        return name, "unknown", uncertain

    # -- serialization -----------------------------------------------------
    def to_json(self):
        return {
            "characters": self.characters,
            "surfaces": self.surfaces,
            "ambiguous": self.ambiguous,
            "generic_patterns": self.generic_patterns,
            "generic_extra": sorted(self.generic_extra),
        }


# ---------------------------------------------------------------------------
def strip_paren(name: str) -> str:
    return re.sub(r"[（(][^）)]*[）)]", "", name).strip() or name


def build_resolver() -> Resolver:
    r = Resolver()
    cfg = common.load_yaml(Path(__file__).resolve().parent / "aliases.yaml")

    # 1) character_table metadata ------------------------------------------
    ct = common.load_json(common.EXCEL / "character_table.json")
    teams = common.load_json(common.EXCEL / "handbook_team_table.json")

    def faction_of(c):
        for key in ("nationId", "groupId", "teamId"):
            fid = c.get(key)
            if fid and fid in teams:
                return fid, teams[fid].get("powerName", fid)
        return None, None

    table_names: dict[str, str] = {}  # name -> charId (first base wins)
    for cid, c in ct.items():
        name = c.get("name")
        if not name:
            continue
        base = strip_paren(name)
        if base not in table_names:
            table_names[base] = cid
    for name, cid in table_names.items():
        c = ct[cid]
        fid, fname = faction_of(c)
        rar = c.get("rarity", "")
        m = re.search(r"(\d+)", rar)
        r.add_character(name, {
            "charId": cid,
            "factionId": fid,
            "faction": fname,
            "star": int(m.group(1)) if m else None,
            "profession": c.get("profession"),
            "appellation": c.get("appellation"),
        })

    # 2) archive filenames (more current than character_table) -------------
    arc_dir = common.OVERVIEW / "干员档案"
    npc_map = cfg["aliases"].get("npc_map", {})
    arc_names: dict[str, str] = {}
    for p in sorted(arc_dir.glob("*.txt")):
        m = re.match(r"^(?P<disp>.+)_(?P<cid>(?:char|npc)_\w+)$", p.stem)
        if not m:
            continue
        disp, cid = m.group("disp"), m.group("cid")
        if cid.startswith("npc_"):
            disp = npc_map.get(cid, disp)
        disp = strip_paren(disp)  # 阿米娅(医疗) -> 阿米娅 (alter merge)
        arc_names[disp] = cid
    for disp, cid in arc_names.items():
        meta = None
        if disp in r.characters:          # enrich with charId if missing
            if not r.characters[disp].get("charId"):
                r.characters[disp]["charId"] = cid
        else:
            meta = {"charId": cid}
            if cid in ct:
                c = ct[cid]
                fid, fname = faction_of(c)
                mm = re.search(r"(\d+)", c.get("rarity", ""))
                meta.update({
                    "factionId": fid, "faction": fname,
                    "star": int(mm.group(1)) if mm else None,
                    "profession": c.get("profession"),
                    "appellation": c.get("appellation"),
                })
            r.add_character(disp, meta)

    # 3) manual aliases ------------------------------------------------------
    # Manual seeds override table registrations: if a surface was registered
    # as its own character (alter display names like 缄默德克萨斯), demote it
    # to an alias of the canonical and carry over any missing metadata.
    def apply_manual(surface: str, canon: str):
        r.add_character(canon)
        cur = r.surfaces.get(surface)
        if cur and cur["can"] == canon:
            return
        if cur and cur["can"] != surface:
            print(f"  ! alias conflict: {surface} -> {cur['can']} vs {canon}")
            return
        if surface in r.characters:
            meta = r.characters.pop(surface)
            for k, v in meta.items():
                if v is not None and not r.characters[canon].get(k):
                    r.characters[canon][k] = v
        r.surfaces[surface] = {"can": canon, "tier": "identity"}
        if surface not in r._long_surfaces:
            r._long_surfaces.append(surface)

    for surface, canon in cfg["aliases"].items():
        if isinstance(surface, str) and isinstance(canon, str):
            apply_manual(surface, canon)
    for surface, canon in cfg["aliases"].get("npc_aliases", {}).items():
        apply_manual(surface, canon)

    # 3.5) imported aliases (build/import_aliases.py funnel output) ----------
    #      manual seeds above already win; flips transfer registry metadata
    #      Set ARK_RESOLVE_BASE=1 to build the pre-import base registry
    #      (used by import_aliases.py to avoid stale-import feedback loops).
    imp_path = common.BUILD_DATA / "aliases_imported.json"
    if imp_path.exists() and not os.environ.get("ARK_RESOLVE_BASE"):
        imp = common.load_json(imp_path)
        for alias, info in imp.items():
            tgt = info["can"]
            if tgt not in r.characters:
                continue
            if info.get("flip"):
                # story-preferred name becomes canonical; demote the target
                meta = dict(r.characters[tgt])
                r.characters.pop(tgt, None)
                r.add_character(alias, meta)
                r.surfaces[alias] = {"can": alias, "tier": "identity"}
                if alias not in r._long_surfaces:
                    r._long_surfaces.append(alias)
                r.surfaces[tgt] = {"can": alias, "tier": "identity"}
                if tgt not in r._long_surfaces:
                    r._long_surfaces.append(tgt)
            else:
                r.add_alias(alias, tgt, "identity")

    # 4) ambiguous + generics ------------------------------------------------
    r.ambiguous = cfg.get("ambiguous", {})
    r.generic_patterns = cfg.get("generic_patterns", [])
    r.generic_extra = set(cfg.get("generic_extra", []))

    # 5) exclusions (contextual role names that exist in official tables) ---
    for name in cfg.get("exclude", []):
        r.characters.pop(name, None)
        r.surfaces.pop(name, None)
        r._long_surfaces = [s for s in r._long_surfaces if s != name]

    # 5.5) map entities: TRAP/TOKEN table entries that never speak as bare
    #      names are summons/traps/mechanics, not characters (河流/棋子/触手/
    #      基地/法术：…). Genuine story units registered as TRAP/TOKEN
    #      (博士 npc_001_doctor, 特雷西斯, 大帝, 盾卫, 沙地兽, 阿咬 …) have
    #      bare-name dialogue lines and survive. Requires speaker_hist.json
    #      from a previous scan run (skipped on first bootstrap).
    hist_path = common.BUILD_DATA / "speaker_hist.json"
    if hist_path.exists():
        hist = common.load_json(hist_path)
        drop = [k for k, m in list(r.characters.items())
                if (m or {}).get("profession") in ("TRAP", "TOKEN")
                and hist.get(k, 0) == 0]
        for name in drop:
            r.characters.pop(name, None)
            r.surfaces.pop(name, None)
            r._long_surfaces = [s for s in r._long_surfaces if s != name]
        print(f"  map-entity filter: dropped {len(drop)} TRAP/TOKEN non-speakers")

    # 6) path compression: chained aliases point to ultimate canonicals ------
    for s in list(r.surfaces):
        seen = set()
        cur = r.surfaces[s]["can"]
        while cur in r.surfaces and r.surfaces[cur]["can"] != cur and cur not in seen:
            seen.add(cur)
            cur = r.surfaces[cur]["can"]
        r.surfaces[s] = {"can": cur, "tier": r.surfaces[s]["tier"]}

    return r


def load_resolver() -> Resolver:
    """Load from names.json if present, else build from sources."""
    cache = common.BUILD_DATA / "names.json"
    if cache.exists():
        d = common.load_json(cache)
        r = Resolver()
        for canon, meta in d["characters"].items():
            r.add_character(canon, meta)
            r.surfaces[canon] = {"can": canon, "tier": "identity"}
            r._long_surfaces.append(canon)
        # rebuild remaining surfaces after canonicals
        for surface, s in d["surfaces"].items():
            if surface not in r.surfaces:
                r.surfaces[surface] = s
                if len(surface) >= 2:
                    r._long_surfaces.append(surface)
        r.ambiguous = d.get("ambiguous", {})
        r.generic_patterns = d.get("generic_patterns", [])
        r.generic_extra = set(d.get("generic_extra", []))
        return r
    return build_resolver()


def main() -> None:
    r = build_resolver()
    common.dump_json(r.to_json(), common.BUILD_DATA / "names.json")
    print(f"characters: {len(r.characters)}")
    print(f"surfaces:   {len(r.surfaces)}")
    print(f"ambiguous:  {len(r.ambiguous)}")


if __name__ == "__main__":
    main()
