---
name: lite-video
version: 2.8.0-20260826
description: |
  全自动短视频生成引擎（SQLite 状态机 + 门控审批 + 逐阶段验证，三模式）。用户给主题或
  文案，先讨论意图、生成分镜剧本并获批，再按「剧本 → 计划 → 旁白 → 视觉 → 片段 →
  合成」生产带旁白、自适应字幕、背景音乐的成片。三种模式：imageflow 图文模式（图片+运镜）；
  webanim Web动画模式（HTML 动画模板一键引用，确定性逐帧渲染，内置风格库与数据图表/榜单/
  图文卡片模板）；fullvideo 全视频模式（调用 agent 自带的生图/生视频工具，规格与一致性由
  本 skill 控制）。TRIGGER：用户提到"生成视频""做个短视频""一键出片""把这个主题/文案
  做成视频""出一条解说视频"时使用。SKIP：仅要单张图片、剪辑已有视频文件。
---

# lite-video

主题/文案 → 成片的全自动流水线。核心纪律：

1. **先讨论再生成**：任何生产动作前，必须先完成意图讨论 + 分镜剧本 + 用户批准。
2. **门控优先**：剧本与计划必须经用户批准才能进入生产（GATE）。
3. **Evidence before claims**：每个阶段宣称完成前必须跑 `pv_verify.py` 拿证据。
4. **状态机推进**：一切进度以 `production.db`（SQLite）为准，禁止凭记忆判断进度。
5. **一致性由你保证**：工具只做机械执行，全片视觉/叙事一致性由你按
   `assets/guides/consistency.md` 控制。


## 六阶段状态机

```
imageflow : script → plan → tts → visuals   → segments  → compose
webanim   : script → plan → tts → webpages → weblint → webrender → compose
fullvideo : script → plan → tts → keyframes → videogen  → compose
            (门控)  (门控)   旁白    视觉素材     片段生成      剪辑合成
```

门控阶段（script/plan）协议：
1. 完成工作后 `pv_db.py gate --dir <目录> --stage <s> --summary <摘要>` → `awaiting_human`
2. 向用户**完整展示**产物（剧本全文/计划书），请求批准，**结束本回合**
3. 用户批准 → `approve --decision approved` → `complete-stage`
4. 用户要修改 → `approve --decision revision` → 修订后重新 gate
5. 未获批准就 `complete-stage` 会被拒绝（GATE VIOLATION），这是设计如此

非门控阶段协议：
1. `start-stage` → 执行 → `pv_verify.py --stage <s>` → 全部 PASS → `complete-stage`
2. 验证有 FAIL：修复后重跑验证，禁止带病通过
3. weblint（webanim）虽无独立验证脚本，但其检查结果自动写入 verifications，
   同样遵守"先证据后完成"

**反馈纪律（四态，焊入状态机）**：
- 反馈四态：`pending`（新·未读）→ `seen`（已读）→ `fixed`（已修复）→ `resolved`（已解决）。
- `start-stage`/`gate` **入口自动读即标记** pending→seen（焊入，不可绕过、非阻塞）：新反馈在进阶段时即被列出并标 seen，**不必手动 feedback-list**。
- agent 逐条修复后用 `pv_db.py feedback-fix --dir <目录> --id <N> --reason "修复原因"` 标 `fixed`（填原因留痕）。
- `resolved` 由**用户**在面板点"确认已解决"（`fixed→resolved`）。**用户不确认也不阻塞 agent 继续往后走**。
- "未修复"（pending+seen）提醒 agent 修复；"已修复待确认"（fixed）在状态/看板提示用户；resolved 不再列出 → 不重复处理。
- 每次用户回复后也留意新反馈（下次 start-stage/gate 自动捕获并标记）。

随时用 `pv_db.py status --dir <目录>` 看进度；`pv_db.py next-stage --dir <目录>`
看下一步（恢复会话时先跑它；新反馈会在下次 `start-stage`/`gate` 自动读即标记）。


## 三模式选择

**在剧本讨论阶段完成模式决策**（完整决策树见 `assets/guides/mode-selection.md`）：

| 模式 | 视觉来源 | 环境要求 | 适用 |
|---|---|---|---|
| **imageflow** 图文 | 每镜一张图 + Ken Burns 运镜 | 仅需文生图（可占位兜底） | 通用解说、资讯、兜底方案 |
| **webanim** Web动画 | HTML 动画模板 + 确定性逐帧渲染 | playwright + Chromium | 数据图表、榜单、观点卡片、教程 |
| **fullvideo** 全视频 | **agent 自带的生图/生视频工具** | 取决于环境工具 | 叙事短片、强表现力题材 |

决策规则：
1. 环境有图生视频能力（生视频 skill/API/工具）且用户接受成本 → **fullvideo**
2. 有 playwright + Chromium 且题材含数据/榜单/观点 → **webanim**
3. 都不满足 → **imageflow**（永远可用）
4. 模式在 `init --mode` 固化，**禁止中途切换**


## 项目目录约定

```
<用户文件目录>/video_<主题短名>/
├── production.db        # 状态库（唯一事实来源）
├── script.md            # 剧本（阶段1产物）
├── plan.md              # 制作计划（阶段2产物）
├── shots.json           # 分镜表（阶段1产物，set-shots 导入）
├── audio/shot_XX.mp3    # 逐镜旁白
├── images/shot_XX.jpg   # 配图（imageflow）/ 首帧图（fullvideo）
├── webpages/shot_XX.html# [webanim] 逐镜动画页面
├── webrender_raw/       # [webanim] 无音轨原始片段
├── raw_videogen/        # [fullvideo] provider 原始输出
├── segments/shot_XX.mp4 # 逐镜视频片段（三种模式统一）
├── subs.ass             # 自适应字幕
└── final.mp4            # 成片
```


