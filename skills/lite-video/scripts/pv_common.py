#!/usr/bin/env python3
"""lite-video 公共模块：依赖自检、ffmpeg 定位、时长测量、SQLite 连接。"""
import os
import re
import subprocess
import sys


def run_cmd(cmd):
    """运行命令，失败时抛出带 stderr 的异常。"""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "命令失败: %s\nstderr: %s" % (" ".join(str(c) for c in cmd[:4]), p.stderr[-2000:])
        )
    return p


def ensure_deps():
    """确保 edge-tts 与 imageio-ffmpeg 可用，缺失则自动 pip 安装。"""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "edge-tts"], check=True
        )
    try:
        import imageio_ffmpeg  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "imageio-ffmpeg"], check=True
        )


def ffmpeg_exe():
    """返回可用的 ffmpeg 可执行文件路径（优先系统，其次 imageio-ffmpeg 静态版）。"""
    import shutil

    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    ensure_deps()
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def ffprobe_duration(path):
    """用 ffmpeg -i 解析媒体时长（秒）。"""
    p = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    if not m:
        raise RuntimeError("无法解析时长: %s" % path)
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def ffprobe_resolution(path):
    """用 ffmpeg -i 解析视频分辨率，返回 (width, height)。
    兼容有无 SAR 注释的输出（image2pipe 编码的片段不带 SAR 元数据）。"""
    p = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True
    )
    m = re.search(r"Stream #0:0.*?(\d{2,5})x(\d{2,5})", p.stderr)
    if not m:
        raise RuntimeError("无法解析分辨率: %s" % path)
    return int(m.group(1)), int(m.group(2))


def connect_db(project_dir):
    """连接项目生产库（复用 pv_db 的连接逻辑）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pv_db

    return pv_db.connect(project_dir)


def get_project(conn):
    d = dict(conn.execute("SELECT * FROM projects ORDER BY id LIMIT 1").fetchone())
    # 兼容升级前旧库（无 mode/新列）：按 imageflow 处理
    d.setdefault("mode", "imageflow")
    return d


def get_shots(conn):
    rows = conn.execute("SELECT * FROM shots ORDER BY id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.setdefault("first_frame_path", None)
        d.setdefault("last_frame_path", None)
        d.setdefault("web_page_path", None)
        d.setdefault("tts_text", None)
        d.setdefault("animation_brief", None)
        out.append(d)
    return out


def escape_filter_path(path):
    """转义用于 ffmpeg filter 图的路径（冒号/逗号/反斜杠）。"""
    return path.replace("\\", "\\\\").replace(":", "\\:").replace(",", "\\,")


def libs_dir():
    """内置动画库目录（assets/libs/）。"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "libs")


def parse_pv_libs(html_path):
    """解析页面 <meta name="pv-libs" content="gsap,d3,..."> 声明，
    返回合法库名列表（白名单校验，防注入）。"""
    import re

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            head = f.read(20000)
    except Exception:
        return []
    m = re.search(r'<meta\s+name="pv-libs"\s+content="([^"]*)"', head)
    if not m:
        return []
    out = []
    for name in [s.strip() for s in m.group(1).split(",") if s.strip()]:
        if re.fullmatch(r"[a-zA-Z0-9_\-]+", name):
            out.append(name)
    return out


def collect_lib_scripts(html_path):
    """按页面 pv-libs 声明收集内置库源码，返回 [(name, code), ...]。
    缺失的库打印警告并跳过（渲染环境无外网，仅用内置库）。"""
    names = parse_pv_libs(html_path)
    if not names:
        return []
    d = libs_dir()
    try:
        avail = {x[:-7] for x in os.listdir(d) if x.endswith(".min.js")}
    except OSError:
        avail = set()
    out = []
    for name in names:
        p = os.path.join(d, name + ".min.js")
        if name in avail and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                out.append((name, f.read()))
        else:
            print("  ⚠️ 库 %s 不在内置清单（忽略），内置: %s"
                  % (name, ", ".join(sorted(avail)) or "(空)"))
    return out


def find_cjk_font_family():
    """找一个支持中文的字体族名（libass 默认字体不含 CJK 字形，
    必须显式指定，否则中文字幕渲染为空白）。"""
    try:
        p = subprocess.run(
            ["fc-list", ":lang=zh", "family"], capture_output=True, text=True, timeout=10
        )
        for line in p.stdout.splitlines():
            fam = line.split(",")[0].strip()
            if fam:
                return fam
    except Exception:
        pass
    return "WenQuanYi Micro Hei"


