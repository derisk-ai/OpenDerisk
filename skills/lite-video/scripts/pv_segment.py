#!/usr/bin/env python3
"""阶段 segments：逐分镜生成视频片段。

对每个分镜：图片 + Ken Burns 运镜（zoompan）+ 对应旁白音轨
→ 输出时长精确等于该段旁白时长的 shot_XX.mp4（h264/yuv420p）。

用法：
  python3 pv_segment.py --dir <项目目录> [--force] [--shot 3]

说明：
- 分辨率/帧率取 projects 表；每镜时长取 shots.duration（TTS 实测值）。
- 运镜模式取 shots.motion（in=推进 / out=拉远），缺省按奇偶交替。
- 每个分镜需要 image_path 与 audio_path 存在；缺失时报错。
- 已存在且时长匹配（误差<0.3s）的片段默认跳过，--force 重做，--shot N 只重做第 N 镜。
"""
import argparse
import os
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


def build_filter(w, h, fps, n_frames, mode):
    """构造运镜滤镜链。先按目标画面比例居中裁切，再按同比例放大到 2 倍分辨率
    （避免运镜时像素化且不变形），最后 zoompan 做缓慢推进/拉远。
    mode: 'in' 缓慢推进 / 'out' 缓慢拉远。末尾 setsar=1 保证方形像素。"""
    if mode == "in":
        z_expr = "min(zoom+%.5f,1.18)" % (0.18 / max(n_frames, 1))
    else:
        z_expr = "if(eq(on,1),1.18,max(zoom-%.5f,1.0))" % (0.18 / max(n_frames, 1))
    return (
        "crop='min(iw,ih*%d/%d)':'min(ih,iw*%d/%d)',"
        "scale=%d:%d,"
        "zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        ":d=%d:s=%dx%d:fps=%d,format=yuv420p,setsar=1"
        % (w, h, h, w, w * 2, h * 2, z_expr, n_frames, w, h, fps)
    )


def gen_segment(shot, w, h, fps, out):
    dur = float(shot["duration"])
    n_frames = max(int(round(dur * fps)), 1)
    vf = build_filter(w, h, fps, n_frames, shot["motion"] or "in")
    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-t", "%.3f" % dur, "-i", shot["image_path"],
        "-i", shot["audio_path"],
        "-vf", vf,
        "-t", "%.3f" % dur,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-shortest", out,
    ]
    run_cmd(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--shot", type=int, help="只重做指定分镜（1 起）")
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        w, h, fps = pr["width"], pr["height"], pr["fps"]
        shots = get_shots(conn)
        if not shots:
            raise SystemExit("shots 表为空")
        seg_dir = os.path.join(args.dir, "segments")
        os.makedirs(seg_dir, exist_ok=True)

        for fr in shots:
            if args.shot is not None and fr["id"] != args.shot:
                continue
            out = os.path.join(seg_dir, "shot_%02d.mp4" % fr["id"])
            if not fr.get("image_path") or not os.path.exists(fr["image_path"]):
                raise SystemExit(
                    "shot_%02d 缺少图片: %s（请先准备图片或用 pv_placeholder.py 兜底）"
                    % (fr["id"], fr.get("image_path") or "<未设置>")
                )
            if not fr.get("audio_path") or not fr.get("duration"):
                raise SystemExit("shot_%02d 缺少音频/时长，请先运行 pv_tts.py" % fr["id"])
            if os.path.exists(out) and not args.force:
                try:
                    if abs(ffprobe_duration(out) - float(fr["duration"])) < 0.3:
                        print("跳过 shot_%02d（片段已存在且时长匹配）" % fr["id"])
                        conn.execute(
                            "UPDATE shots SET video_segment_path=? WHERE id=?",
                            (out, fr["id"]),
                        )
                        conn.commit()
                        continue
                except RuntimeError:
                    pass
            print("生成 shot_%02d (%.2fs, 运镜=%s) ..." % (fr["id"], fr["duration"], fr["motion"]))
            gen_segment(fr, w, h, fps, out)
            conn.execute(
                "UPDATE shots SET video_segment_path=?, status='done' WHERE id=?",
                (out, fr["id"]),
            )
            conn.commit()
            print("  ✅ shot_%02d 完成" % fr["id"])

        print("全部分镜片段就绪")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
