# Web 动画设计指南（webanim 模式）

目标：让生成的动画**更酷、更可爱、更丰富**，且**稳定无质量问题**（不错位、不裁切、
不失色）。原则：**优先用成熟方案（内置动画库 + 方案模板），不要每次从 0 手写**。

## 铁律：确定性契约（任何页面必须遵守）

1. 定义 `window.__seek(t)`：画面状态 = 时间 t 的**纯函数**
2. 定义 `window.__duration`（秒）
3. **禁止**：Math.random、Date.now、performance.now、requestAnimationFrame、
   setTimeout/setInterval、fetch（pv_weblint 会拒绝）
4. 一切"随机感"都用**伪随机纯函数**替代：
   `pseudo(i) = frac(sin(i * 12.9898) * 43758.5453)`
5. 一切"循环动画"用**时间的三角函数**表达：`sin(t * ω + φ)`
6. 有异步初始化（Mermaid 渲染、D3 构建）时必须定义 `window.__ready`
   （返回 Promise），渲染器和看板回放都会先等它完成

## 成熟动画库（内置，零 CDN 依赖）

内置于 `assets/libs/`，渲染器与看板自动注入——页面只需声明，**禁止从 CDN 加载**
（渲染环境可能无外网；pv_weblint 会拦截 fetch）：

```html
<meta name="pv-libs" content="gsap,d3">
```

| 库 | 版本 | 确定性用法 |
|---|---|---|
| **gsap** | 3.12.5 | `gsap.timeline({paused:true})` 构建 → `__seek` 里 `tl.time(t)`。⚠️ **禁止对 CSS `opacity:0` 的元素用 `from()`**（GSAP 会把 CSS 值当动画终点，元素永远透明）——一律用 `fromTo(起点, 终点, ...)` |
| **anime** | 3.2.2 | `anime({autoplay:false, ...})` → `anim.seek(t*1000)`。弹性缓动 `easeOutElastic` 做可爱弹跳 |
| **d3** | 7.9.0 | 只做**静态构建**（比例尺/轴/柱/线），不启动过渡动画；动画交给 GSAP 或 `__seek` 直接改属性 |
| **mermaid** | 10.9.1 | 在 `__ready` 里 `mermaid.run()` 渲染一次（静态图），节点入场动画用 GSAP 驱动 `.node`/`.edgePath` |

## 三套成熟方案模板（推荐优先使用）

对应业界三个成熟组合，已做成确定性模板。`pv_template.py --template <名>` 引用：

### 方案 A：gsap-story（轻量快速，新手推荐）
HTML + GSAP 时间轴：要点卡片交错入场 + 进度条 + 收尾字幕。适合中小型科普、
观点递进、要点罗列。数据格式：
```json
{"steps": ["第一步：...", "第二步：...", "第三步：..."], "caption": "收尾文案"}
```

### 方案 B：data-narrative（数据叙事专业向）
D3 柱状图 + GSAP 时间分步叙事（Scrollama 思想适配为时间轴）：图表静态构建，
逐步高亮数据点并推进叙述。适合数据演进、技术方案演进、强叙事场景。数据格式：
```json
{"chart": {"points": [{"label": "2024", "value": 38, "display": "38K"}, ...]},
 "steps": ["2024 提速：...", "2025 爆发：...", ...], "caption": "..."}
```
（steps 第 i 条叙述时高亮第 i 个数据点）

### 方案 C：mermaid-diagram（逻辑图解）
Mermaid 渲染流程图/架构图 + GSAP 节点逐步点亮、连线渐显。适合技术方案、
架构说明、因果推理。数据格式：
```json
{"diagram": "flowchart TD\n  A[输入] --> B{判断}\n  B -->|是| C[输出]", "caption": "..."}
```

## 质量防线（血泪教训，必读）

这些是实测踩过的坑，写成页面后逐项自查：

1. **GSAP `from()` 陷阱**：元素 CSS 初始 `opacity:0` 时，`from({...opacity:0})`
   会把 CSS 值当作动画终点 → 播完仍全透明。**必须 `fromTo`**
2. **布局防裁切**：全局 `box-sizing: border-box`；页面水平内边距用 `{{PAGE_PAD}}`
   （宽度 6%），卡片右缘贴边裁切就是水平内边距太小造成的
3. **文字色跟随风格**：用 `{{TEXT_COLOR}}`，不要硬编码白色——明亮风格
   （clean-professional/cute-pastel）背景是浅色，白字直接消失
4. **异步库必须 `__ready`**：Mermaid/D3 构建未完成就 `__seek` 会拿到空节点
5. **图表撑满容器**：SVG 的 `width:100%` 参照的是父元素而非外层容器（常失效），
   应在 `__ready` 里用 JS 按 viewBox 比例计算像素尺寸（参考 mermaid-diagram 模板）
6. **边标签衬底**：htmlLabels 模式下边标签是 `span.edgeLabel`，直接给
   `background + padding`，不要找 `rect`（不存在）
7. 字号用占位符按高度比例注入，**不要写死像素**
8. 文本含 `{` `}` 时替换为全角（防占位符误匹配）
9. 字体写多个候选并带兜底（沙箱：文泉驿）；页面写完**必须过 pv_weblint.py**

