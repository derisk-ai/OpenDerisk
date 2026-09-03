#!/usr/bin/env python3
"""兜底/调试用：为缺少图片的分镜生成"渐变背景 + 标题文字"占位图。

用法：
  python3 pv_placeholder.py --dir <项目目录> [--force]

正式出片时应由 agent 为每个分镜准备真实图片（用生图能力生成后写入 shots.image_path），
本脚本仅用于：1) 流水线调试；2) 个别分镜无素材时的兜底。
分辨率取 projects 表的 width/height。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import connect_db, get_shots, get_project

PALETTES = [
    ((26, 35, 126), (66, 66, 171)),
    ((13, 71, 61), (38, 128, 96)),
    ((74, 20, 90), (140, 62, 122)),
    ((96, 32, 8), (176, 96, 32)),
    ((10, 40, 70), (40, 90, 140)),
]


def find_cjk_font():
    for cand in (
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ):
        if os.path.exists(cand):
            return cand
    return None


def make_image(text, sub, w, h, idx, out):
    from PIL import Image, ImageDraw, ImageFont

    c1, c2 = PALETTES[idx % len(PALETTES)]
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    d = ImageDraw.Draw(img)
    font_path = find_cjk_font()
    try:
        f_big = ImageFont.truetype(font_path, int(h * 0.045)) if font_path else ImageFont.load_default()
        f_sm = ImageFont.truetype(font_path, int(h * 0.022)) if font_path else ImageFont.load_default()
    except Exception:
        f_big = f_sm = ImageFont.load_default()
    title = text[:16]
    bbox = d.textbbox((0, 0), title, font=f_big)
    d.text(((w - bbox[2]) / 2, h * 0.44), title, font=f_big, fill=(255, 255, 255))
    bbox2 = d.textbbox((0, 0), sub, font=f_sm)
    d.text(((w - bbox2[2]) / 2, h * 0.52), sub, font=f_sm, fill=(220, 220, 230))
    img.save(out, quality=92)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        w, h = pr["width"], pr["height"]
        shots = get_shots(conn)
        img_dir = os.path.join(args.dir, "images")
        os.makedirs(img_dir, exist_ok=True)

        for fr in shots:
            out = os.path.join(img_dir, "shot_%02d.jpg" % fr["id"])
            # fullvideo 模式用 first_frame_path；imageflow 模式用 image_path
            img_field = "first_frame_path" if pr.get("mode") == "fullvideo" else "image_path"
            cur = fr.get(img_field)
            if cur and os.path.exists(cur) and not args.force:
                print("跳过 shot_%02d（已有图片）" % fr["id"])
                continue
            label = (fr.get("image_prompt") or "shot %d" % fr["id"])[:14]
            make_image(label, "shot %02d · 占位图" % fr["id"], w, h, fr["id"] - 1, out)
            conn.execute("UPDATE shots SET %s=? WHERE id=?" % img_field, (out, fr["id"]))
            conn.commit()
            print("占位图: %s" % out)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