def patch_edge_tts_ssl():
    """edge-tts 默认用 certifi 证书包；企业代理（自签名 CA 注入系统证书链）
    环境会校验失败。改用系统默认证书链。探测与正式合成都必须调用，否则探测会
    与真实合成得出不同结论（探测说不可用、合成却成功）。"""
    try:
        import ssl

        import edge_tts.communicate as _c

        if hasattr(_c, "_SSL_CTX"):
            _c._SSL_CTX = ssl.create_default_context()
    except Exception:
        pass


def edge_tts_synthesis_ok(voice="zh-CN-YunxiNeural", attempts=2):
    """用真实合成探测 edge-tts 可用性，返回 (ok, msg)。

    早期版本用一次 curl WebSocket 握手探测（只接受 HTTP 101/400），但 edge-tts
    真实通道与裸 curl 握手路径不同，常在公网返回 404，**误判为不可用**——而
    实际合成却能成功。改为真实合成一小段语音：任一次产出非空音频即判可用；
    单次 NoAudioReceived（灰色通道突发抖动）会被 attempts 次重试吸收。"""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False, "edge-tts 未安装"
    import asyncio
    import tempfile
    import time

    patch_edge_tts_ssl()

    async def _synth(out):
        import edge_tts

        await edge_tts.Communicate("语音合成测试", voice).save(out)

    last_err = None
    for i in range(max(1, attempts)):
        out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
        try:
            asyncio.run(_synth(out))
            if os.path.exists(out) and os.path.getsize(out) > 0:
                os.remove(out)
                return True, "已安装，真实合成成功（注意：灰色通道可能抖动重试）"
        except Exception as e:  # noqa: BLE001
            last_err = e
        finally:
            if os.path.exists(out):
                try:
                    os.remove(out)
                except OSError:
                    pass
        time.sleep(1.0 * (i + 1))
    return False, "已安装但真实合成失败：%s" % (last_err or "未知")


def ffmpeg_has_filter(exe, filt):
    """检查 ffmpeg 是否编译进了某个滤镜（如 ass/subtitles）。

    `ffmpeg -h filter=<name>` 的退出码对存在/不存在都返 0，**不可靠**；判定靠输出
    文本：存在打印 'Filter <name>'，不存在打印 "Unknown filter '<name>'."。"""
    if not exe or not os.path.exists(exe):
        return False
    try:
        p = subprocess.run(
            [exe, "-hide_banner", "-h", "filter=" + filt],
            capture_output=True, text=True, timeout=25,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return ("Unknown filter" not in out) and ("Filter " in out)
    except Exception:
        return False


def libass_ffmpeg():
    """返回一个支持 libass（ass/subtitles 滤镜）的 ffmpeg 路径；找不到则报错指引。

    顺序：默认 ffmpeg_exe() 若含 ass 滤镜 → static-ffmpeg（pip 沙箱静态版，带 libass）
    → 明确报错。避免在缺 libass 的 ffmpeg（如部分 Homebrew 精简构建）上烧录字幕时
    报出晦涩的 filter 解析错误。"""
    primary = ffmpeg_exe()
    if ffmpeg_has_filter(primary, "ass"):
        return primary
    # 回落 static-ffmpeg：add_paths() 会把它的 bin 前置到 PATH，shutil.which 即得
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
        import shutil

        sf = shutil.which("ffmpeg")
        if sf and ffmpeg_has_filter(sf, "ass"):
            return sf
    except Exception:
        pass
    raise SystemExit(
        "当前 ffmpeg 不含 libass（无 ass/subtitles 滤镜），无法烧录字幕。\n"
        "任选其一解决：\n"
        " 1) pip install static-ffmpeg（沙箱静态版，自带 libass，无需动系统 ffmpeg）\n"
        " 2) 安装带 libass 的 ffmpeg，如 brew reinstall ffmpeg\n"
        " 3) 暂不烧录字幕：清理项目目录的 subs.ass 后重跑 pv_concat"
    )


def doctor():
    """环境自检：打印 ffmpeg 路径、edge-tts、字体情况。"""
    ensure_deps()
    print("ffmpeg:", ffmpeg_exe())
    import edge_tts

    print("edge-tts: ok (%s)" % getattr(edge_tts, "__version__", "?"))
    fonts = []
    for cand in (
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ):
        if os.path.exists(cand):
            fonts.append(cand)
    print("CJK fonts:", fonts or "未找到文泉驿字体（字幕可能回退默认字体）")


if __name__ == "__main__":
    doctor()
