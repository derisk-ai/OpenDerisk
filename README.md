### OpenDeRisk

OpenDeRisk AI-Native Risk Intelligence Systems —— Your application system risk intelligent manager provides 7 * 24-hour comprehensive and in-depth protection.

### Features
1. DeepResearch RCA: 通过深度分析日志、Trace、代码进行问题根因的快速定位。
2. 可视化证据链：定位诊断过程与证据链全部可视化展示，诊断过程一目了然，可以快速判断定位的准确性。
3. 多智能体协同: SRE-Agent、Code-Agent、ReportAgent、Vis-Agent、Data-Agent协同工作。
4. 架构开源开放: OpenDerisk采用完全开源、开放的方式构建，相关框架、代码在开源项目也能实现开箱即用。

### Quick Start

Install uv

```python
curl -LsSf https://astral.sh/uv/install.sh | sh
```

####  Install Packages

```
uv sync --all-packages --frozen \
--extra "base" \
--extra "proxy_openai" \
--extra "rag" \
--extra "storage_chromadb" \
--extra "client" \
--index-url=https://pypi.tuna.tsinghua.edu.cn/simple
```

#### Start

Config `API_KEY` at `derisk-proxy-deepseek.toml`, and the run follow command.

```
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-deepseek.toml
```

#### Visit Website

Open your browser and visit [`http://localhost:7777`](http://localhost:7777)


### Acknowledgement 
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT)
- [GPT-Vis](https://github.com/antvis/GPT-Vis)
- [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
- [OpenRCA](https://github.com/microsoft/OpenRCA)

The OpenDeRisk-AI community is dedicated to building AI-native risk intelligence systems. 🛡️ We hope our community can provide you with better services, and we also hope that you can join us to create a better future together. 🤝

### Community Group

Join our networking group on Feishu and share your experience with other developers!

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDeRisk-AI 交流群" width="200" />
</div>
