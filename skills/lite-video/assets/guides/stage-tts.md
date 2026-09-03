# 阶段 3 · tts（三种模式相同）

> 本文件由 SKILL.md 的 tts 入口块引用；进入旁白合成时必读。


```bash
python3 scripts/pv_tts.py --dir <目录> [--provider auto|piper|cmd|dashscope|edge-tts] \
    [--voice ...] [--rate +10%] [--piper-model <模型>] [--provider-cmd "模板"]
python3 scripts/pv_verify.py --dir <目录> --stage tts
python3 scripts/pv_db.py --dir <目录> complete-stage --stage tts
```

**provider 路由**（质量优先 + 级联降级；借鉴 OpenMontage tts_selector）：
`auto` 按质量优先序探测候选链，首个合成成功的锁定为全片音色，失败的自动出局——

**探测语义（重要，勿误判）**：`auto` 的可用性探测对 edge-tts 采用 **fail-open**——
轻量的 curl 握手探测不带 edge-tts 完整协议头，被拒（404/403）**不代表**真实不可用，
只作参考；**真实合成才是裁判**。因此即使探测报"被拒"，edge-tts 仍会进候选链实际尝试；
真实合成失败（如网络层 403）才会被 ban 并自动降级到下一候选。
不要因为 `pv_setup.py` 里看到"探测被拒"就断定 edge-tts 不能用。

| 优先级 | provider | 韵律质量 | 要求 |
|---|---|---|---|
| 1 | **cmd** | 取决于接入引擎 | `--provider-cmd`（占位符 `{text}/{out}`） |
| 2 | **dashscope** | 自然，中英混读好 | 环境变量 `DASHSCOPE_API_KEY` |
| 3 | **edge-tts** | 自然，中英混读好 | 公网可达（逆向灰色通道，可能随时 403） |
| 4 | **piper** | **平直、无起伏**，中英混读差 | `pip install piper-tts` + 音色模型 |

**关于配音质量（重要，写剧本时就要知道）**：
- piper 是架构性平直（无声调韵律模型），只适合兜底，**不要指望它有起伏**；
  追求自然旁白必须用 dashscope 或 edge-tts
- 中英混读（"OpenClaw"这类词）：piper 会乱读。写作规范——剧本阶段为每个
  含英文/数字/符号的镜头提供 `tts_text`（朗读转写文本，如 "OpenClaw" → "欧盆扣"），
  字幕仍显示 `narration` 原文；`pv_tts.py` 自动优先用 `tts_text`
- 纯中文内容 + piper 兜底时，句间停顿已内置（0.35s），仍建议分镜旁白多用
  逗号断句、控制单句长度，减轻机械感

- Piper 中文音色下载（约 60MB）：
  `python3 -m piper.download_voices zh_CN-huayan-medium`；
  受限网络用镜像：`https://hf-mirror.com/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx`
  （连同同名 `.onnx.json`），放入项目目录 `piper_model/`
- 没有任何可用 provider 时脚本会明确报错并给出修复指引——**禁止用占位音冒充交付**
- 音色默认男声 `zh-CN-YunxiNeural`（edge-tts 语义）；piper 用 `--piper-model` 换音色；
  儿童/情感类主题先问用户
- 脚本内置指数退避重试（单镜最多 3 次尝试）；全部重试失败会给出排错提示
- 用付费云（dashscope 等）时按 `assets/guides/cost-strategy.md` 登记 `cost-log`

**TTS 配置（`tts.yaml`，想要更好的配音看这里）**：
配置优先级：CLI 参数 > 环境变量 > `tts.yaml` > 内置默认。
模板见 `assets/tts.yaml.example`，复制到项目目录或 skill 目录改名 `tts.yaml` 即可：

```yaml
provider: auto              # 或手动锁定 piper/cmd/dashscope/edge-tts
voice: zh-CN-YunxiNeural    # 音色（edge 用 zh-CN 系；dashscope 用 longwan 等）
rate: +0%                   # 语速
piper_silence: 0.35         # piper 句间停顿秒数
dashscope_api_key: sk-xxx   # 正规云 key（建议改用环境变量，勿入包）
cmd_template: "my-tts --text {text} --out {out}"   # 自定义引擎逃生通道
piper_model: /path/to/model.onnx
```

升级到更好配音的三条路：
1. **正规云**（推荐）：`export DASHSCOPE_API_KEY=sk-xxx` 或写进 `tts.yaml`，
   auto 路由会自动优先选它（韵律自然、中英混读好）
2. **自定义引擎**：任意本地/云端 TTS 写成 `cmd_template` 一行命令即可接入
3. **手动锁定**：`--provider dashscope` 跳过自动探测直接指定

**cmd 包装 edge-tts（备选逃生通道）**：
若你想让 edge-tts 走 cmd 通道（例如固定用 CLI 版、或内置路由之外还要单独挂一份），
标准包装命令（edge-tts 安装包自带 `edge-tts` CLI）：
```yaml
provider: cmd
cmd_template: "edge-tts --voice zh-CN-YunxiNeural --text {text} --write-media {out}"
```
注意：`{text}`/`{out}` 已由脚本用 shlex.quote 转义，命令里直接引用即可。
不过通常无需这么做——内置的 `edge-tts` provider 已能正确处理，且级联降级会自动兜底。

