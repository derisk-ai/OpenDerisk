# 资源库（模板 / 风格 / 动画库 一键引用）

> 本文件由 SKILL.md 的资源库索引入口块引用；选模板/风格/库时查。


内置资源让 agent 不必从零发明，直接引用复用：

**模板库 `assets/templates/`**（webanim 模式用，见各目录 `meta.json`）：

成熟方案模板（**优先使用**，基于内置动画库，质量有保障）：
- `gsap-story` **方案A** GSAP 分步叙事：要点卡片交错入场（轻量快速，科普/要点）
- `data-narrative` **方案B** 数据叙事：D3 图表 + 时间分步高亮叙述（数据演进/强叙事）
- `mermaid-diagram` **方案C** 逻辑图解：Mermaid 流程图 + 节点逐步点亮（架构/流程/推理）

基础模板（纯 CSS/JS，零库依赖）：
- `data-chart` 数据图表：柱状图生长 + 计数器滚动（榜单/对比/增长）
- `ranking-list` 榜单入场：条目逐条滑入 + 进度条（Top N/热门排行）
- `text-card` 图文卡片：逐字点亮 + 关键词高亮 + 光斑（观点/金句/过渡）
- `cute-pop` 可爱弹跳：果冻弹跳入场 + 表情装饰 + 漂浮星光（轻松可爱内容）
- `neon-glow` 霓虹流光：辉光脉冲 + 扫描线 + 赛博网格 + 数字滚动（科技酷炫）

**内置动画库 `assets/libs/`**（成熟方案模板的依赖，渲染器/看板自动注入，
**禁止改用 CDN**——渲染环境可能无外网）：
- `gsap` 3.12.5 / `anime` 3.2.2 / `d3` 7.9.0 / `mermaid` 10.9.1
- 页面声明方式：`<meta name="pv-libs" content="gsap,d3">`（写进模板/手写页面）
- 确定性用法与避坑见 `assets/guides/webanim-design.md`（**写页面前必读**）

**风格库 `assets/styles/`**（YAML，含配色/字体/动效节奏/生图 prompt 前缀）：
- `flat-motion-graphics` 活力现代（社媒/榜单，快）
- `premium-minimalist` 高级克制（品牌/深度分析，慢）
- `clean-professional` 明亮专业（教程/汇报，中）
- `cute-pastel` 粉彩可爱（生活/情感向，中）
- `neon-cyber` 赛博霓虹（科技/未来感，快）

风格文件中的 `template_injection` 段是 webanim 模板的配色注入源；
`asset_generation.image_prompt_prefix/consistency_anchors` 是 imageflow/fullvideo
生图时的风格锚点。**选定一个风格后全片固定，不得中途更换。**

**策略库 `assets/guides/`**（方法论，写剧本/计划前读）：
- `mode-selection.md` 模式决策树与降级规则
- `consistency.md` 全片一致性控制清单
- `cost-strategy.md` 成本登记与预算策略
- `webanim-design.md` **动效设计 cookbook**：让动画更酷/更可爱/更丰富的配方、
  确定性契约、手写页面骨架、模板选择速查——手写动画页面前必读

