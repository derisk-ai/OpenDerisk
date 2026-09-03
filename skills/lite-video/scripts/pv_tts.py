#!/usr/bin/env python3
"""阶段 tts：多 provider 路由的逐镜旁白合成（参考 OpenMontage tts_selector 设计）。

Provider 优先级与定位：
  piper      本地离线（确定性 100%，零 key；韵律平直，适合兜底，不适合中英混读）
  cmd        用户自定义命令模板（接入任意引擎的逃生通道，--provider-cmd）
  dashscope  正规云 API（音质好、韵律自然，需 API key）
  edge-tts   灰色通道（韵律自然，但逆向微软接口，可能随时 403）

路由规则：--provider 手动锁定；否则按质量优先 [cmd, dashscope, edge-tts, piper]
顺序探测，首个合成成功的锁定为全片音色，失败的自动级联降级。

配置来源（优先级从高到低）：
  1. CLI 参数（--provider/--voice/--rate/--provider-cmd/--piper-model/--silence）
  2. 环境变量（DASHSCOPE_API_KEY）
  3. tts.yaml 配置文件（先找 <项目目录>/tts.yaml，再找 <skill目录>/tts.yaml）
  4. 内置默认值

朗读文本分离（修复中英混读）：每镜的"字幕文本"用 narration（原文），
"朗读文本"用 tts_text（可为空，空则回退 narration）。
中英夹杂场景下应提供转写后的朗读文本，如 "OpenClaw" → "欧盆扣"，
保证 TTS 不乱读，而字幕仍显示原文。

用法：
  python3 pv_tts.py --dir <项目目录> [--voice 音色] [--rate +0%]
                    [--provider auto|piper|cmd|dashscope|edge-tts]
                    [--provider-cmd "模板"] [--piper-model 模型路径]
                    [--silence 0.35] [--force]

piper 模型：默认找 <项目目录>/piper_model/*.onnx、~/.local/share/piper/*.onnx、
./piper-voices/*.onnx；或用 --piper-model 指定。中文音色下载：
  python3 -m piper.download_voices zh_CN-huayan-medium（或从镜像下载，见 SKILL.md）

cmd provider 模板占位符：{text} 文本 / {out} 输出路径（输出建议 wav/mp3）。
"""
import argparse
import asyncio
import glob
import os
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import ffmpeg_exe, connect_db, get_shots, get_project, ffprobe_duration

MAX_RETRIES = 2
RETRY_BACKOFF = 2.0
# 质量优先：有云/公网可用就不退化到平直的本地 piper；piper 永远兜底
PROVIDER_ORDER = ["cmd", "dashscope", "edge-tts", "piper"]
# piper 句间停顿默认值（秒）：修复"连着不断"的问题，可用 --silence / tts.yaml 调整
PIPER_SENTENCE_SILENCE = 0.35
DEFAULT_EDGE_VOICE = "zh-CN-YunxiNeural"
DEFAULT_DASHSCOPE_VOICE = "longwan"

PIPER_MODEL_SEARCH = [
    "{project}/piper_model/*.onnx",
    os.path.expanduser("~/.local/share/piper/*.onnx"),
    "./piper-voices/*.onnx",
]


def _patch_edge_tts_ssl():
    """edge-tts 默认用 certifi 证书包；企业代理（自签名 CA 注入系统证书链）
    环境会校验失败。改用系统默认证书链。"""
    try:
        import ssl

        import edge_tts.communicate as _c

        if hasattr(_c, "_SSL_CTX"):
            _c._SSL_CTX = ssl.create_default_context()
    except Exception:
        pass


# ---------- tts.yaml 配置加载 ----------

