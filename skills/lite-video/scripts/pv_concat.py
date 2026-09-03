#!/usr/bin/env python3
"""阶段 compose：视频合成。顺序拼接所有分镜片段 → 可选烧录字幕 → 可选叠加 BGM → 成片。

用法：
  python3 pv_concat.py --dir <项目目录> [--bgm bgm.mp3] [--bgm-volume 0.15]
                       [--subs subs.ass] [--output final.mp4]

字幕查找顺序：--subs 指定 > 项目目录 subs.ass（推荐，pv_subs.py 生成，自适应分辨率）
> subs.srt（旧版兜底）。BGM 自动循环到正片长度并渐出收尾。
成片路径与总时长写回 projects 表。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import (
    ffmpeg_exe,
    libass_ffmpeg,
    connect_db,
    get_shots,
    ffprobe_duration,
    run_cmd,
    escape_filter_path,
    find_cjk_font_family,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--bgm", help="背景音乐文件路径")
    ap.add_argument("--bgm-volume", type=float, default=0.15, help="BGM 音量(0~1)")
    ap.add_argument("--subs", help="字幕文件（推荐 .ass，兼容 .srt）")
    ap.add_argument("--output", help="输出路径，默认 <项目目录>/final.mp4")
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        shots = get_shots(conn)
        segs = [fr["video_segment_path"] for fr in shots if fr.get("video_segment_path")]
        if not segs:
            raise SystemExit("没有可拼接的分镜片段，请先运行 pv_segment.py")

        base = args.dir
        final = args.output or os.path.join(base, "final.mp4")
        os.makedirs(os.path.dirname(os.path.abspath(final)), exist_ok=True)

        # 1) concat demuxer 拼接
        list_file = os.path.join(base, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in segs:
                f.write("file '%s'\n" % p.replace("'", "'\\''"))
        concat_mp4 = os.path.join(base, "concat_raw.mp4")
        run_cmd([
            ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
            concat_mp4,
        ])

        # 2) 可选烧录字幕（自适应分辨率的 ASS，由 pv_subs.py 生成）
        # 优先级：--subs 指定路径 > 项目目录默认 subs.ass > subs.srt（旧版兜底）
        subs = args.subs if args.subs else os.path.join(base, "subs.ass")
        if not os.path.exists(subs):
            fallback = os.path.join(base, "subs.srt")
            if os.path.exists(fallback):
                subs = fallback
        if os.path.exists(subs):
            subbed = os.path.join(base, "with_subs.mp4")
            fs = escape_filter_path(subs)
            # 字幕烧录依赖 libass。系统 ffmpeg 可能是精简构建（如部分 Homebrew 版未带
            # libass），libass_ffmpeg() 自动回落到 static-ffmpeg 等带 libass 的 ffmpeg，
            # 或在确实没有时报出可操作的错误，避免晦涩的 filter 解析错误。
            burn_ff = libass_ffmpeg()
            if subs.endswith(".ass"):
                vf = "ass='%s'" % fs
                print("烧录 ASS 字幕: %s（ffmpeg=%s）" % (subs, burn_ff))
            else:
                font = find_cjk_font_family()
                force_style = (
                    "FontName=%s,FontSize=18,PrimaryColour=&HFFFFFF&,"
                    "OutlineColour=&H80000000&,BorderStyle=3,MarginV=36" % font
                )
                vf = "subtitles='%s':force_style='%s'" % (fs, force_style)
                print("烧录 SRT 字幕（旧版兜底）: %s（ffmpeg=%s）" % (subs, burn_ff))
            run_cmd([
                burn_ff, "-y", "-hide_banner", "-loglevel", "error",
                "-i", concat_mp4,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
                "-c:a", "copy", subbed,
            ])
            concat_mp4 = subbed

        # 3) 可选叠加 BGM（循环 + 音量 + 尾部 1.5s 渐出）
        if args.bgm and os.path.exists(args.bgm):
            total = ffprobe_duration(concat_mp4)
            fade_st = max(total - 1.5, 0.0)
            tmp_out = final if not os.path.exists(final) else final + ".bgm.tmp.mp4"
            run_cmd([
                ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", concat_mp4, "-stream_loop", "-1", "-i", args.bgm,
                "-filter_complex",
                "[1:a]volume=%.3f,afade=t=out:st=%.2f:d=1.5[bgm];"
                "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
                % (args.bgm_volume, fade_st),
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", tmp_out,
            ])
            if tmp_out != final:
                os.replace(tmp_out, final)
        else:
            if os.path.abspath(concat_mp4) != os.path.abspath(final):
                os.replace(concat_mp4, final)

        total_dur = round(ffprobe_duration(final), 2)
        conn.execute(
            "UPDATE projects SET final_video_path=?, total_duration=?, updated_at=datetime('now')"
            " WHERE id=1",
            (os.path.abspath(final), total_dur),
        )
        conn.commit()
        print("成片完成: %s (总时长 %.2fs, %d 个分镜)" % (final, total_dur, len(segs)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
