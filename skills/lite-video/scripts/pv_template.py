#!/usr/bin/env python3
"""模板一键引用：从 assets/templates 取模板 + assets/styles 取风格，
注入数据后生成该镜动画页面，并写入 shots.web_page_path。

用法：
  python3 pv_template.py --dir <项目目录> --shot <N> --template data-chart \
      [--style flat-motion-graphics] --data items.json [--duration 10] \
      [--title 标题] [--subtitle 副标题]

若该镜的 shots 表有 animation_brief（剧本阶段的动画简报），会自动嵌入生成页面
顶部的注释块，作为后续按简报增强动画的依据。

模板占位符约定（见各模板 template.html）：
  尺寸类：{{WIDTH}} {{HEIGHT}} {{DURATION}} 以及字号 {{*_SIZE}}（按高度比例自动）
  风格类：{{BG1}} {{BG2}} {{ACCENT}} {{ACCENT2}} {{BAR_COLORS}}（来自风格库）
  内容类：{{TITLE}} {{SUBTITLE}} {{ITEMS_JSON}} {{TEXT_JSON}} {{HIGHLIGHT_JSON}} 等

--data 文件格式：
  data-chart / ranking-list: {"items":[{"label":"A","value":152000,"display":"152K","name":"OpenClaw","desc":"...","metric":"152K"}, ...]}
  text-card: {"text":"主文","highlight":["关键词"],"kicker":"章节","subtitle":"副题"}

退出码：成功 0；模板/风格不存在、数据缺字段 1。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import connect_db, get_project

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(SKILL_DIR, "assets", "templates")
STYLES_DIR = os.path.join(SKILL_DIR, "assets", "styles")


def load_style(name):
    path = os.path.join(STYLES_DIR, name + ".yaml")
    if not os.path.exists(path):
        avail = [f[:-5] for f in os.listdir(STYLES_DIR) if f.endswith(".yaml")]
        raise SystemExit("风格不存在: %s（可选：%s）" % (name, ", ".join(avail)))
    injection = {}
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        injection = (doc.get("visual_language") or {}).get("template_injection") or {}
    except ImportError:
        # 无 PyYAML 时用简单解析（只取 template_injection 块的键值）
        with open(path, "r", encoding="utf-8") as f:
            in_block, key = False, None
            for line in f:
                s = line.rstrip()
                if s.strip() == "template_injection:":
                    in_block = True
                    continue
                if in_block:
                    if s and not s.startswith(" "):
                        break
                    if ":" in s:
                        k, v = s.split(":", 1)
                        k = k.strip(); v = v.strip()
                        if v.startswith("["):
                            injection[k] = v
                        elif v.startswith('"') and v.endswith('"'):
                            injection[k] = v[1:-1]
                        else:
                            injection[k] = v
    # 默认值兜底
    injection.setdefault("BG1", "#0B1026")
    injection.setdefault("BG2", "#2B1A4E")
    injection.setdefault("ACCENT", "#EC4899")
    injection.setdefault("ACCENT2", "#06B6D4")
    injection.setdefault("BAR_COLORS",
                         '["#7C3AED", "#EC4899", "#06B6D4", "#F59E0B", "#10B981", "#EF4444"]')
    return injection


def build_page(template, style_name, data, width, height, duration, title, subtitle):
    tpl_path = os.path.join(TEMPLATES_DIR, template, "template.html")
    if not os.path.exists(tpl_path):
        avail = os.listdir(TEMPLATES_DIR)
        raise SystemExit("模板不存在: %s（可选：%s）" % (template, ", ".join(avail)))
    with open(tpl_path, "r", encoding="utf-8") as f:
        html = f.read()

    inj = load_style(style_name)

    # 字号按高度比例
    sizes = {
        "TITLE_SIZE": int(height * 0.040),
        "SUB_SIZE": int(height * 0.021),
        "LBL_SIZE": int(height * 0.017),
        "VAL_SIZE": int(height * 0.020),
        "CTR_SIZE": int(height * 0.055),
        "CAP_SIZE": int(height * 0.016),
        "NAME_SIZE": int(height * 0.019),
        "DESC_SIZE": int(height * 0.015),
        "METRIC_SIZE": int(height * 0.022),
        "RANK_SIZE": int(height * 0.020),
        "KICKER_SIZE": int(height * 0.015),
        "TEXT_SIZE": int(height * 0.026),
        "EMOJI_SIZE": int(height * 0.055),
        "FLOAT_SIZE": int(height * 0.028),
        # 成熟方案模板（gsap-story / data-narrative / mermaid-diagram）
        "NUM_SIZE": int(height * 0.020),
        "STEP_SIZE": int(height * 0.020),
        "NARR_SIZE": int(height * 0.020),
        "AX_SIZE": int(height * 0.016),
        "NODE_SIZE": int(height * 0.017),
    }
    repl = {
        "WIDTH": str(width), "HEIGHT": str(height),
        "DURATION": "%.2f" % duration,
        "BAR_W": str(max(10, 80 // max(len(data.get("items", [])), 1))),
        "PAD": str(int(height * 0.012)),
        "CARD_PAD": str(int(height * 0.03)),
        "GAP": str(int(height * 0.010)),
        "BADGE": str(int(height * 0.030)),
        "BAR_H": str(int(height * 0.005)),
        "CARD_H": str(int(height * 0.38)),
        "W": str(width),
        "TITLE": title or "",
        "SUBTITLE": subtitle or "",
        "CAPTION": data.get("caption", ""),
        "KICKER": data.get("kicker", ""),
        "UNIT_SUFFIX": data.get("unit_suffix", ""),
        "EMOJI": data.get("emoji", ""),
        "COUNTER_VALUE": str(data.get("counter_value", 0)),
        "DIAGRAM_MMD": data.get("diagram", ""),
        # 成熟方案模板布局变量
        "CPAD": str(int(height * 0.016)),
        "CPADX": str(int(height * 0.020)),
        "SGAP": str(int(height * 0.014)),
        "NUM": str(int(height * 0.040)),
        "NARR_H": str(int(height * 0.07)),
        # 页面级布局：水平内边距（防卡片右缘裁切）+ 文本色（跟随风格明暗）
        "PAGE_PAD": str(int(width * 0.06)),
        "TEXT_COLOR": inj.get("TEXT_COLOR", "#FFFFFF"),
    }
    repl.update(sizes)
    for k, v in inj.items():
        repl[k] = v

    # JSON 类占位符
    repl["ITEMS_JSON"] = json.dumps(data.get("items", []), ensure_ascii=False)
    repl["TEXT_JSON"] = json.dumps(data.get("text", ""), ensure_ascii=False)
    repl["HIGHLIGHT_JSON"] = json.dumps(data.get("highlight", []), ensure_ascii=False)
    repl["STEPS_JSON"] = json.dumps(data.get("steps", []), ensure_ascii=False)
    repl["CHART_JSON"] = json.dumps(data.get("chart", {}), ensure_ascii=False)
    repl["DIAGRAM_JSON"] = json.dumps(data.get("diagram", ""), ensure_ascii=False)

    out = html
    for k, v in repl.items():
        out = out.replace("{{%s}}" % k, str(v))
    # 残留占位符检测
    import re

    leftovers = re.findall(r"\{\{([A-Z_0-9]+)\}\}", out)
    if leftovers:
        raise SystemExit("模板占位符未完全填充: %s" % ", ".join(set(leftovers)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--shot", type=int, required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--style", default="flat-motion-graphics")
    ap.add_argument("--data", required=True, help="内容数据 JSON 文件")
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--duration", type=float,
                    help="覆盖该镜时长（默认用 shots 表 TTS 时长）")
    args = ap.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        if pr["mode"] != "webanim":
            raise SystemExit("当前项目是 %s 模式，pv_template 仅用于 webanim 模式" % pr["mode"])
        row = conn.execute("SELECT * FROM shots WHERE id=?", (args.shot,)).fetchone()
        if not row:
            raise SystemExit("shot %d 不存在" % args.shot)
        dur = args.duration or float(row["duration"] or 8.0)

        page = build_page(args.template, args.style, data,
                          pr["width"], pr["height"], dur, args.title, args.subtitle)
        # 嵌入动画简报（剧本阶段产物）作为后续增强动画的依据
        brief = (row["animation_brief"] if "animation_brief" in row.keys() else None) or ""
        if brief:
            note = ("<!-- ANIMATION_BRIEF（剧本阶段动画简报，增强动画时按此执行）：\n  %s\n-->\n"
                    % brief.replace("\n", "\n  "))
            page = page.replace("<!DOCTYPE html>", note + "<!DOCTYPE html>", 1)
        pages_dir = os.path.join(args.dir, "webpages")
        os.makedirs(pages_dir, exist_ok=True)
        out = os.path.join(pages_dir, "shot_%02d.html" % args.shot)
        with open(out, "w", encoding="utf-8") as f:
            f.write(page)
        conn.execute("UPDATE shots SET web_page_path=? WHERE id=?", (out, args.shot))
        conn.commit()
        print("动画页面已生成: %s（模板=%s, 风格=%s, 时长=%.1fs）"
              % (out, args.template, args.style, dur))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
