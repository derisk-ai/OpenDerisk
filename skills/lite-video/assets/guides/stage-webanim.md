# 阶段 3 · webpages + weblint + webrender（webanim）

> 本文件由 SKILL.md 的 webanim 入口块引用；进入 Web 动画环节时必读。动效设计 cookbook 见 webanim-design.md。


**4.1 webpages：模板一键引用**

每镜按剧本选定的模板生成动画页面（数据从剧本映射而来）：

```bash
# 先写该镜的数据文件（临时文件即可，放 /tmp）：
#   data-chart / ranking-list: {"items":[{"label":"A","value":152000,"display":"152K","name":"...","desc":"...","metric":"..."}]}
#   text-card: {"text":"主文","highlight":["关键词"],"kicker":"章节","subtitle":"副题"}
python3 scripts/pv_template.py --dir <目录> --shot 1 --template data-chart \
    --style flat-motion-graphics --data /tmp/shot1.json \
    --title "标题" --subtitle "副题"
```

- `--style` 从 `assets/styles/` 选，配色自动注入；时长默认取该镜 TTS 实测时长
- 无合适模板时**可以手写页面**，但必须遵守确定性契约：定义 `window.__seek(t)`
  （画面状态 = 时间的纯函数）、`window.__duration`，禁止 Math.random/Date.now/
  rAF/setTimeout/fetch（完整规则见 pv_weblint.py 的违禁清单）
- **动画简报落地**：`pv_template.py` 会自动把该镜的 `animation_brief` 嵌入生成
  页面顶部注释。生成基础页面后，你应按简报对页面做二次增强（加配方里的动效、
  调整节奏点），再进入 weblint。注意：简报文字中不要出现违禁关键词
  （如 "setTimeout"），以免触发静态扫描误报
- `pv_verify.py --stage webpages` → `complete-stage --stage webpages`

**4.2 weblint：确定性预检**

```bash
python3 scripts/pv_weblint.py --dir <目录>          # 静态扫描 + 无头浏览器动态探测
python3 scripts/pv_db.py --dir <目录> complete-stage --stage weblint   # 检查结果已自动入库
```

有违禁调用或缺 `__seek` 时 FAIL：修改页面后重跑，禁止带病进入渲染。

**4.3 webrender：多进程并发逐帧渲染**

```bash
python3 scripts/pv_webrender.py --dir <目录> [--workers 2]
python3 scripts/pv_verify.py --dir <目录> --stage webrender
python3 scripts/pv_db.py --dir <目录> complete-stage --stage webrender
```

- workers 建议 2~4（每进程一个浏览器实例，内存约 500MB/个）
- 单镜重做：`--shot N --force`；已完成的镜头自动跳过（断点续做）
- 速度参考：沙箱实测约 292ms/帧（1080×1920），6 秒镜头约 30 秒×并发度倒数