def _parse_yaml_value(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def load_tts_config(project_dir):
    """读取 tts.yaml（先项目目录后 skill 目录）。返回 dict（可能为空）。
    只支持扁平 key: value 格式；值含特殊字符请用引号包裹。"""
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(project_dir, "tts.yaml"),
                 os.path.join(skill_dir, "tts.yaml")):
        if not os.path.exists(cand):
            continue
        cfg = {"__file__": cand}
        try:
            with open(cand, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or ":" not in s:
                        continue
                    k, v = s.split(":", 1)
                    k = k.strip()
                    if k and not k.startswith("#"):
                        cfg[k] = _parse_yaml_value(v)
        except Exception as e:  # noqa: BLE001
            print("tts.yaml 解析失败（%s），忽略该配置: %s" % (cand, e))
            return {}
        return cfg
    return {}


# ---------- provider 可用性探测 ----------

def find_piper_model(project_dir, explicit):
    if explicit and os.path.exists(explicit):
        return explicit
    for pat in PIPER_MODEL_SEARCH:
        hits = sorted(glob.glob(pat.format(project=project_dir)))
        if hits:
            return hits[0]
    return None


def piper_available(project_dir, explicit):
    try:
        import piper  # noqa: F401
    except ImportError:
        return False, "piper-tts 未安装（pip install piper-tts）"
    model = find_piper_model(project_dir, explicit)
    if not model:
        return False, "piper 已装但无音色模型（--piper-model 或下载中文模型）"
    return True, model


def cmd_available(cmd_tpl):
    if not cmd_tpl:
        return False, "未提供 --provider-cmd"
    return True, cmd_tpl


def dashscope_available():
    key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_KEY")
    if not key:
        return False, "无 DASHSCOPE_API_KEY 环境变量（或 tts.yaml 的 dashscope_api_key）"
    return True, "key 已配置"


def _probe_edge_ws():
    """轻量 WebSocket 握手探测，返回 HTTP 状态码字符串（超时/异常返回 ''）。
    仅供参考——这是不带 edge-tts 完整协议头（Sec-MS-GEC token 等）的简化握手，
    与真实客户端行为可能不一致。"""
    try:
        p = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "8",
             "-H", "Connection: Upgrade", "-H", "Upgrade: websocket",
             "-H", "Sec-WebSocket-Version: 13",
             "-H", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
             "-H", "User-Agent: Mozilla/5.0 Edg/130.0.0.0",
             "https://speech.platform.bing.com/consumer/speech/synthesize/"
             "readaloud/edge/v1?TrustedClientToken=6A5AA1D4EAFF4E9FB37E23D68491D6F4"],
            capture_output=True, text=True, timeout=15,
        )
        return p.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def edge_tts_available():
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False, "edge-tts 未安装"
    # 轻量网络探测（仅参考，不做一票否决）：端口可达即认为可尝试，
    # 运行时真实失败由级联降级机制兜底（ban 后自动切下一候选）
    code = _probe_edge_ws()
    if code in ("101", "400"):
        return True, "已安装，探测正常（HTTP %s）" % code
    if code:
        return True, ("已安装，简化探测被拒（HTTP %s）但不以此为准——"
                      "真实合成为准，失败自动降级" % code)
    return True, "已安装（探测跳过：环境无 curl），真实合成为准"


def candidate_chain(args):
    """返回有序候选列表 [(provider, info), ...]。
    手动锁定模式只返回指定项；auto 按质量优先序返回全部探测可用项。
    探测一律 fail-open（仅 import 级检查），真实可用性由合成探针/级联降级裁决。"""
    forced = args.provider and args.provider != "auto"
    if forced:
        ok, info = probe(args.provider, args)
        if not ok:
            raise SystemExit("指定的 provider %s 不可用: %s" % (args.provider, info))
        return [(args.provider, info)]
    chain = []
    for name in PROVIDER_ORDER:
        ok, info = probe(name, args)
        if ok:
            chain.append((name, info))
    if not chain:
        raise SystemExit(
            "没有任何可用的 TTS provider。\n"
            "建议（按质量优先）：\n"
            " 1) 正规云: 设置 DASHSCOPE_API_KEY（环境变量或 tts.yaml）后用 "
            "--provider dashscope（韵律自然）\n"
            " 2) 公网: pip install edge-tts 且保证公网可达（韵律自然，灰色通道）\n"
            " 3) 本地 Piper: pip install piper-tts + 中文模型（确定性兜底，韵律平直）\n"
            " 4) 自定义: --provider-cmd \"模板\" 或写入 tts.yaml 的 cmd_template\n"
            "    （接 edge-tts CLI 的标准包装见 SKILL.md「cmd 包装 edge-tts」）"
        )
    return chain


def probe(name, args):
    if name == "piper":
        return piper_available(args.dir, args.piper_model)
    if name == "cmd":
        return cmd_available(args.provider_cmd)
    if name == "dashscope":
        return dashscope_available()
    if name == "edge-tts":
        return edge_tts_available()
    return False, "未知 provider: %s" % name


# ---------- 各 provider 合成实现 ----------

def synth_piper(text, model_path, out_mp3, rate, silence):
    wav = out_mp3 + ".tmp.wav"
    cmd = [sys.executable, "-m", "piper", "-m", model_path, "-f", wav]
    # piper 语速用 length-scale：>1 变慢，<1 变快（与 edge-tts rate 语义相反）
    scale = 1.0 / max(0.5, min(2.0, 1.0 + _rate_pct(rate) / 100.0))
    cmd += ["--length-scale", "%.2f" % scale]
    # 句间停顿：修复"连着不断"的机械感（可调）
    if silence and silence > 0:
        cmd += ["--sentence-silence", "%.2f" % silence]
    p = subprocess.run(cmd, input=text, capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(wav):
        raise RuntimeError("piper 合成失败: %s" % p.stderr[-300:])
    subprocess.run([
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", wav, "-c:a", "libmp3lame", "-b:a", "128k", out_mp3,
    ], check=True)
    os.remove(wav)


async def _edge_synth(text, voice, rate, out):
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate).save(out)


