# 预览看板（实时进度 + 产出预览 + 反馈闭环）

> 本文件由 SKILL.md 的看板入口块引用；看板已在阶段 1 init 后自动启动（见 stage-script.md 步骤 2b）；本文件讲能力/反馈闭环/手动管控。


用户想边做边看效果时，启动本地看板服务：

```bash
# 多项目模式（推荐）：不指定目录，自动扫描出所有项目，列表页点进去看
python3 scripts/pv_dashboard.py [--root <扫描根>] [--depth 3] [--port 8620]

# 单项目模式：只看指定项目（兼容旧用法）
python3 scripts/pv_dashboard.py --dir <目录> [--port 8620] [--bind 127.0.0.1]
```

多项目模式下，看板首页是**项目列表**：自动递归扫描 `--root`（默认当前目录）
下所有含 `production.db` 的目录，每个项目显示标题/模式/阶段进度条/分镜数/
待处理反馈数/是否已出成片/更新时间，点击进入该项目的完整看板
（路由 `/p/<slug>/`，所有预览与反馈功能与单项目模式一致）。

- **看板能力**（纯标准库实现，零第三方依赖，浏览器打开即用）：
  - 流水线进度可视化（阶段状态/门控标识），每 2s 增量同步（分块 diff 更新：
    数据未变化的卡片不重建，用户展开的详情/播放进度/滚动位置不被轮询打断）
  - 逐镜产出预览：旁白音频、配图/首帧、片段/成片播放；旁白文字可展开全文
  - **分镜视觉点击放大**（Lightbox）：图片/视频/动画回放全屏查看，Esc 关闭
  - **剧本/计划 Markdown 渲染**：标题/列表/表格/代码块/引用排版展示，
    支持「全屏阅读」模式
  - **webanim 动画页面实时回放**：`/page/<shot_id>` 注入回放驱动（rAF 循环调用
    `__seek`），浏览器里直接看到动画实际效果；注入只发生在预览副本，
    不改动源文件（确定性不受影响，weblint/渲染照常）
  - 验证记录、成本明细、决策日志
**反馈四态**：提交→`pending`（新·未读）→（`start-stage`/`gate` 自动读即标记）`seen`（已读）→（agent `feedback-fix --id N --reason "原因"`）`fixed`（已修复）→（用户面板点"确认已解决"）`resolved`。看板角标"⏳ N 待处理"=未解决（pending+seen+fixed），resolve 后才清零。`feedback-list --pending` 读即标记；`--seen`/`--fixed`/`--unresolved` 只读复查。

- **反馈闭环**（用户在看板提意见 → agent 必须读回处理）：
  1. 用户在看板表单提交反馈（可指定阶段/分镜），写入 `feedback` 表（状态 `pending`）
  2. 有待处理反馈时，看板顶部显示提醒横幅 + 一键复制的读取命令
  3. **agent 每次推进阶段前/每次用户回复后**必须先跑
     `pv_db.py feedback-list --dir <目录> --pending`（`status`/`next-stage`
     输出也会自动提醒待处理条数）
  4. 按反馈修改对应产物并重跑相关阶段
  5. 处理完执行 `pv_db.py feedback-resolve --dir <目录> --id <N>` 标记完成，
     看板自动同步状态
- **使用时机**：webanim 模式建议在 webpages 阶段完成后启动看板，让用户预览动画
  效果并提反馈再进入渲染；其他模式可在任意阶段启动。交付前用看板做最终验收展示
- 沙箱/远程环境访问：加 `--bind 0.0.0.0`（注意：看板会暴露项目目录静态文件，
  仅限可信网络）
- 旧版本数据库兼容：首次连接自动补齐 `feedback` 表等新结构
- `pv_db.py` 命令参数顺序兼容 `--dir` 在前或在后两种写法


## 手动管控（后台启动 / 停止 / 查询）

看板已在阶段 1 `init` 后**自动后台启动并报地址**（见 `stage-script.md` 步骤 2b）。如需手动管控：

```bash
python3 scripts/pv_dashboard.py --dir <目录> --start    # 后台启动；stdout 打印 DASHBOARD_URL= 地址（端口被占自动避让到 8621..8639）
python3 scripts/pv_dashboard.py --dir <目录> --stop      # 停止
python3 scripts/pv_dashboard.py --dir <目录> --status    # 查询是否在运行
```

- `--start` 非阻塞：fork 后台进程，日志写项目目录 `.dashboard.log`，状态写 `.dashboard.json`；已在运行会自动复用、不重复开端口。
- 调试时可省略 `--start`，直接前台阻塞运行：`--dir <目录>` 单项目，或 `--root`/`--depth` 多项目列表模式，`Ctrl+C` 停止。