## 资源库索引（一键引用；选型时 Read `assets/guides/assets-catalog.md`）

- **模板库** `assets/templates/`：成熟方案 gsap-story/data-narrative/mermaid-diagram；基础 data-chart/ranking-list/text-card/cute-pop/neon-glow（meta.json）。webanim 用。
- **动画库** `assets/libs/`：gsap/anime/d3/mermaid（渲染器/看板自动注入，禁止 CDN）。页面声明 `<meta name="pv-libs" content="...">`。
- **风格库** `assets/styles/`：flat-motion-graphics/premium-minimalist/clean-professional/cute-pastel/neon-cyber（YAML，配色+字体+动效+生图 prompt 前缀）。选定后全片固定。
- **策略库** `assets/guides/`：mode-selection（模式决策树）/ consistency（一致性）/ cost-strategy（成本）/ webanim-design（动效 cookbook）。
- 完整目录与用法见 `assets/guides/assets-catalog.md`。

## 环节入口（渐进加载，逐环节 Read 对应 ref）

> 每个环节的可执行细节只在对应 ref 文件里。进入某环节前**必须先 Read 其 ref**——未读不得开始该环节任何生产动作。门控/非门控协议见上文「六阶段状态机」。

### Step 0：环境监察与自动准备
▸ **进入前必读** `assets/guides/env-setup.md` —— 未读不得开工。
完成判定：`pv_setup.py` 报告 `✅ 环境就绪` 或就绪但有提醒（TTS/字体缺失须如实告知用户）；硬性缺失禁止开工。

### 阶段 1：剧本讨论（script，门控）
▸ **进入前必读** `assets/guides/stage-script.md` —— 未读不得开始本环节任何生产动作。
目的：意图讨论 → 分镜剧本 → 获批。完成判定：`script.md`+`shots.json` 经 `gate` 展示并获 `approve`（验证标准见 ref）。本环节含 init 后自动启动看板（见 `dashboard.md`）。

### 阶段 2：制作计划（plan，门控）
▸ **进入前必读** `assets/guides/stage-plan.md` —— 未读不得开始本环节任何生产动作。
目的：按模式逐阶写计划。完成判定：`plan.md` 含选定风格/每镜方案/验证标准/成本预估，经 `gate` 展示并获 `approve`（见 ref）。

### 阶段 3 · tts（三种模式相同）
▸ **进入前必读** `assets/guides/stage-tts.md` —— 未读不得开始本环节任何生产动作。
完成判定：每镜旁白存在、时长>0.5s、与 DB 一致（±0.3s）（验证标准见 ref）。

### 阶段 3 · 视觉 — imageflow（图文）
▸ **进入前必读** `assets/guides/stage-imageflow.md` —— 未读不得开始本环节任何生产动作。
完成判定：图可解码；片段时长对齐（±0.3s）、分辨率正确、SAR=1:1（见 ref）。仅当模式=imageflow。

### 阶段 3 · 视觉 — webanim（Web 动画）
▸ **进入前必读** `assets/guides/stage-webanim.md` —— 未读不得开始本环节任何生产动作。
辅读 `assets/guides/webanim-design.md`（动效 cookbook）。完成判定：__seek 契约满足、无违禁调用；片段时长对齐（±0.3s）、分辨率正确、SAR=1:1（见 ref）。仅当模式=webanim。

### 阶段 3 · 视觉 — fullvideo（全视频）
▸ **进入前必读** `assets/guides/stage-fullvideo.md` —— 未读不得开始本环节任何生产动作。
完成判定：首帧可解码；片段时长对齐（±0.5s）、分辨率正确、SAR=1:1（见 ref）。仅当模式=fullvideo。

### 阶段 3 · compose（三种模式相同）
▸ **进入前必读** `assets/guides/stage-compose.md` —— 未读不得开始本环节任何生产动作。
完成判定：成片时长=各镜之和（±1s）、分辨率正确、有音轨、字幕已渲染（见 ref）。

### 预览看板
▸ **进入前必读** `assets/guides/dashboard.md` —— 查看进度/预览/反馈时必读。
看板已在阶段 1 init 后自动启动并报地址（见 `stage-script.md` 步骤 2b）；本 ref 讲能力/反馈闭环/`--stop`/`--status` 手动管控。

### 阶段 4：交付
▸ **进入前必读** `assets/guides/delivery.md` —— 未读不得宣告交付。
完成判定：向用户报告标题/模式/总时长/分镜数/成片路径/各镜概览/验证汇总/累计成本（见 ref）。

### 断点续做（会话恢复）
▸ **恢复会话时必读** `assets/guides/delivery.md`（断点续做节）—— 未读不得续做。
先 `next-stage`/`status` 看卡点；并 `pv_dashboard.py --dir <目录> --start` 拉起看板（自动复用）再报地址。

### 排错
▸ **遇症状时必读** `assets/guides/troubleshooting.md` —— 按症状/排查表对照。

### 边界与禁止
▸ **任何环节都受红线约束**：详见 `assets/guides/boundaries.md`（全文）。摘要见下。

## 红线摘要（全文见 `assets/guides/boundaries.md`）

- 禁止伪造验证结果；验证失败必须修复后重验。
- 禁止跳过门控直接生产；剧本每次修改都要落回 `shots.json` 并重新导入。
- 禁止中途切换模式；网络不可用时如实告知，不用占位音/图/模拟视频冒充交付。
- 计费动作先报预算后登记成本；风格一经选定全片固定；跨镜主体描述必须完整重复，禁止指代。
- 不在用户文件目录外写中间产物。
