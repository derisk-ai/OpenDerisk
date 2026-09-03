# 环境监察与自动准备（Step 0）

> 本文件由 SKILL.md 的 Step 0 入口块引用；进入开工前环境检查时必读。


**接到视频生成请求后、任何生产动作之前，先跑环境监察**：

```bash
python3 scripts/pv_setup.py --mode <imageflow|webanim|fullvideo|all>
```

- 脚本逐项检测依赖（python/sqlite/Pillow/ffmpeg/edge-tts/中文字体/TTS 网络），
  缺失项**自动安装**（Pillow、imageio-ffmpeg、edge-tts 走 pip）
- webanim 模式额外检测 playwright + Chromium；浏览器未装时追加
  `--install-browsers` 自动下载（约 150MB，先征得用户同意）
- 解读报告：
  - `✅ 环境就绪` → 直接进入剧本讨论
  - `⚠️ 就绪但有提醒` → **TTS 结论**显示没有任何可用 provider 时（piper 缺包/模型、
    无云 key、edge-tts 被拦），必须向用户声明旁白无法真实合成，确认修复方案或换环境
    后再开工；**中文字体缺失**会影响字幕渲染，同样如实告知
  - `❌ 硬性缺失`（退出码 1）→ 向用户报告缺失项与手动安装命令，
    未修复前**禁止开工**，更禁止用占位产物冒充交付
- 模式决策（见下节）确定后如更换模式，按新模式**重跑一次** `pv_setup.py`

## 依赖清单（参考，日常以 pv_setup.py 报告为准）

- `ffmpeg`：脚本自动经 `imageio-ffmpeg`（pip）获取，无需手动安装
- `edge-tts`、`Pillow`：脚本自动检测并安装
- `sqlite3`：Python 标准库自带
- `playwright` + Chromium：**仅 webanim 模式需要**。检查 `python3 -c "import playwright"`；
  缺失时 `pip install playwright && playwright install chromium`
- 网络要求：TTS 需访问 edge-tts 服务（公网环境）。纯内网无法生成旁白时，
  向用户说明并停止，**不要用占位音冒充**。

