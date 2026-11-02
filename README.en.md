# Arknights Social

**The Arknights social circle: a character relationship network built from story, archives, records, and voice lines.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
![data version](https://img.shields.io/badge/data%20version-2026.11.02-orange)

*Have these operators ever met? Have they spoken? Is one mentioned in the other's archive? From a small street vendor in Yan to the Director-General of a cutting-edge tech company in Columbia — how many hops does it take?*

Readme: [中文](README.md) | [English](README.en.md)

---

## Feature Overview

Arknights Social builds a character relationship network (operators and NPCs alike) from the game's complete story, archive, record, and voice-line text — one-to-one or one-to-many — with every quote traceable to its story chapter and the exact sentence.

Writing fan works? Shipping? Catching up on the lore? All of it gets easier.

---

## 1. Quick Start

**Online**: <https://l1zhe.github.io/ark-social/> (placeholder — replace once deployed)

**Local**:

```bash
git clone https://gitee.com/l1zhe/ark-network.git
cd ark-network/web
npm install
npm run build
npx vite preview
```

## 2. Weights

| Type | Rule | Weight |
| --- | --- | --- |
| Dialogue | direct dialogue in story text | ×1 |
| Mention | explicit name/codename mention in story text | ×1 |
| Record | dialogue & mentions inside operator records | ×2 |
| Archive | mentions inside archive text | ×3 |
| Voice | mentions inside voice lines | ×5 |
| Kinship | hand-curated in families.yaml | ×60 |

Edge weight = Σ(event count × per-event weight).

---

## 3. Credits

- Game metadata: [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData)
- Story text extraction: [ark_story](https://github.com/HX0922/ark_story.git)

All static assets in this project (story text, operator archives, etc.) are © **Arknights / Hypergryph (Shanghai)**, provided for learning and exchange only. Please contact us for removal in case of infringement.
