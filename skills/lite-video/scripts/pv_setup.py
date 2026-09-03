#!/usr/bin/env python3
"""Step 0：环境监察与自动准备（开工前必跑）。

按目标模式检测全部依赖，能自动装的自动装（pip 类），装不了的给出明确指引。

用法：
  python3 pv_setup.py --mode imageflow|webanim|fullvideo|all [--no-auto-install]
                      [--install-browsers]

检查项：
  公共    python≥3.8 / sqlite3 / Pillow / ffmpeg / edge-tts / 中文字体 / TTS 网络连通
  webanim 额外：playwright + Chromium 无头浏览器
  fullvideo 额外：提示需 agent 自带生图/生视频工具（无硬性环境要求）

退出码：0=就绪可开工；1=存在硬性缺失（无法自动补齐）。
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import edge_tts_synthesis_ok  # noqa: E402  真实合成探测（给出可信 TTS 结论）

TTS_HOST = "speech.platform.bing.com"

CJK_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # 仅西文兜底，不算中文可用
]

results = []  # (级别, 项目, 说明)


def note(level, item, msg):
    results.append((level, item, msg))
    mark = {"OK": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[level]
    print("%s %s: %s" % (mark, item, msg))


def pip_install(pkg):
    p = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", pkg],
        capture_output=True, text=True,
    )
    return p.returncode == 0


def check_python():
    ok = sys.version_info >= (3, 8)
    note("OK" if ok else "FAIL", "python",
         "%d.%d（要求 ≥3.8）" % (sys.version_info[:2]))
    return ok


def check_sqlite():
    try:
        import sqlite3

        note("OK", "sqlite3", "内置 %s" % sqlite3.sqlite_version)
        return True
    except ImportError:
        note("FAIL", "sqlite3", "不可用（需要标准库完整的 Python 发行版）")
        return False


def check_pillow(auto):
    try:
        import PIL

        note("OK", "Pillow", PIL.__version__)
        return True
    except ImportError:
        if auto and pip_install("Pillow"):
            note("OK", "Pillow", "已自动安装")
            return True
        note("FAIL", "Pillow", "缺失，自动安装失败（手动: pip install Pillow）")
        return False


def check_ffmpeg(auto):
    if shutil.which("ffmpeg"):
        note("OK", "ffmpeg", shutil.which("ffmpeg"))
        return True
    try:
        import imageio_ffmpeg

        note("OK", "ffmpeg", "imageio-ffmpeg 静态版: %s" % imageio_ffmpeg.get_ffmpeg_exe())
        return True
    except ImportError:
        if auto and pip_install("imageio-ffmpeg"):
            import imageio_ffmpeg

            note("OK", "ffmpeg", "已自动安装 imageio-ffmpeg 静态版")
            return True
        note("FAIL", "ffmpeg", "缺失，自动安装失败（手动: pip install imageio-ffmpeg）")
        return False


def check_edge_tts(auto):
    try:
        import edge_tts  # noqa: F401

        note("OK", "edge-tts", "ok")
        return True
    except ImportError:
        if auto and pip_install("edge-tts"):
            note("OK", "edge-tts", "已自动安装")
            return True
        note("FAIL", "edge-tts", "缺失，自动安装失败（手动: pip install edge-tts）")
        return False


def check_piper(auto):
    """本地离线 TTS（确定性首选）。检测：包 + 音色模型。"""
    try:
        import piper  # noqa: F401
        pkg_ok = True
    except ImportError:
        pkg_ok = auto and pip_install("piper-tts")
        if pkg_ok:
            note("OK", "piper-tts", "已自动安装（python 包）")
    if not pkg_ok:
        note("WARN", "piper-tts", "未安装（本地离线配音首选: pip install piper-tts）")
        return False
    # 模型搜索（与 pv_tts.py 一致）
    import glob

    cands = (
        glob.glob("./piper_model/*.onnx")
        + glob.glob(os.path.expanduser("~/.local/share/piper/*.onnx"))
        + glob.glob("./piper-voices/*.onnx")
    )
    if cands:
        note("OK", "piper模型", sorted(cands)[0])
        return True
    note("WARN", "piper模型",
         "未找到音色模型——中文: python3 -m piper.download_voices zh_CN-huayan-medium "
         "（约60MB；受限网络可用镜像: https://hf-mirror.com/rhasspy/piper-voices/"
         "resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
         " 与同目录 .onnx.json，放入项目目录 piper_model/）")
    return False


def check_dashscope():
    if os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_KEY"):
        note("OK", "dashscope", "DASHSCOPE_API_KEY 已配置（正规云，音质好）")
        return True
    note("WARN", "dashscope", "未配置 DASHSCOPE_API_KEY（正规云备选，音质优于本地）")
    return False


def check_tts_providers(auto):
    """TTS provider 全景扫描（与运行时路由一致，质量优先）：
    正规云/公网可用则用之（韵律自然），Piper 作为确定性兜底。
    至少一个可用才算通过。"""
    print("--- TTS provider 扫描（运行时路由顺序：cmd > dashscope > edge-tts > piper）---")
    piper_ok = check_piper(auto)
    dash_ok = check_dashscope()
    edge_pkg_ok = check_edge_tts(auto)
    edge_net_ok = check_tts_network() if edge_pkg_ok else False
    if dash_ok:
        note("OK", "TTS结论",
             "正规云 dashscope 可用（韵律自然，运行时首选；piper %s作兜底）"
             % ("已装" if piper_ok else "未装，建议安装"))
        return True
    if edge_pkg_ok and edge_net_ok:
        # 用真实合成给出可信结论（fail-open 路由不变，这里只是向用户如实报告）
        sok, smsg = edge_tts_synthesis_ok(attempts=2)
        if sok:
            note("OK" if not piper_ok else "WARN", "TTS结论",
                 "正规云未配；edge-tts 真实合成成功（%s）——逆向灰色通道可能 403 封堵，"
                 "建议配置正规云 key 或装 piper 兜底" % ("piper 已装可兜底" if piper_ok else "piper 未装建议安装"))
        else:
            note("WARN", "TTS结论",
                 "edge-tts 真实合成失败：%s。运行时会自动级联降级；piper %s。"
                 "建议配置正规云 key 或装 piper 兜底"
                 % (smsg, "已装可离线兜底" if piper_ok else "未装，无离线兜底"))
        return True
    if piper_ok:
        note("WARN", "TTS结论",
             "仅本地 Piper 可用（确定性 100%、零成本，但韵律平直、"
             "中英混读效果差）；追求音质请配置正规云 key 或保证 edge-tts 公网可达")
        return True
    note("FAIL", "TTS结论",
         "没有任何可用 TTS provider：piper 缺包/模型、dashscope 缺 key、"
         "edge-tts 不可用或网络被拦。旁白无法合成，必须修复后再开工，"
         "禁止用占位音交付")
    return False


def check_tts_network():
    """TTS 服务连通性：端口探测 + 简化 WebSocket 握手（仅参考）。
    端口可达即认为可尝试（fail-open）：简化 curl 握手不带 edge-tts 完整协议头，
    被拒不代表真实合成不可用，真实合成为准；端口不可达才是硬失败。"""
    try:
        socket.create_connection((TTS_HOST, 443), timeout=6).close()
    except Exception as e:  # noqa: BLE001
        note("WARN", "TTS网络",
             "%s:443 不可达（%s）——edge-tts 无法工作（若装了 piper 可离线兜底）"
             % (TTS_HOST, type(e).__name__))
        return False
    # WebSocket 握手探测（仅参考，不做一票否决）
    probe = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10",
         "-H", "Connection: Upgrade", "-H", "Upgrade: websocket",
         "-H", "Sec-WebSocket-Version: 13",
         "-H", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
         "-H", "User-Agent: Mozilla/5.0 Edg/130.0.0.0",
         "https://%s/consumer/speech/synthesize/readaloud/edge/v1"
         "?TrustedClientToken=6A5AA1D4EAFF4E9FB37E23D68491D6F4" % TTS_HOST],
        capture_output=True, text=True,
    )
    code = probe.stdout.strip()
    if code in ("101", "400"):  # 101=升级成功；400=协议小错但服务在响应
        note("OK", "TTS网络", "%s 可达，握手探测正常（HTTP %s）" % (TTS_HOST, code))
        return True
    note("WARN", "TTS网络",
         "%s 端口可达，但简化握手被拒（HTTP %s）——不做一票否决，"
         "edge-tts 真实合成为准；若真实失败运行时会自动级联降级"
         % (TTS_HOST, code or "超时"))
    return True


def check_cjk_font():
    for cand in CJK_FONT_CANDIDATES[:-1]:
        if os.path.exists(cand):
            note("OK", "中文字体", cand)
            return True
    try:
        p = subprocess.run(["fc-list", ":lang=zh"], capture_output=True, text=True, timeout=10)
        if p.stdout.strip():
            note("OK", "中文字体", "fontconfig 检测到中文字体")
            return True
    except Exception:
        pass
    note("WARN", "中文字体",
         "未检测到中文字体——字幕/占位图中文可能显示异常（建议安装文泉驿或 Noto CJK）")
    return False


def check_playwright(auto, install_browsers):
    try:
        import playwright  # noqa: F401
    except ImportError:
        if not (auto and pip_install("playwright")):
            note("FAIL", "playwright", "缺失，自动安装失败（手动: pip install playwright）")
            return False
        note("OK", "playwright", "已自动安装（python 包）")

    # 检查 Chromium 浏览器是否已安装：尝试快速启动
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--force-color-profile=srgb"])
            browser.close()
        note("OK", "Chromium", "无头浏览器可启动")
        return True
    except Exception:
        if install_browsers:
            print("  → 尝试下载 Chromium（约 150MB，请耐心等待）...")
            p = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True,
            )
            if p.returncode == 0:
                note("OK", "Chromium", "已自动下载安装")
                return True
            note("FAIL", "Chromium",
                 "自动下载失败: %s" % (p.stderr[-200:] or "未知错误"))
            return False
        note("FAIL", "Chromium",
             "无头浏览器未安装——请运行: python3 -m playwright install chromium "
             "（或重新运行本脚本并加 --install-browsers）")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="all",
                    choices=["imageflow", "webanim", "fullvideo", "all"])
    ap.add_argument("--no-auto-install", action="store_true",
                    help="只检测不安装")
    ap.add_argument("--install-browsers", action="store_true",
                    help="允许自动下载 Chromium（webanim 需要，约150MB）")
    args = ap.parse_args()
    auto = not args.no_auto_install

    print("====== lite-video 环境监察（模式: %s）======" % args.mode)
    hard_ok = True

    # 公共依赖（三种模式都需要）
    hard_ok &= check_python()
    hard_ok &= check_sqlite()
    hard_ok &= check_pillow(auto)
    hard_ok &= check_ffmpeg(auto)
    hard_ok &= check_tts_providers(auto)   # 全景扫描，内含 edge-tts 与网络检测
    check_cjk_font()         # WARN 级：影响字幕渲染质量

    if args.mode in ("webanim", "all"):
        print("--- webanim 专属 ---")
        hard_ok &= check_playwright(auto, args.install_browsers)

    if args.mode in ("fullvideo", "all"):
        print("--- fullvideo 专属 ---")
        note("WARN", "生图/生视频工具",
             "fullvideo 依赖 agent 自带的生图/生视频工具（skill/子agent/插件），"
             "无硬性环境要求；开工前请确认当前会话存在可用工具，否则应改用 imageflow")

    print("")
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    if fails:
        print("监察结论: ❌ %d 项硬性缺失，修复后再开工" % len(fails))
        for _, item, msg in fails:
            print("  - %s: %s" % (item, msg))
        sys.exit(1)
    if warns:
        print("监察结论: ⚠️ 就绪，但有 %d 项提醒（见上，涉及则如实告知用户）" % len(warns))
    else:
        print("监察结论: ✅ 环境就绪，可以开工")
    sys.exit(0)


if __name__ == "__main__":
    main()
