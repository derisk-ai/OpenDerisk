#!/usr/bin/env python3
"""阶段 weblint：动画页面确定性预检（借鉴 HyperFrames 的 lint/validate 设计）。

渲染前把不确定性挡在门外，两项检查：
1. 静态扫描：
   - 页面必须定义 window.__seek(t)（确定性时间轴的契约）
   - 拒绝一切墙钟/随机/网络依赖：Math.random、Date.now、new Date、performance.now、
     requestAnimationFrame、setInterval/setTimeout、fetch/XMLHttpRequest、navigator
2. 动态探测（无头浏览器）：
   - 页面可加载、__seek 可调用、__seek(0) 与 __seek(duration) 无异常

用法：
  python3 pv_weblint.py --dir <项目目录> [--static-only]

检查逐镜记录进 verifications（stage=weblint），全过退出码 0，否则 1。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import connect_db, get_shots, get_project
from pv_db import record_verify

FORBIDDEN = [
    ("Math.random", "随机数破坏确定性"),
    ("Date.now", "墙钟时间破坏确定性"),
    ("new Date(", "墙钟时间破坏确定性"),
    ("performance.now", "墙钟时间破坏确定性"),
    ("requestAnimationFrame", "动画必须可被 __seek 驱动，禁止 rAF 墙钟循环"),
    ("setInterval(", "定时器破坏确定性"),
    ("setTimeout(", "定时器破坏确定性"),
    ("fetch(", "运行时网络请求破坏确定性"),
    ("XMLHttpRequest", "运行时网络请求破坏确定性"),
    ("navigator.", "环境依赖破坏确定性"),
]


def static_scan(path):
    """返回 (通过, 证据)。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if not re.search(r"window\.__seek\s*=", text):
        return False, "缺少 window.__seek 定义（确定性时间轴契约）"
    hits = []
    for pat, reason in FORBIDDEN:
        if pat in text:
            hits.append("%s(%s)" % (pat, reason))
    if hits:
        return False, "违禁调用: " + "; ".join(hits)
    return True, "__seek 契约满足，无违禁调用"


def dynamic_probe(paths_with_dur):
    """动态探测：逐个加载页面验证 __seek 可执行。返回 {path: (ok, msg)}。
    按页面 pv-libs 声明注入内置库，并等待 __ready 异步初始化（与渲染器同逻辑）。"""
    from playwright.sync_api import sync_playwright

    from pv_common import collect_lib_scripts

    results = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--force-color-profile=srgb"])
        for path, dur in paths_with_dur:
            ctx = browser.new_context(viewport={"width": 100, "height": 100})
            for _name, code in collect_lib_scripts(path):
                ctx.add_init_script(code)
            page = ctx.new_page()
            try:
                page.goto("file://" + path)
                page.wait_for_timeout(100)
                page.evaluate(
                    "async () => { if (typeof window.__ready === 'function') "
                    "await window.__ready(); }"
                )
                page.wait_for_timeout(100)
                ok = page.evaluate(
                    "(d) => { try {"
                    " if (typeof window.__seek !== 'function') return 'NO_SEEK';"
                    " window.__seek(0); window.__seek(d); return 'OK';"
                    " } catch(e) { return 'ERR:' + e.message; } }",
                    float(dur),
                )
                if ok == "OK":
                    results[path] = (True, "动态探测通过（__seek(0)/__seek(%s) 无异常）" % dur)
                else:
                    results[path] = (False, "动态探测失败: %s" % ok)
            except Exception as e:  # noqa: BLE001
                results[path] = (False, "页面加载失败: %s" % str(e)[:120])
            finally:
                ctx.close()
        browser.close()
    return results


# 矩形几何检查：真实视口多点采样，断言可见节点无重叠/不出画布/文字不溢出，
# 可见连线端点落在目标节点矩形内。这是「不出现错位遮挡」的机械兜底门。
# 与 dynamic_probe 同构：注入内置库、等 __ready、真实视口；对无 data-node 的
# 模板页/旧页，无可检元素即 trivially PASS，不误伤。
_LAYOUT_JS = r"""
(tt, GW, GH) => {
  try {
    window.__seek(tt);
    var nodes = [];
    document.querySelectorAll('[data-node]').forEach(function(el){
      var op = parseFloat(getComputedStyle(el).opacity) || 0;
      if (op < 0.3) return;
      var r = el.getBoundingClientRect();
      nodes.push({id: el.id, x: r.left, y: r.top, w: r.width, h: r.height,
                  sw: el.scrollWidth, cw: el.clientWidth});
    });
    var overlaps = [];
    for (var i = 0; i < nodes.length; i++)
      for (var j = i + 1; j < nodes.length; j++) {
        var a = nodes[i], b = nodes[j];
        var ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        var oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        if (ox > 6 && oy > 6) overlaps.push(a.id + '<>' + b.id + ' ' + ox.toFixed(0) + 'x' + oy.toFixed(0));
      }
    var oob = [], over = [];
    nodes.forEach(function(n) {
      if (n.x < -2 || n.y < -2 || n.x + n.w > GW + 2 || n.y + n.h > GH + 2) oob.push(n.id);
      if (n.sw > n.cw + 24) over.push(n.id + '(' + (n.sw - n.cw).toFixed(0) + 'px)');
    });
    var mis = [];
    document.querySelectorAll('[data-edge]').forEach(function(el) {
      var op = parseFloat(getComputedStyle(el).opacity) || 0;
      if (op < 0.3) return;
      var fr = el.getAttribute('data-from'), to = el.getAttribute('data-to');
      var G = window.__geo && window.__geo.nodes ? window.__geo.nodes : {};
      var a = G[fr], b = G[to];
      var x1 = +el.getAttribute('x1'), y1 = +el.getAttribute('y1');
      var x2 = +el.getAttribute('x2'), y2 = +el.getAttribute('y2');
      function onRect(px, py, r) {
        return px >= r.x - 2 && px <= r.x + r.w + 2 && py >= r.y - 2 && py <= r.y + r.h + 2;
      }
      if (a && !onRect(x1, y1, a)) mis.push(el.id + '端点1(' + x1 + ',' + y1 + ')');
      if (b && !onRect(x2, y2, b)) mis.push(el.id + '端点2(' + x2 + ',' + y2 + ')');
    });
    return {overlaps: overlaps, oob: oob, over: over, mis: mis};
  } catch (e) { return {err: e.message}; }
}
"""


