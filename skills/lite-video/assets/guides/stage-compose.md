# 阶段 3 · compose（三种模式相同）

> 本文件由 SKILL.md 的 compose 入口块引用；进入合成环节时必读。


```bash
python3 scripts/pv_subs.py --dir <目录>          # 生成自适应 ASS 字幕
python3 scripts/pv_concat.py --dir <目录> [--bgm <音乐文件>] [--bgm-volume 0.15]
python3 scripts/pv_verify.py --dir <目录> --stage compose
python3 scripts/pv_db.py --dir <目录> complete-stage --stage compose
```

- 字幕由 `pv_subs.py` 按真实分辨率几何计算生成（字号=高度3.4%、行宽按画面算、
  每条≤2行、长旁白自动拆条），**不要手写 SRT**
- fullvideo 路线 A 若片段尚未混旁白，先逐镜混音再合成（见上一节）
- BGM：用户自带则用之；无则跳过（成片仅旁白），不要伪造音乐
- 成片后登记：`pv_db.py add-artifact --dir <目录> --kind final --path <final.mp4>`

