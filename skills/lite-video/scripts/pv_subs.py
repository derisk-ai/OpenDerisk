#!/usr/bin/env python3
"""阶段 compose 前置：由 shots 表生成 ASS 字幕（自适应分辨率）。

替代旧版"固定字号 SRT"方案，修复字幕溢出屏幕的问题：
1. PlayRes 与项目真实分辨率一致（不用 libass 384x288 虚拟分辨率，避免字号失真）
2. 字号 = 画面高度 × 3.4%（随分辨率自适应）
3. 每行最大字数按画面几何计算：可用宽度 = 宽 - 2×边距，中文全角字宽 ≈ 字号
4. 每条字幕事件最多 2 行；超长旁白自动拆成多条事件，按字数比例分配时间窗
5. BorderStyle=1（描边）替代不透明底框，杜绝底框撑出画面

用法：
  python3 pv_subs.py --dir <项目目录> [--output subs.ass]
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import connect_db, get_shots, get_project, find_cjk_font_family


def fmt_ass(t):
    """ASS 时间格式 H:MM:SS.cc"""
    cs = int(round((t - int(t)) * 100))
    s = int(t)
    return "%d:%02d:%02d.%02d" % (s // 3600, (s % 3600) // 60, s % 60, cs)


def smart_wrap(text, max_chars):
    """把文本折成多行，优先标点断句，每行 ≤ max_chars。"""
    text = text.strip()
    lines, cur = [], ""
    punct = "，。！？；：、,"
    for ch in text:
        cur += ch
        if ch in punct and len(cur) >= 6:
            lines.append(cur)
            cur = ""
        elif len(cur) >= max_chars:
            cut = max(cur.rfind(p) for p in punct)
            cut = cut + 1 if cut >= 4 else len(cur)
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    return lines


def group_events(lines, max_lines=2):
    """把折好的行按每条事件最多 max_lines 行分组，返回 [(行列表), ...]。"""
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--output")
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        shots = get_shots(conn)
        if not shots:
            raise SystemExit("shots 表为空")
        W, H = pr["width"], pr["height"]

        # ---- 几何自适应参数 ----
        # 字号取短边（min(W,H)）的 3.4%：竖屏时 H 是长边，按 H 会过大；
        # 用短边保证横竖屏字幕视觉大小一致，且不因竖屏 H 偏大导致字号爆涨/强制换行
        short = min(W, H)
        fontsize = max(24, round(short * 0.034))        # 字号：短边 3.4%
        margin_lr = round(W * 0.06)                     # 左右边距：宽度 6%
        margin_v = round(H * 0.045)                     # 底部边距：高度 4.5%
        usable_w = W - 2 * margin_lr
        # CJK 全角字宽 ≈ 字号；留 4% 余量防描边溢出
        max_chars = max(6, int(usable_w / (fontsize * 1.04)))
        font = find_cjk_font_family()

        out = args.output or os.path.join(args.dir, "subs.ass")

        # ---- 生成事件：长旁白拆多条，按字数分配时间 ----
        events = []
        t = 0.0
        total_chars = 0
        for fr in shots:
            dur = float(fr.get("duration") or 0)
            if dur <= 0:
                raise SystemExit("shot_%02d 无时长，请先运行 pv_tts.py" % fr["id"])
            narration = (fr.get("narration") or "").replace("{", "｛").replace("}", "｝")
            lines = smart_wrap(narration, max_chars)
            groups = group_events(lines, max_lines=2)
            # 按各事件字数比例分配该镜时间窗
            weights = [sum(len(s) for s in g) for g in groups]
            total_w = sum(weights) or 1
            cursor = t
            for g, wgt in zip(groups, weights):
                seg_dur = dur * wgt / total_w
                text = "\\N".join(g)
                events.append((cursor, cursor + seg_dur, text))
                cursor += seg_dur
                total_chars += wgt
            t += dur

        # ---- 写 ASS ----
        head = """[Script Info]
ScriptType: v4.00+
PlayResX: %d
PlayResY: %d
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,%s,%d,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,%d,0,2,%d,%d,%d,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" % (W, H, font, fontsize, max(2.0, fontsize / 28.0), margin_lr, margin_lr, margin_v)

        body = []
        for start, end, text in events:
            body.append(
                "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                % (fmt_ass(start), fmt_ass(end), text)
            )
        with open(out, "w", encoding="utf-8") as f:
            f.write(head + "\n".join(body) + "\n")
        print("ASS 字幕已生成: %s（%d 条事件，字号 %d，每行≤%d 字，画布 %dx%d）"
              % (out, len(events), fontsize, max_chars, W, H))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
