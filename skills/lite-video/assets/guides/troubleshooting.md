# 排错指引

> 本文件由 SKILL.md 的排错入口块引用；遇症状时按表查。


| 症状 | 排查 |
|---|---|
| TTS 全部重试失败 | 先跑 `pv_setup.py` 看 TTS provider 全景；优先装 piper（本地，`pip install piper-tts` + 下载中文模型）；其次配正规云 key；edge-tts 灰色通道可能被 403 封堵属已知风险；向用户说明，不得用占位音交付 |
| TTS 单镜失败后重试成功 | 正常（内置指数退避），无需处理 |
| webrender 报 "playwright not found" | `pip install playwright && playwright install chromium` |
| webrender 渲染慢/超时 | 降 `--workers` 到 1（内存不足时）；或降项目分辨率 |
| weblint 静态检查违禁调用 | 删除页面中的 Math.random/Date.now/rAF 等，改写为 __seek(t) 纯函数表达 |
| 片段时长不对齐（验证 FAIL） | 重跑该镜生成；fullvideo 路线 A 用 setpts 变速（见上文命令） |
| 成片无字幕 | 确认 `pv_subs.py` 已生成 `subs.ass` 且在 `pv_concat` 之前 |
| 字幕字体缺失（方块字） | 系统缺中文字体；安装文泉驿或 Noto CJK |
| 门控被拒（GATE VIOLATION） | 设计如此：先 `gate` → 展示 → 用户 `approve` 后再 `complete-stage` |
| complete 被拒（EVIDENCE REQUIRED） | 先跑 `pv_verify.py --stage <阶段>` 拿证据 |
| 顺序违规报错 | 状态机要求按序推进；用 `next-stage` 确认当前应做阶段 |
| 沙箱/受限环境 CPU 超限被杀 | 编码已用轻量档（veryfast/threads=2）；仍被杀则分步重跑被中断的阶段（幂等） |

