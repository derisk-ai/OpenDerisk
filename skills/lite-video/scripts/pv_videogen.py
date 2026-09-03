#!/usr/bin/env python3
"""阶段 videogen（全视频模式）：按首帧图（可选尾帧图）+ 目标时长调用图生视频能力，
为每个分镜生成真实动态视频片段，时长精确对齐该镜旁白。

Provider 可插拔：通过 --provider-cmd 传入命令模板，占位符：
  {image}   首帧图路径      {image2}  尾帧图路径（无则为空串）
  {prompt}  该镜画面描述    {duration} 目标时长（秒）
  {width}/{height} 目标分辨率          {out} 输出 mp4 路径

示例（可灵官方 CLI，仅示意格式）：
  --provider-cmd "kling i2v --image {image} --prompt {prompt} --duration {duration} --out {out}"

无可用 provider 时：
- 测试/调试可用 --simulate（用首帧+运镜模拟动态，明确非真实生成）
- 正式场景应退回让用户提供 provider，或改用 imageflow 图文模式

用法：
  python3 pv_videogen.py --dir <项目目录> [--provider-cmd "..."] [--simulate]
                         [--shot 3] [--force]

时长对齐策略：provider 输出时长与目标差 >0.5s 时，用 setpts 变速缩放（保音画同步由
无音轨片段后续混音保证）；差 <=0.5s 直接 -t 截断/补齐。已存在且时长匹配的片段跳过。
"""
import argparse
import os
import shlex
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
)
from pv_segment import build_filter


def simulate_clip(shot, w, h, fps, out):
    """测试用：首帧图 + 运镜生成伪动态片段（非真实图生视频）。"""
    dur = float(shot["duration"])
    n_frames = max(int(round(dur * fps)), 1)
    vf = build_filter(w, h, fps, n_frames, shot.get("motion") or "in")
    run_cmd([
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-t", "%.3f" % dur, "-i", shot["first_frame_path"],
        "-vf", vf, "-t", "%.3f" % dur,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", out,
    ])


def run_provider(cmd_tpl, shot, w, h, out):
    """执行 provider 命令模板。所有注入值经 shlex.quote 转义，防止命令注入。"""
    cmd = cmd_tpl.format(
        image=shlex.quote(shot["first_frame_path"]),
        image2=shlex.quote(shot.get("last_frame_path") or ""),
        prompt=shlex.quote(shot.get("image_prompt") or ""),
        duration="%.1f" % float(shot["duration"]),
        width=w, height=h, out=shlex.quote(out),
    )
    print("  provider: %s" % cmd)
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(
            "provider 执行失败（退出码 %d）\nstdout: %s\nstderr: %s"
            % (p.returncode, p.stdout[-500:], p.stderr[-800:])
        )


def align_duration(path, target, w, h, fps):
    """把片段时长对齐到 target：差异大用 setpts 变速，差异小直接重截。"""
    cur = ffprobe_duration(path)
    if abs(cur - target) <= 0.5:
        if cur < target:
            # 补齐：末尾定格（tpad clone）
            tmp = path + ".pad.mp4"
            run_cmd([
                ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", path,
                "-vf", "tpad=stop_mode=clone:stop_duration=%.3f" % (target - cur),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-an", tmp,
            ])
            os.replace(tmp, path)
        elif cur > target:
            tmp = path + ".trim.mp4"
            run_cmd([
                ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-t", "%.3f" % target, "-i", path,
                "-c", "copy", "-an", tmp,
            ])
            os.replace(tmp, path)
        return
    # 变速缩放：setpts=PTS*(target/cur)
    ratio = target / cur
    tmp = path + ".speed.mp4"
    run_cmd([
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", path,
        "-vf", "setpts=%.4f*PTS,scale=%d:%d,format=yuv420p,setsar=1" % (ratio, w, h),
        "-t", "%.3f" % target,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", tmp,
    ])
    os.replace(tmp, path)


def mix_narration(seg_path, audio_path, out, fps):
    """给无音轨的视频片段混入该镜旁白。"""
    run_cmd([
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", seg_path, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", out,
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--provider-cmd", help="图生视频命令模板（占位符见文件头）")
    ap.add_argument("--simulate", action="store_true",
                    help="测试模式：用首帧+运镜模拟动态片段（非真实生成，仅供流水线调试）")
    ap.add_argument("--shot", type=int, help="只处理指定分镜（1 起）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.provider_cmd and not args.simulate:
        raise SystemExit(
            "需要 --provider-cmd（图生视频能力）或 --simulate（仅测试）。\n"
            "若当前环境没有图生视频能力，建议改用 imageflow 图文模式。"
        )

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        if pr["mode"] != "fullvideo":
            raise SystemExit("当前项目是 %s 模式，pv_videogen 仅用于 fullvideo 模式" % pr["mode"])
        w, h, fps = pr["width"], pr["height"], pr["fps"]
        shots = get_shots(conn)
        if not shots:
            raise SystemExit("shots 表为空")
        seg_dir = os.path.join(args.dir, "segments")
        raw_dir = os.path.join(args.dir, "raw_videogen")
        os.makedirs(seg_dir, exist_ok=True)
        os.makedirs(raw_dir, exist_ok=True)

        for fr in shots:
            if args.shot is not None and fr["id"] != args.shot:
                continue
            out = os.path.join(seg_dir, "shot_%02d.mp4" % fr["id"])
            if not fr.get("first_frame_path") or not os.path.exists(fr["first_frame_path"]):
                raise SystemExit("shot_%02d 缺少首帧图，请先完成 keyframes 阶段" % fr["id"])
            if not fr.get("audio_path") or not fr.get("duration"):
                raise SystemExit("shot_%02d 缺少音频/时长，请先运行 pv_tts.py" % fr["id"])
            if os.path.exists(out) and not args.force:
                try:
                    if abs(ffprobe_duration(out) - float(fr["duration"])) < 0.3:
                        print("跳过 shot_%02d（片段已存在且时长匹配）" % fr["id"])
                        continue
                except RuntimeError:
                    pass

            tag = "simulate" if args.simulate else "provider"
            print("生成 shot_%02d (%.2fs, %s) ..." % (fr["id"], fr["duration"], tag))
            raw = os.path.join(raw_dir, "shot_%02d.mp4" % fr["id"])
            if args.simulate:
                simulate_clip(fr, w, h, fps, raw)
            else:
                run_provider(args.provider_cmd, fr, w, h, raw)
            align_duration(raw, float(fr["duration"]), w, h, fps)
            mix_narration(raw, fr["audio_path"], out, fps)
            conn.execute(
                "UPDATE shots SET video_segment_path=?, status='done' WHERE id=?",
                (out, fr["id"]),
            )
            conn.commit()
            print("  ✅ shot_%02d 完成" % fr["id"])

        print("全部分镜视频片段就绪")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