def synth_edge(text, voice, rate, out):
    asyncio.run(_edge_synth(text, voice, rate, out))


def synth_dashscope(text, out, rate, voice):
    """DashScope cosyvoice TTS（正规云，需 API key）。voice 为 dashscope 音色名。"""
    import json
    import urllib.request

    key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_KEY")
    body = {
        "model": "cosyvoice-v1",
        "input": {"text": text},
        "parameters": {"voice": voice or DEFAULT_DASHSCOPE_VOICE, "format": "mp3"},
    }
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req, timeout=60)
    doc = json.loads(r.read().decode("utf-8"))
    url = (((doc.get("output") or {}).get("audio") or {}).get("url")
           or (doc.get("output") or {}).get("audio", {}).get("url"))
    if not url:
        raise RuntimeError("dashscope 返回无音频: %s" % str(doc)[:200])
    urllib.request.urlretrieve(url, out)


def synth_cmd(text, out, cmd_tpl):
    cmd = cmd_tpl.format(text=shlex.quote(text), out=shlex.quote(out))
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("cmd provider 失败（退出码 %d）: %s"
                           % (p.returncode, p.stderr[-300:]))


def _rate_pct(rate):
    """把 '+10%'/'-5%' 转成数值百分比，解析失败返回 0。"""
    try:
        return float(rate.strip().rstrip("%"))
    except (ValueError, AttributeError):
        return 0


# 明显属于网络层失败的错误关键词：命中即快速出局，不浪费重试
_NET_ERR_MARKERS = (
    "ClientConnectorCertificateError", "WSServerHandshakeError", "403",
    "CERTIFICATE_VERIFY_FAILED", "ClientConnectorError", "ClientHttpProxyError",
    "TimeoutError", "ServerTimeoutError", "ServerDisconnectedError",
    "ConnectionRefusedError", "OSError", "Cannot connect", "nodename nor servname",
)


def _is_net_error(err):
    s = type(err).__name__ + " " + str(err)
    return any(m in s for m in _NET_ERR_MARKERS)


def synth_one(provider, info, speak, voice, rate, out, silence):
    """按 provider 分派单次合成（不含重试）。"""
    if provider == "piper":
        synth_piper(speak, info, out, rate, silence)
    elif provider == "cmd":
        synth_cmd(speak, out, info)
    elif provider == "dashscope":
        synth_dashscope(speak, out, rate, voice)
    else:
        _patch_edge_tts_ssl()
        synth_edge(speak, voice, rate, out)


def synth_with_retry(provider, info, speak, voice, rate, out, silence):
    """单 provider 带重试合成。返回 (成功, 时长, 错误)。
    网络层错误（证书/403/连接拒绝等）快速失败：重试无用，直接出局交给级联降级。"""
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            synth_one(provider, info, speak, voice, rate, out, silence)
            dur = ffprobe_duration(out)
            if dur > 0.5:
                return True, dur, None
            last_err = RuntimeError("音频过短: %.2fs" % dur)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if _is_net_error(e):
                print("  [%s] 网络层错误（%s），快速出局不重试"
                      % (provider, str(e)[:60]))
                return False, 0.0, last_err
        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF * (2 ** attempt)
            print("  [%s] 第 %d 次失败（%s），%.0fs 后重试"
                  % (provider, attempt + 1, str(last_err)[:80], wait))
            time.sleep(wait)
    return False, 0.0, last_err


