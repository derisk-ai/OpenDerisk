# 阶段 3 · visuals（imageflow 图文）

> 本文件由 SKILL.md 的 imageflow 入口块引用；进入图文视觉环节时必读。


1. 逐镜生成图片：优先用当前环境可用的文生图能力（生图 skill/工具）；
   prompt = 风格库 `image_prompt_prefix` + 该镜 `image_prompt`。
   保存为 `images/shot_XX.jpg`，然后：
   `pv_db.py set-shot --dir <目录> --id N --image-path <path>`
2. 生图产生费用时按 `assets/guides/cost-strategy.md` 登记 `cost-log`
3. 个别镜头失败用 `pv_placeholder.py --dir <目录>` 兜底（只补缺图镜头），
   并**明确告知用户哪些镜头是占位图**
4. `pv_verify.py --stage visuals` → `complete-stage --stage visuals`

