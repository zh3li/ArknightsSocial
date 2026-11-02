
# Arknights Social

**明日方舟社交圈：根据剧情、档案、密录和语音构建的角色关系网。**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
![data version](https://img.shields.io/badge/data%20version-2026.11.02-orange)

*干员之间、NPC之间是否见过面？是否有过交流？是否在档案里提及？从炎国小商贩，到哥伦比亚尖端科技公司的总辖，一共需要几步？*

Readme: [中文](README.md) | [English](README.en.md)

---

## 功能预览

Arknights Social 根据游戏中的全部剧情、档案、密录和语音文本，建立了角色关系网（包括干员、NPC），一对一或一对多，每句话都可以溯源到故事章节、句子本身。

做二创？磕CP？补剧情？都更方便。

---

## 1. 快速开始

**在线使用**：<https://zh3li.github.io/ArknightsSocial/>

**本地部署**：

```bash
git clone https://gitee.com/l1zhe/ark-network.git
cd ark-network/web
npm install
npm run build
npx vite preview
```

## 2. 规则权重

| 类型  | 判定                   | 权重   |
| --- | -------------------- | ---- |
| 对话  | 剧情文本存在直接对话           | ×1   |
| 提及  | 剧情文本直接提及"姓名/代号"      | ×1   |
| 密录  | 密录内对话与提及             | ×2   |
| 档案  | 档案正文提及               | ×3   |
| 语音  | 语音台词提及               | ×5   |
| 亲属  | 根据families.yaml 手工维护 | ×60  |

边权 = Σ(事件次数 × 单次权重)。

---

## 3. 致谢

- 游戏元数据： [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData) 
- 相关文本提取： [ark_story](https://github.com/HX0922/ark_story.git)

本项目所有静态资源（剧情文本、干员档案等）版权均属于 **Arknights / 上海鹰角网络科技有限公司**，仅用于学习与交流，如有侵权请联系删除。