def layout_probe(paths_with_dur_dims):
    """真实视口多点采样几何检查。返回 {path: (ok, msg)}。

    与 dynamic_probe 同构（注入内置库、等 __ready），断言（仅对可见元素 opacity≥0.3，
    规避入场/退场瞬时与不可见元素）：节点无重叠、不出画布、文字不溢出盒子、可见
    连线端点落在目标节点矩形内。"""
    from playwright.sync_api import sync_playwright

    from pv_common import collect_lib_scripts

    results = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--force-color-profile=srgb"])
        for path, dur, W, H in paths_with_dur_dims:
            issues = []
            ctx = browser.new_context(viewport={"width": int(W), "height": int(H)})
            for _name, code in collect_lib_scripts(path):
                ctx.add_init_script(code)
            page = ctx.new_page()
            try:
                page.goto("file://" + path)
                page.wait_for_timeout(100)
                page.evaluate(
                    "async () => { if (typeof window.__ready === 'function') "
                    "await window.__ready(); }"
                )
                page.wait_for_timeout(100)
                for frac in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
                    t = dur * frac
                    r = page.evaluate(_LAYOUT_JS, (t, int(W), int(H)))
                    if isinstance(r, dict) and r.get("err"):
                        issues.append("t=%.1f ERR:%s" % (t, r["err"][:60]))
                        break
                    if r["overlaps"]:
                        issues.append("t=%.1f 重叠:%s" % (t, ",".join(r["overlaps"][:3])))
                    if r["oob"]:
                        issues.append("t=%.1f 出画布:%s" % (t, ",".join(r["oob"][:3])))
                    if r["over"]:
                        issues.append("t=%.1f 溢出:%s" % (t, ",".join(r["over"][:3])))
                    if r["mis"]:
                        issues.append("t=%.1f 错位:%s" % (t, ",".join(r["mis"][:3])))
            except Exception as e:  # noqa: BLE001
                issues.append("加载失败:%s" % str(e)[:80])
            finally:
                ctx.close()
            if issues:
                results[path] = (False, "几何检查发现: " + "; ".join(issues[:4]))
            else:
                results[path] = (True, "几何检查通过（无重叠/无错位/无溢出/不出画布）")
        browser.close()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--static-only", action="store_true",
                    help="只做静态扫描，跳过无头浏览器动态探测")
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        if pr["mode"] != "webanim":
            raise SystemExit("当前项目是 %s 模式，pv_weblint 仅用于 webanim 模式" % pr["mode"])
        shots = get_shots(conn)
        if not shots:
            raise SystemExit("shots 表为空")

        all_ok = True
        dyn_paths = []
        for fr in shots:
            path = fr.get("web_page_path")
            if not path or not os.path.exists(path):
                all_ok = False
                record_verify(conn, "weblint", "shot_%02d_page_exists" % fr["id"], False,
                              "动画页面不存在: %s" % path)
                continue
            ok, msg = static_scan(path)
            all_ok &= ok
            record_verify(conn, "weblint", "shot_%02d_static" % fr["id"], ok, msg)
            if ok:
                dyn_paths.append((path, fr.get("duration") or 5.0))

        if dyn_paths and not args.static_only:
            results = dynamic_probe(dyn_paths)
            for path, (ok, msg) in results.items():
                sid = next(fr["id"] for fr in shots if fr.get("web_page_path") == path)
                all_ok &= ok
                record_verify(conn, "weblint", "shot_%02d_dynamic" % sid, ok, msg)
            # 矩形几何检查（真实视口多点采样：无重叠/无错位/无溢出/不出画布）
            lay = layout_probe([(p, d, pr["width"], pr["height"]) for (p, d) in dyn_paths])
            for path, (ok, msg) in lay.items():
                sid = next(fr["id"] for fr in shots if fr.get("web_page_path") == path)
                all_ok &= ok
                record_verify(conn, "weblint", "shot_%02d_layout" % sid, ok, msg)
        elif dyn_paths and args.static_only:
            print("（--static-only：跳过动态探测与几何检查）")

        print("")
        print("动画预检: %s" % ("PASS" if all_ok else "FAIL"))
        sys.exit(0 if all_ok else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