def probe_real_synth(provider, info, voice, rate, silence, tmp_dir):
    """试合成探针：用一段超短文本真实合成一次，验证 provider 真实可用性。
    仅 edge-tts 启用（探测与真实行为可能不一致的灰色通道）。
    返回 (成功, 错误)。失败即全局 ban，不再浪费时间。"""
    if provider != "edge-tts":
        return True, None
    tmp = os.path.join(tmp_dir, ".probe_edge.mp3")
    try:
        synth_one(provider, info, "测试", voice, rate, tmp, silence)
        ok = os.path.exists(tmp) and ffprobe_duration(tmp) > 0.3
        if ok:
            os.remove(tmp)
        return ok, None if ok else RuntimeError("探针音频无效")
    except Exception as e:  # noqa: BLE001
        return False, e


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="项目目录（含 production.db）")
    ap.add_argument("--voice", help="音色（覆盖 projects 表/tts.yaml；"
                                    "edge-tts 用 zh-CN-XXX，dashscope 用 longwan 等）")
    ap.add_argument("--rate", help="语速，如 +10%% / -10%%（默认取 tts.yaml 或 +0%%）")
    ap.add_argument("--provider",
                    choices=["auto", "piper", "cmd", "dashscope", "edge-tts"],
                    help="手动锁定 provider（默认 auto，可被 tts.yaml 的 provider 覆盖）")
    ap.add_argument("--provider-cmd", help="cmd provider 命令模板（{text}/{out}）")
    ap.add_argument("--piper-model", help="piper ONNX 模型路径")
    ap.add_argument("--silence", type=float,
                    help="piper 句间停顿秒数（默认取 tts.yaml 或 0.35）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    conn = connect_db(args.dir)
    try:
        pr = get_project(conn)
        shots = get_shots(conn)
        if not shots:
            raise SystemExit("shots 表为空，请先用 pv_db.py set-shots 写入分镜")

        # ---- 配置合并：CLI > 环境变量 > tts.yaml > 内置默认 ----
        cfg = load_tts_config(args.dir)
        if cfg:
            print("已加载 TTS 配置: %s" % cfg.get("__file__"))
            # tts.yaml 中的 dashscope_api_key 注入环境变量（不覆盖已存在的）
            if cfg.get("dashscope_api_key"):
                os.environ.setdefault("DASHSCOPE_API_KEY", cfg["dashscope_api_key"])
        if args.provider is None:
            args.provider = cfg.get("provider") or "auto"
        if args.voice is None:
            args.voice = cfg.get("voice") or None
        if args.rate is None:
            args.rate = cfg.get("rate") or "+0%"
        if not args.provider_cmd:
            args.provider_cmd = cfg.get("cmd_template") or None
        if not args.piper_model:
            args.piper_model = cfg.get("piper_model") or None
        silence = args.silence if args.silence is not None \
            else float(cfg.get("piper_silence", PIPER_SENTENCE_SILENCE))

        # 音色解析：edge 音色与 dashscope 音色命名不同，分开处理
        edge_voice = args.voice or pr["voice"] or DEFAULT_EDGE_VOICE
        dash_voice = args.voice if args.voice and not args.voice.startswith("zh-CN") \
            else cfg.get("voice", DEFAULT_DASHSCOPE_VOICE)

        chain = candidate_chain(args)
        print("TTS 候选链: %s（rate=%s, piper句间停顿=%.2fs）"
              % (" > ".join(p for p, _ in chain), args.rate, silence))
        audio_dir = os.path.join(args.dir, "audio")
        os.makedirs(audio_dir, exist_ok=True)

        locked = None      # 首个合成成功的 provider，锁定后全片统一音色
        banned = set()     # 运行时失败的候选，全局出局
        total = 0.0
        for fr in shots:
            out = os.path.join(audio_dir, "shot_%02d.mp3" % fr["id"])
            # 朗读文本分离：优先用转写后的朗读文本，无则用原文
            speak = (fr.get("tts_text") or fr.get("narration") or "").strip()
            if not speak:
                raise SystemExit("shot_%02d 旁白为空" % fr["id"])
            cached, dur = os.path.exists(out), 0.0
            if cached:
                try:
                    dur = ffprobe_duration(out)
                except RuntimeError:
                    cached = False
            if cached and dur > 0.5 and not args.force:
                print("跳过 shot_%02d（已存在 %.2fs）" % (fr["id"], dur))
            else:
                ok = False
                # 级联降级：锁定优先，否则按候选链逐个尝试
                order = ([locked] if locked else [p for p, _ in chain if p not in banned])
                for pname in order:
                    pinfo = next(i for p, i in chain if p == pname)
                    v = dash_voice if pname == "dashscope" else edge_voice
                    ok, dur, err = synth_with_retry(pname, pinfo, speak, v,
                                                    args.rate, out, silence)
                    if ok:
                        if locked is None or pname != locked:
                            locked = pname
                            print("TTS provider 锁定: %s（%s）" % (pname, pinfo))
                        print("shot_%02d TTS 完成: %.2fs" % (fr["id"], dur))
                        break
                    banned.add(pname)
                    print("  provider %s 出局: %s" % (pname, str(err)[:100]))
                    if args.provider != "auto":
                        raise SystemExit(
                            "shot_%02d TTS（provider=%s）失败: %s"
                            % (fr["id"], pname, str(err)[:200])
                        )
                if not ok:
                    raise SystemExit(
                        "shot_%02d TTS 失败：所有候选 provider 均不可用。"
                        "运行 pv_setup.py 查看修复指引。" % fr["id"]
                    )
            conn.execute(
                "UPDATE shots SET audio_path=?, duration=? WHERE id=?",
                (out, round(dur, 2), fr["id"]),
            )
            conn.commit()
            total += dur

        print("全部旁白完成（provider=%s），预计总时长 %.2fs" % (locked, total))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