## 动效增强配方（按"酷/可爱/丰富"三档）

### 让动画更酷（科技感/冲击力）

| 效果 | 实现 |
|---|---|
| 辉光脉冲 | `glow = 0.75 + 0.25 * sin(t * 2.4)`，套进 `text-shadow: 0 0 ${40*glow}px 颜色` |
| 扫描线巡逻 | `top = (sin(t*0.8)*0.5+0.5) * H`，一条发光横线 |
| 赛博网格地面 | `perspective(500px) rotateX(58deg)` + 网格背景，入场时 opacity 渐显 |
| 数字滚动 | `Math.round(ease(进度) * 目标值).toLocaleString()` |
| glitch 入场 | 前 0.3s：`translateX(sin(t*90)*8*(1-t/0.3)px)` 高频抖动衰减 |
| RGB 分离 | 两个重叠副本，红/青通道色，水平错位 `3*(1-进度)px` 后归位 |
| 流光柱 | 底部竖线 `height = ease(进度) * H*0.3 * (0.6+0.4*sin(t*1.8+i))` |
| GSAP 专业版 | `tl.fromTo(..., ease:"power4.out")` + `stagger` + 屏幕震动 `x: sin(t*80)*5` |

### 让动画更可爱（亲和力/生命感）

| 效果 | 实现 |
|---|---|
| 果冻弹跳入场 | 缓动 `1 + 2.70158*(x-1)^3 + 1.70158*(x-1)^2`（overshoot 8%），GSAP 用 `ease:"back.out(1.7)"` |
| 呼吸缩放 | `scale(1 + 0.08 * sin(t * 3.0))` 用于表情/头像 |
| 漂浮装饰 | 圆点/星星位置 = 基准 + `sin(t*ω)*振幅`（每装饰物不同 ω、φ） |
| 闪烁星光 | `opacity = max(0, sin(t*2.2 + i*2.1)) * 0.9`，相位错开 |
| 卡片歪头 | 入场时 `rotate((1-ease)*-4deg)` 回正 |
| 逐字弹入 | 每字 `local = 全局进度*总字数 - i`，各自过一遍弹跳缓动（anime 的 `easeOutElastic` 效果更佳） |

### 让动画更丰富（层次/节奏）

| 手段 | 说明 |
|---|---|
| 三层结构 | 背景层（网格/渐变/粒子）+ 主体层（卡片/图表）+ 前景层（光斑/装饰） |
| 错峰入场 | 元素入场时间 `base + i * stagger`（stagger 0.2~0.4s），避免同帧齐发 |
| 节奏公式 | 单镜时间预算：入场 15% → 主体展示 50% → 强调/转折 20% → 收尾字幕 15% |
| 每 2-3 秒一个新元素 | 静止超过 3 秒的画面要加呼吸/漂浮/脉冲保活 |
| 颜色纪律 | 同屏 ≤3 高饱和色，从风格库 `BAR_COLORS` 取序 |

## 手写页面的骨架模板

```html
<head>
  <meta name="pv-libs" content="gsap">   <!-- 按需声明内置库 -->
</head>
<body>
  ...
<script>
  window.__duration = {{DURATION}};
  window.__ready = function () {          /* 有异步初始化才需要 */
    return Promise.resolve();
  };
  (function () {
    var D = window.__duration;
    function ease(x){x=Math.max(0,Math.min(1,x));return 1-Math.pow(1-x,3);}
    function bounce(x){x=Math.max(0,Math.min(1,x));var c1=1.70158,c3=c1+1;
      return 1+c3*Math.pow(x-1,3)+c1*Math.pow(x-1,2);}
    function pseudo(i){var s=Math.sin(i*12.9898)*43758.5453;return s-Math.floor(s);}
    window.__seek = function (t) {
      // 一切样式在这里按 t 计算；禁止在此之外修改样式
    };
    window.__seek(0);
  })();
</script>
</body>
```

## 模板选择速查

| 内容类型 | 首选模板（成熟方案） | 备选 |
|---|---|---|
| 要点递进/科普 | **gsap-story**（方案A） | text-card |
| 数据演进/强叙事 | **data-narrative**（方案B） | data-chart |
| 流程/架构/推理 | **mermaid-diagram**（方案C） | — |
| Top N 榜单 | ranking-list | gsap-story |
| 轻松可爱内容 | cute-pop | text-card |
| 科技/未来/酷炫 | neon-glow | gsap-story + neon-cyber 风格 |

## 成熟参考源（灵感库，遵守确定性契约后借鉴）

以下资源用于**借鉴结构与创意**，不能直接照搬（大多依赖 CDN/滚动事件/随机数，
违反本 skill 契约；借鉴后按本文档改造）：

- **CodePen**：搜索 "scrollytelling" / "data visualization" / "GSAP timeline"
- **Observable**（observablehq.com）：数据叙事案例库，fork 后看 D3 用法
- **GSAP Showcase**（greensock.com/showcase）：时间轴编排与缓动搭配范例
- 改造三原则：① 去掉滚动依赖，改为时间分步（Scrollama → 时间轴）；
  ② 随机参数换伪随机纯函数；③ 外部资源（字体/图/库）换内置或占位符注入
