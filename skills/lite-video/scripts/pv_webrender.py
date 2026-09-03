#!/usr/bin/env python3
"""阶段 webrender（Web动画模式）：多进程并发逐帧渲染动画页面 → 分镜视频片段。

渲染模型（借鉴 Remotion concurrency + HyperFrames seek 引擎）：
- 每个分镜一个动画页面（含 window.__seek(t) 确定性时间轴契约，先经 pv_weblint 预检）
- N 个 worker 进程，各自启动独立浏览器，并发渲染不同分镜
- 每镜：__seek(i/fps) → 截图 → 字节流直接喂 ffmpeg（image2pipe）→ 混入旁白
- 已存在且时长匹配的片段自动跳过（断点续做）

用法：
  python3 pv_webrender.py --dir <项目目录> [--workers 2] [--shot N] [--force]

依赖：playwright（缺失时自动安装；浏览器缓存通常已存在，否则需
`playwright install chromium`）。帧率/分辨率取 projects 表。
"""
import argparse
import multiprocessing as mp
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import (
    ffmpeg_exe,
    connect_db,
    get_shots,
    get_project,
    ffprobe_duration,
    run_cmd,
    collect_lib_scripts,
)


def _render_one(job):
    """worker：渲染单个分镜。job = dict(base,shot,fps,w,h)。独立进程内运行。"""
    base, shot, fps, w, h = job["base"], job["shot"], job["fps"], job["w"], job["h"]
    from playwright.sync_api import sync_playwright

    dur = float(shot["duration"])
    n = max(int(round(dur * fps)), 1)
    raw = os.path.join(base, "webrender_raw", "shot_%02d.mp4" % shot["id"])
    seg = os.path.join(base, "segments", "shot_%02d.mp4" % shot["id"])

    proc = subprocess.Popen(
        [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "image2pipe", "-framerate", str(fps), "-i", "pipe:0",
         "-t", "%.3f" % dur,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
         "-pix_fmt", "yuv420p", "-r", str(fps), raw],
        stdin=subprocess.PIPE,
    )
    lib_scripts = collect_lib_scripts(shot["web_page_path"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--force-color-profile=srgb"])
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        # 库代码在页面任何脚本之前注入（确保页面脚本执行时库已就绪）
        for _name, code in lib_scripts:
            ctx.add_init_script(code)
        page = ctx.new_page()
        page.goto("file://" + shot["web_page_path"])
        page.wait_for_timeout(150)
        # 异步初始化钩子（如 Mermaid 渲染）：最多等 20s
        page.evaluate(
            "async () => { if (typeof window.__ready === 'function') "
            "await window.__ready(); }"
        )
        page.wait_for_timeout(150)
        for i in range(n):
            page.evaluate("window.__seek(%f)" % (i / fps))
            png = page.screenshot(type="png", animations="disabled")
            proc.stdin.write(png)
        browser.close()
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError("shot_%02d 编码失败（ffmpeg 退出码 %d）" % (shot["id"], rc))

    # 混入旁白（无音轨片段 + 该镜音频）
    run_cmd([
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", raw, "-i", shot["audio_path"],
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", seg,
    ])
    return shot["id"], n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--workers", type=int, default=2, help="并发渲染进程数（默认2，建议≤4）")
    ap.add_argument("--shot", type=int, help="只渲染指定分镜（1 起）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        if pr["mode"] != "webanim":
            raise SystemExit("当前项目是 %s 模式，pv_webrender 仅用于 webanim 模式" % pr["mode"])
        w, h, fps = pr["width"], pr["height"], pr["fps"]
        shots = get_shots(conn)
        if not shots:
            raise SystemExit("shots 表为空")
        os.makedirs(os.path.join(args.dir, "segments"), exist_ok=True)
        os.makedirs(os.path.join(args.dir, "webrender_raw"), exist_ok=True)

        jobs = []
        for fr in shots:
            if args.shot is not None and fr["id"] != args.shot:
                continue
            seg = os.path.join(args.dir, "segments", "shot_%02d.mp4" % fr["id"])
            if not fr.get("web_page_path") or not os.path.exists(fr["web_page_path"]):
                raise SystemExit("shot_%02d 缺少动画页面，请先完成 webpages 阶段" % fr["id"])
            if not fr.get("audio_path") or not fr.get("duration"):
                raise SystemExit("shot_%02d 缺少音频/时长，请先运行 pv_tts.py" % fr["id"])
            if os.path.exists(seg) and not args.force:
                try:
                    if abs(ffprobe_duration(seg) - float(fr["duration"])) < 0.3:
                        print("跳过 shot_%02d（片段已存在且时长匹配）" % fr["id"])
                        continue
                except RuntimeError:
                    pass
            jobs.append({"base": args.dir, "shot": fr, "fps": fps, "w": w, "h": h})

        if not jobs:
            print("全部片段已就绪")
            return

        workers = max(1, min(args.workers, 4, len(jobs)))
        print("渲染 %d 个分镜，并发 %d ..." % (len(jobs), workers))
        if workers == 1:
            results = [_render_one(j) for j in jobs]
        else:
            ctx = mp.get_context("spawn")
            with ctx.Pool(workers) as pool:
                results = pool.map(_render_one, jobs)

        for sid, n in results:
            seg = os.path.join(args.dir, "segments", "shot_%02d.mp4" % sid)
            conn.execute(
                "UPDATE shots SET video_segment_path=?, status='done' WHERE id=?",
                (seg, sid),
            )
            conn.commit()
            print("  ✅ shot_%02d 完成（%d 帧）" % (sid, n))
        print("全部分镜渲染就绪")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
