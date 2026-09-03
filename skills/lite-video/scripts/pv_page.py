#!/usr/bin/env python3
"""声明式页面构造器（webanim 手写页进的防错位/防遮挡/精致化基座）。

为什么需要它：手写页用硬编码 SVG `x1/y1/x2/y2` 连 CSS 绝对定位的 div，两份几何
各自手填必然错位；且无防重叠布局、字号随手填会溢出。本构造器把每页拆成**声明式
场景 spec**——节点矩形 + 用 node id 描述的边 + 注解 + 运动(只动 opacity/transform/
glow，不动几何)——然后：

1. 在 Python 里校验节点矩形**不出画布、两两不重叠**；
2. **由节点矩形派生**每条边的端点（取相邻侧中点），SVG 线必然贴合节点 → 错位构造上不可能；
3. 产出统一 neon-cyber 精致 CSS（无全程扫描线）+ `window.__geo`（几何单一源）+ 自动
   节点/边元素引用 `__N`/`__E`，再注入该页的运动 JS；
4. 写回 `webpages/shot_NN.html` 与 `shots.web_page_path`。

运行时仍由 pv_weblint 的矩形几何检查兜底（真实视口多点采样断言无重叠/无错位/无溢出）。

用法：
  python3 pv_page.py --dir <项目目录> --shot <N>
场景 spec 见同目录 scenes.py 的 shot_NN_spec(w,h,dur)。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import connect_db, get_project
from pv_template import load_style

# 颜色键 → hex（与 neon-cyber 一致；inj 兜底由 load_style 保证存在）
def _col(key, inj):
    palette = {
        "cyan": inj.get("ACCENT", "#00F0FF"),
        "magenta": inj.get("ACCENT2", "#FF2E97"),
        "purple": "#7C3AED",
        "green": "#00FF9F",
        "gray": "#94a3b8",
        "white": "#E8F6FF",
    }
    return palette.get(key, key if key.startswith("#") else "#E8F6FF")


def _rect_centres(r):
    return (r["x"] + r["w"] / 2.0, r["y"] + r["h"] / 2.0)


def _edge_endpoints(a, b):
    """由两节点矩形派生连线端点：按中心相对位置选相邻侧中点（正交连线，贴合节点）。"""
    ax, ay = _rect_centres(a)
    bx, by = _rect_centres(b)
    dx, dy = bx - ax, by - ay
    if abs(dx) >= abs(dy):
        # 横向相邻：用左右侧
        if dx >= 0:
            return (a["x"] + a["w"], ay, b["x"], by)
        return (a["x"], ay, b["x"] + b["w"], by)
    # 纵向相邻：用上下侧
    if dy >= 0:
        return (ax, a["y"] + a["h"], bx, b["y"])
    return (ax, a["y"], bx, b["y"] + b["h"])


def _overlaps(a, b, tol=0.0):
    return not (a["x"] + a["w"] <= b["x"] + tol or b["x"] + b["w"] <= a["x"] + tol
                or a["y"] + a["h"] <= b["y"] + tol or b["y"] + b["h"] <= a["y"] + tol)


def validate(spec, W, H):
    """校验节点矩形：不出画布、两两不重叠、必填字段。失败即抛（构造期暴露，不让错位页流到渲染）。"""
    nodes = spec.get("nodes", [])
    ids = set()
    for n in nodes:
        for k in ("id", "x", "y", "w", "h"):
            if k not in n:
                raise SystemExit("node 缺字段 %s: %r" % (k, n))
        if n["id"] in ids:
            raise SystemExit("node id 重复: %s" % n["id"])
        ids.add(n["id"])
        r = n
        if r["x"] < -1 or r["y"] < -1 or r["x"] + r["w"] > W + 1 or r["y"] + r["h"] > H + 1:
            raise SystemExit("node %s 出画布: x=%s y=%s w=%s h=%s (画布 %sx%s)"
                             % (n["id"], r["x"], r["y"], r["w"], r["h"], W, H))
        if r["w"] <= 0 or r["h"] <= 0:
            raise SystemExit("node %s 尺寸非正: %sx%s" % (n["id"], r["w"], r["h"]))
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if _overlaps(nodes[i], nodes[j], tol=2.0):
                raise SystemExit("节点重叠: %s 与 %s（容差内仍交叠）"
                                 % (nodes[i]["id"], nodes[j]["id"]))
    node_ids = {n["id"] for n in nodes}
    for e in spec.get("edges", []):
        if e["from"] not in node_ids or e["to"] not in node_ids:
            raise SystemExit("edge %s 引用了不存在的节点: %s→%s"
                             % (e.get("id"), e["from"], e["to"]))


def _title_html(title, inj):
    """title 支持 str 或 [(text, color_key)] 段，渲染成带色 span。"""
    if title is None:
        return ""
    if isinstance(title, str):
        return title
    parts = []
    for seg in title:
        text, key = seg if isinstance(seg, (list, tuple)) else (seg, None)
        if key:
            parts.append('<span style="color:%s;text-shadow:0 0 12px %s">%s</span>'
                         % (_col(key, inj), _col(key, inj), text))
        else:
            parts.append(text)
    return "".join(parts)


def build_page(spec, width, height, duration, inj):
    validate(spec, width, height)
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    W, H = width, height

    # 派生几何（单一源）：节点中心 + 边端点
    geo_nodes = {}
    for n in nodes:
        cx, cy = _rect_centres(n)
        geo_nodes[n["id"]] = {"x": n["x"], "y": n["y"], "w": n["w"], "h": n["h"],
                              "cx": cx, "cy": cy}
    geo_edges = []
    ep_map = {}
    for e in edges:
        a, b = geo_nodes[e["from"]], geo_nodes[e["to"]]
        x1, y1, x2, y2 = _edge_endpoints(a, b)
        ep_map[e["id"]] = (x1, y1, x2, y2)
        geo_edges.append({"id": e["id"], "from": e["from"], "to": e["to"],
                          "x1": x1, "y1": y1, "x2": x2, "y2": y2})

    # --- CSS（neon-cyber 精致，无扫描线）---
    ACC, ACC2 = _col("cyan", inj), _col("magenta", inj)
    css = """
  html,body{margin:0;padding:0;width:%(W)spx;height:%(H)spx;overflow:hidden;}
  body{background:linear-gradient(165deg,#05060F 0%%,#120826 100%%);
    font-family:"PingFang SC","Noto Sans CJK SC","WenQuanYi Micro Hei",sans-serif;color:#E8F6FF;}
  .bg-grid{position:absolute;inset:0;opacity:.05;pointer-events:none;
    background-image:linear-gradient(#00F0FF 1px,transparent 1px),linear-gradient(90deg,#00F0FF 1px,transparent 1px);
    background-size:80px 80px;}
  .kicker{position:absolute;top:30px;width:100%%;text-align:center;font-size:30px;letter-spacing:6px;color:%(ACC2)s;opacity:0;}
  .title{position:absolute;top:72px;width:100%%;text-align:center;font-size:50px;font-weight:700;letter-spacing:2px;opacity:0;}
  .anno{position:absolute;opacity:0;line-height:1.35;}
  .node{position:absolute;box-sizing:border-box;border-radius:20px;display:flex;flex-direction:column;
    align-items:center;justify-content:center;text-align:center;opacity:0;border:1.5px solid #3E5570;
    background:rgba(255,255,255,0.04);}
  .node .lab{font-size:31px;font-weight:700;line-height:1.2;}
  .node .sub{font-size:24px;color:#94a3b8;margin-top:8px;font-weight:400;}
  .node .mono{font-family:"SF Mono","Menlo",monospace;}
  .c-cyan{color:%(ACC)s;} .c-magenta{color:%(ACC2)s;} .c-purple{color:#C4B5FD;} .c-green{color:%(GRN)s;} .c-gray{color:#94a3b8;}
  .edge{stroke-width:4;opacity:0;fill:none;}
""" % {"W": W, "H": H, "ACC": ACC, "ACC2": ACC2, "GRN": _col("green", inj)}

    # 节点 div
    node_html = []
    for n in nodes:
        col = _col(n.get("color", "white"), inj)
        border = n.get("border", col)
        bg = n.get("bg") or ("rgba(255,255,255,0.04)")
        lab_cls = "mono" if n.get("mono") else ""
        sub_cls = "mono" if n.get("sub_mono") else ""
        if n.get("html"):
            inner = n["html"]
        else:
            inner = '<div class="lab %s %s">%s</div>' % (lab_cls, _colcls(n.get("color", "white")), n["label"])
            if n.get("sub"):
                inner += '<div class="sub %s">%s</div>' % (sub_cls, n["sub"])
        node_html.append(
            '<div class="node" id="%(id)s" data-node="1" '
            'style="left:%(x)spx;top:%(y)spx;width:%(w)spx;height:%(h)spx;'
            'border-color:%(bd)s;background:%(bg)s;">%(inner)s</div>'
            % {"id": n["id"], "x": n["x"], "y": n["y"], "w": n["w"], "h": n["h"],
               "bd": border, "bg": bg, "inner": inner}
        )

    # 边 svg
    svg_lines = []
    for e in edges:
        x1, y1, x2, y2 = ep_map[e["id"]]
        col = _col(e.get("color", "cyan"), inj)
        dash = 'stroke-dasharray="14 12"' if e.get("dashed") else ""
        svg_lines.append(
            '<line class="edge" id="%(id)s" data-edge="1" data-from="%(fr)s" data-to="%(to)s" '
            'x1="%(x1)s" y1="%(y1)s" x2="%(x2)s" y2="%(y2)s" stroke="%(c)s" %(dash)s/>'
            % {"id": e["id"], "fr": e["from"], "to": e["to"],
               "x1": round(x1, 1), "y1": round(y1, 1), "x2": round(x2, 1), "y2": round(y2, 1),
               "c": col, "dash": dash}
        )
    svg = ('<svg id="__svg" style="position:absolute;inset:0;width:100%%;height:100%%;pointer-events:none" '
           'viewBox="0 0 %d %d">%s</svg>' % (W, H, "".join(svg_lines)))

    # 注解（kicker/title 由 spec 顶层，其余 anno）
    anno_html = []
    if spec.get("kicker") is not None:
        anno_html.append('<div class="kicker">%s</div>' % spec["kicker"])
    if spec.get("title") is not None:
        anno_html.append('<div class="title">%s</div>' % _title_html(spec["title"], inj))
    for a in spec.get("annos", []):
        cls_extra = a.get("cls", "")
        is_kt = cls_extra in ("kicker", "title")
        # kicker/title 由其 CSS 定位（top/width/居中），不写内联 left/top 覆盖；其余 anno 用内联定位
        style = ""
        if not is_kt:
            style = "left:%spx;top:%spx;width:%spx;" % (a["x"], a["y"], a.get("w", "auto"))
            if a.get("h"):
                style += "height:%spx;" % a["h"]
        if a.get("align"):
            style += "text-align:%s;" % a["align"]
        if a.get("size"):
            style += "font-size:%spx;" % a["size"]
        col = a.get("color")
        cls = " ".join(c for c in ("anno", cls_extra, _colcls(col)) if c)
        text = a.get("text", "")
        body = a.get("html") or (_title_html(text, inj) if isinstance(text, list) else text)
        anno_html.append('<div class="%s" id="%s" data-box=%s style="%s">%s</div>'
                         % (cls, a["id"], '"1"' if a.get("check") else '""', style, body))

    raw_html = spec.get("raw", "")

    geo_js = "window.__geo=" + json.dumps({"nodes": geo_nodes, "edges": geo_edges},
                                          ensure_ascii=False) + ";"
    seek_setup = spec.get("seek_setup", "")
    seek_body = spec.get("seek", "")
    script = """
  %(geo)s
  window.__duration = %(dur).2f;
  (function () {
    var D = window.__duration, G = window.__geo;
    function ease(x){x=Math.max(0,Math.min(1,x));return 1-Math.pow(1-x,3);}
    function c01(x){return Math.max(0,Math.min(1,x));}
    function pseudo(i){var s=Math.sin(i*12.9898)*43758.5453;return s-Math.floor(s);}
    // 自动收集节点/边元素引用，供运动 JS 用 __N[<id>] / __E[<id>]
    window.__N={};window.__E={};
    document.querySelectorAll("[data-node]").forEach(function(e){__N[e.id]=e;});
    document.querySelectorAll("[data-edge]").forEach(function(e){__E[e.id]=e;});
    %(setup)s
    window.__seek = function (t) {
%(body)s
    };
    window.__seek(0);
  })();
""" % {"geo": geo_js, "dur": duration, "setup": seek_setup, "body": _indent(seek_body, 6)}

    brief = spec.get("brief") or ""
    brief_comment = ("<!-- ANIMATION_BRIEF: %s -->\n" % brief.replace("\n", " ")) if brief else ""

    html = ("<!DOCTYPE html>\n" + brief_comment +
            "<html><head><meta charset='utf-8'><style>" + css + "</style></head><body>\n"
            + '<div class="bg-grid"></div>\n'
            + "\n".join(anno_html) + "\n"
            + "\n".join(node_html) + "\n"
            + svg + "\n"
            + raw_html + "\n"
            + "<script>" + script + "</script>\n"
            + "</body></html>")
    return html


def _colcls(key):
    return {"cyan": "c-cyan", "magenta": "c-magenta", "purple": "c-purple",
            "green": "c-green", "gray": "c-gray"}.get(key, "")


def _indent(s, n):
    pad = " " * n
    return "\n".join((pad + ln if ln.strip() else ln) for ln in s.splitlines())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--shot", type=int, required=True)
    ap.add_argument("--style", default="neon-cyber")
    args = ap.parse_args()

    import scenes  # 同目录
    spec_fn = getattr(scenes, "shot_%02d_spec" % args.shot, None)
    if spec_fn is None:
        raise SystemExit("scenes.py 无 shot_%02d_spec" % args.shot)

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        if pr["mode"] != "webanim":
            raise SystemExit("当前项目是 %s 模式，pv_page 仅用于 webanim" % pr["mode"])
        row = conn.execute("SELECT duration, animation_brief FROM shots WHERE id=?", (args.shot,)).fetchone()
        dur = float(row["duration"] or 8.0)
        brief = row["animation_brief"] or ""
        inj = load_style(args.style)
        spec = spec_fn(pr["width"], pr["height"], dur)
        spec.setdefault("brief", brief)
        html = build_page(spec, pr["width"], pr["height"], dur, inj)
        pages_dir = os.path.join(args.dir, "webpages")
        os.makedirs(pages_dir, exist_ok=True)
        out = os.path.join(pages_dir, "shot_%02d.html" % args.shot)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        conn.execute("UPDATE shots SET web_page_path=? WHERE id=?", (out, args.shot))
        conn.commit()
        print("动画页面已构造: %s（节点 %d 边 %s，几何已校验无重叠/无错位）"
              % (out, len(spec.get("nodes", [])), len(spec.get("edges", []))))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
