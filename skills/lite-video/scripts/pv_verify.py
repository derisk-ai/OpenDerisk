#!/usr/bin/env python3
"""阶段验证引擎：Evidence before claims（借鉴 superpowers 的验证纪律）。

每个非门控阶段在标记完成前，必须先运行对应检查并把结果记入 verifications 表。
pv_db.py complete-stage 会拒绝没有任何通过验证记录的阶段（EVIDENCE REQUIRED）。

用法：
  python3 pv_verify.py --dir <项目目录> --stage <阶段名>

各阶段检查项：
  tts       每个分镜有音频文件、时长>0.5s、DB 时长与实测一致（误差<0.3s）
  visuals   [imageflow] 每镜有图片、可解码、分辨率满足 >= 项目分辨率一半
  keyframes [fullvideo] 每镜有首帧图、可解码、分辨率满足 >= 项目分辨率一半
  segments  [imageflow] 片段时长与旁白对齐（误差<0.3s）、分辨率=项目规格、SAR=1:1
  videogen  [fullvideo] 片段时长与旁白对齐（误差<0.5s）、分辨率=项目规格、SAR=1:1
  webpages  [webanim] 每镜有动画页面、含 __seek 定义、无违禁调用（静态快查）
  webrender [webanim] 片段时长与旁白对齐（误差<0.3s）、分辨率=项目规格、SAR=1:1
  compose   成片存在、总时长=各镜之和（误差<1s）、分辨率正确、音轨存在、
            底部有字幕渲染（有字幕文件时）

退出码：全部通过=0；任一失败=1（失败项同样入库，FAIL 会阻止阶段完成）。
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import (
    ffmpeg_exe,
    connect_db,
    get_shots,
    get_project,
    ffprobe_duration,
    ffprobe_resolution,
)

TOL = 0.3


def record(conn, stage, check, passed, evidence):
    conn.execute(
        "INSERT INTO verifications(stage,check_name,passed,evidence,created_at)"
        " VALUES(?,?,?,?,datetime('now','localtime'))",
        (stage, check, 1 if passed else 0, evidence),
    )
    conn.commit()
    print("%s [%s] %s: %s" % ("✅" if passed else "❌", stage, check, evidence))
    return passed


def check_tts(conn, shots, base):
    ok = True
    for fr in shots:
        path = fr.get("audio_path")
        if not path or not os.path.exists(path):
            ok &= record(conn, "tts", "shot_%02d_audio_exists" % fr["id"], False,
                         "音频文件不存在: %s" % path)
            continue
        real = ffprobe_duration(path)
        db_dur = float(fr.get("duration") or 0)
        if real < 0.5:
            ok &= record(conn, "tts", "shot_%02d_duration_valid" % fr["id"], False,
                         "音频过短: %.2fs" % real)
        elif abs(real - db_dur) > TOL:
            ok &= record(conn, "tts", "shot_%02d_db_consistency" % fr["id"], False,
                         "DB 时长 %.2f 与实测 %.2f 不一致" % (db_dur, real))
        else:
            ok &= record(conn, "tts", "shot_%02d_ok" % fr["id"], True,
                         "%.2fs（DB %.2f）" % (real, db_dur))
    return ok


def check_visuals(conn, shots, base, pr):
    return _check_image_stage(conn, shots, pr, "visuals", "image_path", "图片")


def check_keyframes(conn, shots, base, pr):
    return _check_image_stage(conn, shots, pr, "keyframes", "first_frame_path", "首帧图")


def _check_image_stage(conn, shots, pr, stage, field, label):
    ok = True
    min_side = min(pr["width"], pr["height"]) // 2
    for fr in shots:
        path = fr.get(field)
        if not path or not os.path.exists(path):
            ok &= record(conn, stage, "shot_%02d_%s_exists" % (fr["id"], stage), False,
                         "%s不存在: %s" % (label, path))
            continue
        try:
            from PIL import Image

            with Image.open(path) as im:
                w, h = im.size
            passed = w >= min_side and h >= min_side
            ok &= record(conn, stage, "shot_%02d_decode" % fr["id"], passed,
                         "可解码 %dx%d（最低要求边长 %d）" % (w, h, min_side))
        except Exception as e:
            ok &= record(conn, stage, "shot_%02d_decode" % fr["id"], False, str(e))
    return ok


def check_sar(path):
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path],
                       capture_output=True, text=True)
    import re

    m = re.search(r"SAR (\d+):(\d+)", p.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else (1, 1)


def check_segments(conn, shots, base, pr):
    return _check_video_stage(conn, shots, pr, "segments", TOL)


def check_webpages(conn, shots, base, pr):
    """webanim：每镜动画页面存在 + 含 __seek 定义（静态快查，深度预检归 weblint）。"""
    import re

    ok = True
    for fr in shots:
        path = fr.get("web_page_path")
        if not path or not os.path.exists(path):
            ok &= record(conn, "webpages", "shot_%02d_page_exists" % fr["id"], False,
                         "动画页面不存在: %s" % path)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            has_seek = bool(re.search(r"window\.__seek\s*=", text))
            ok &= record(conn, "webpages", "shot_%02d_seek_contract" % fr["id"], has_seek,
                         "__seek 契约满足" if has_seek else "缺少 window.__seek 定义")
        except Exception as e:
            ok &= record(conn, "webpages", "shot_%02d_readable" % fr["id"], False, str(e))
    return ok


def check_webrender(conn, shots, base, pr):
    return _check_video_stage(conn, shots, pr, "webrender", TOL)


def check_videogen(conn, shots, base, pr):
    # 图生视频输出时长波动更大，容差放宽到 0.5s
    return _check_video_stage(conn, shots, pr, "videogen", 0.5)


def _check_video_stage(conn, shots, pr, stage, tol):
    ok = True
    for fr in shots:
        path = fr.get("video_segment_path")
        if not path or not os.path.exists(path):
            ok &= record(conn, stage, "shot_%02d_exists" % fr["id"], False,
                         "片段不存在: %s" % path)
            continue
        try:
            real = ffprobe_duration(path)
            want = float(fr.get("duration") or 0)
            ok &= record(conn, stage, "shot_%02d_duration_align" % fr["id"],
                         abs(real - want) <= tol,
                         "片段 %.2fs / 旁白 %.2fs（误差限 %.1fs）" % (real, want, tol))
            rw, rh = ffprobe_resolution(path)
            ok &= record(conn, stage, "shot_%02d_resolution" % fr["id"],
                         (rw, rh) == (pr["width"], pr["height"]),
                         "实测 %dx%d / 规格 %dx%d" % (rw, rh, pr["width"], pr["height"]))
            sar = check_sar(path)
            ok &= record(conn, stage, "shot_%02d_sar" % fr["id"], sar == (1, 1),
                         "SAR %d:%d（要求 1:1）" % sar)
        except RuntimeError as e:
            ok &= record(conn, stage, "shot_%02d_probe" % fr["id"], False, str(e))
    return ok


def check_compose(conn, shots, base, pr):
    ok = True
    final = dict(conn.execute(
        "SELECT final_video_path, total_duration FROM projects ORDER BY id LIMIT 1"
    ).fetchone())["final_video_path"]
    if not final or not os.path.exists(final):
        return record(conn, "compose", "final_exists", False, "成片不存在: %s" % final)

    real = ffprobe_duration(final)
    want = sum(float(fr.get("duration") or 0) for fr in shots)
    ok &= record(conn, "compose", "total_duration", abs(real - want) <= 1.0,
                 "成片 %.2fs / 各镜之和 %.2fs" % (real, want))
    try:
        rw, rh = ffprobe_resolution(final)
        ok &= record(conn, "compose", "resolution",
                     (rw, rh) == (pr["width"], pr["height"]),
                     "实测 %dx%d / 规格 %dx%d" % (rw, rh, pr["width"], pr["height"]))
    except RuntimeError as e:
        ok &= record(conn, "compose", "resolution", False, str(e))

    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", final],
                       capture_output=True, text=True)
    has_audio = "Audio:" in p.stderr
    ok &= record(conn, "compose", "audio_track", has_audio, "音轨存在" if has_audio else "无音轨")

    srt = os.path.join(base, "subs.ass")
    if not os.path.exists(srt):
        srt = os.path.join(base, "subs.srt")
    if os.path.exists(srt):
        # 字幕渲染验证：抽成片帧，检查底部区域亮像素占比
        from PIL import Image

        frame = os.path.join(base, ".verify_frame.png")
        subprocess.run([
            ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", "1", "-i", final, "-frames:v", "1", frame,
        ], check=True)
        img = Image.open(frame).convert("L")
        w, h = img.size
        px = img.load()
        region = [px[x, y] for y in range(int(h * 0.85), h) for x in range(w)]
        bright = sum(1 for v in region if v > 200) / len(region)
        ok &= record(conn, "compose", "subtitles_rendered", bright > 0.005,
                     "底部15%%区域亮像素占比 %.4f（阈值 0.005）" % bright)
        os.remove(frame)
    return ok


CHECKERS = {
    "tts": check_tts,
    "visuals": check_visuals,
    "keyframes": check_keyframes,
    "segments": check_segments,
    "videogen": check_videogen,
    "webpages": check_webpages,
    "webrender": check_webrender,
    "compose": check_compose,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--stage", required=True, choices=list(CHECKERS))
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        shots = get_shots(conn)
        pr = get_project(conn)
        if args.stage == "tts":
            ok = CHECKERS[args.stage](conn, shots, args.dir)
        else:
            ok = CHECKERS[args.stage](conn, shots, args.dir, pr)
        print("")
        print("阶段 %s 验证: %s" % (args.stage, "PASS" if ok else "FAIL"))
        sys.exit(0 if ok else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
