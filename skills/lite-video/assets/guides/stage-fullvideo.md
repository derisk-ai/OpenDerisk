# 阶段 3 · keyframes + videogen（fullvideo）

> 本文件由 SKILL.md 的 fullvideo 入口块引用；进入全视频环节时必读。


fullvideo 模式**优先使用 agent 自带的生图/生视频工具、子 agent 或插件**完成素材生成，
本 skill 负责规格、风格与一致性控制，`pv_videogen.py` 仅作为 CLI 类 provider 的
兜底执行器与时长对齐/混音工具。

**4.1 keyframes：首尾帧生成**

1. 用当前环境的生图能力逐镜生成首帧图（prompt = 风格库 `image_prompt_prefix` +
   该镜 `image_prompt` + 首帧构图描述）。规格要求：
   - 分辨率 ≥ 项目规格（1080×1920 项目则 ≥1080×1920）
   - 同一主体跨镜出现时，每镜 prompt 必须完整重复该主体描述（禁止指代）
2. 保存为 `images/shot_XX.jpg`，登记：
   `pv_db.py set-shot --dir <目录> --id N --first-frame-path <path>`
3. 可选尾帧：需要控制镜头落点的镜头额外生成尾帧，
   `set-shot --id N --last-frame-path <path>`
4. 费用登记（`cost-log`）→ `pv_verify.py --stage keyframes` → `complete-stage`

**4.2 videogen：图生视频（两条路线）**

**路线 A（推荐）：agent 原生工具**
1. 用当前环境的图生视频能力（生视频 skill/子 agent/插件），逐镜输入：
   首帧图 + （可选尾帧图）+ 画面描述 + **目标时长**（取 shots 表 duration，
   即该镜旁白时长）
2. 产出保存为 `segments/shot_XX.mp4`（无音轨亦可），登记：
   `pv_db.py set-shot --dir <目录> --id N --segment-path <path>`
3. **时长对齐**：生成模型输出时长往往不可控。偏差 ≤0.5s 可忽略；偏差更大时
   逐镜用变速对齐（片段无音轨时安全）：
   ```bash
   # ratio = 目标时长/实际时长；例：实际 12s、目标 9s → 0.75
   ffmpeg -y -i 原片段.mp4 -vf "setpts=0.75*PTS" -c:v libx264 -preset veryfast \
     -crf 21 -threads 2 -pix_fmt yuv420p -r <fps> -an 对齐片段.mp4
   ```
   对齐后覆盖登记 `set-shot --id N --segment-path <对齐片段路径>`
4. 混入旁白由 compose 前统一处理：确保每镜片段含该镜旁白音轨
   （生成工具若支持音轨输入则直接带；否则用 ffmpeg 混：
   `-i seg.mp4 -i audio/shot_XX.mp3 -c:v copy -c:a aac -shortest`）
5. 费用登记（`cost-log`，生成视频通常按秒计费）

**路线 B（兜底）：CLI provider 命令**
环境只有命令行图生视频工具时：
```bash
python3 scripts/pv_videogen.py --dir <目录> \
    --provider-cmd "kling i2v --image {image} --prompt {prompt} --duration {duration} --out {out}"
```
占位符：`{image}` 首帧 / `{image2}` 尾帧 / `{prompt}` 画面描述 / `{duration}` 秒 /
`{width}` `{height}` / `{out}` 输出。脚本自动做时长对齐 + 混入旁白。
（注入值已做 shlex 转义，防命令注入）

**完成条件**：`pv_verify.py --stage videogen`（时长对齐±0.5s、分辨率、SAR=1:1）
全过 → `complete-stage --stage videogen`。

**禁止**：用 `--simulate` 的输出冒充真实生成结果交付；generate 失败不得用占位图
视频糊弄，应暂停并向用户报告。

