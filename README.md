### OpenDeRisk

OpenDeRisk is an AI-Native Risk Intelligence System designed as your application system's intelligent manager, providing 7×24 hour comprehensive and in-depth protection.

<div align="center">
  <p>
    <a href="https://github.com/derisk-ai/OpenDerisk">
        <img alt="stars" src="https://img.shields.io/github/stars/derisk-ai/OpenDerisk?style=social" />
    </a>
    <a href="https://github.com/derisk-ai/OpenDerisk">
        <img alt="forks" src="https://img.shields.io/github/forks/derisk-ai/OpenDerisk?style=social" />
    </a>
    <a href="https://opensource.org/licenses/MIT">
      <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg" />
    </a>
     <a href="https://github.com/derisk-ai/OpenDerisk/releases">
      <img alt="Release Notes" src="https://img.shields.io/github/release/derisk-ai/OpenDerisk" />
    </a>
    <a href="https://github.com/derisk-ai/OpenDerisk/issues">
      <img alt="Open Issues" src="https://img.shields.io/github/issues-raw/derisk-ai/OpenDerisk" />
    </a>
    <a href="https://codespaces.new/derisk-ai/OpenDerisk">
      <img alt="Open in GitHub Codespaces" src="https://github.com/codespaces/badge.svg" />
    </a>
    <a href="https://discord.com/invite/bgWkskhe">
      <img alt="Discord" src="https://img.shields.io/discord/1335244307281457152?color=7289DA&label=Discord&logo=discord&logoColor=white" />
    </a>
  </p>

[**English**](README.md) | [**简体中文**](README.zh.md) | [**日本語**](README.ja.md) | [**Video Tutorial**](https://www.youtube.com/watch?v=1qDIu-Jwdf0)
</div>

### Features
1. **DeepResearch RCA:** Quickly locate root causes through in-depth analysis of logs, traces, and code.
2. **Visualized Evidence Chain:** Fully visualize diagnostic processes and evidence chains for clear, accurate judgment.
3. **Multi-Agent Collaboration:** SRE-Agent, Code-Agent, ReportAgent, Vis-Agent, and Data-Agent working in coordination.
4. **Open-Source Architecture:** Built with a completely open architecture, enabling framework and code reuse in open-source projects.

<p align="left">
  <img src="./assets/features.jpg" width="100%" />
</p>

### Architecture
<p align="left">
  <img src="./assets/arch_en.jpg" width="100%" />
</p>

#### Introduction
The system employs a multi-agent architecture. Currently, the code primarily implements the highlighted components. Alert awareness is based on Microsoft's open-source [OpenRCA dataset](https://github.com/microsoft/OpenRCA). The decompressed dataset is approximately 26GB. On this dataset, we achieve root cause analysis through multi-agent collaboration, with Code-Agent dynamically writing code for final analysis.

#### Technical Implementation
**Data Layer:** Pull the large-scale OpenRCA dataset (20GB) from GitHub, decompress locally, and process for analysis.

**Logic Layer:** Multi-agent architecture with SRE-Agent, Code-Agent, ReportAgent, Vis-Agent, and Data-Agent collaborating for deep DeepResearch RCA (Root Cause Analysis).

**Visualization Layer:** Use the Vis protocol to dynamically render the entire processing flow and evidence chain, as well as the multi-role collaboration and switching process.

Digital Employees (Agents) in OpenDeRisk
<p align="left">
  <img src="./assets/ai-agent.png" width="100%" />
</p>

### Install (recommended)

#### Install via curl

```shell
# Download and install latest version
curl -fsSL https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/install.sh | bash
```
#### Configuration File
After installation, you need to configure the system. Create a configuration file:
Edit `~/.openderisk/derisk-proxy-aliyun.toml` and set your API keys.

#### Start 
```
openderisk-server  
```

### From source(development)

#### Install uv (required)

**macOS/Linux:**
```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```shell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### Clone and Install Dependencies

```shell
git clone https://github.com/derisk-ai/OpenDerisk.git

cd OpenDerisk

# Install Dependencies with uv
uv sync --all-packages --frozen \
    --extra "base" \
    --extra "proxy_openai" \
    --extra "rag" \
    --extra "storage_chromadb" \
    --extra "derisks" \
    --extra "storage_oss2" \
    --extra "client" \
    --extra "ext_base"
```

#### Start Server

Configure the API_KEY in `derisk-proxy-aliyun.toml`, then run:

> Note: By default, we use the Telecom dataset from OpenRCA. Download via:
> `gdown https://drive.google.com/uc?id=1cyOKpqyAP4fy-QiJ6a_cKuwR7D46zyVe`

After downloading, move datasets to `pilot/datasets/`

Run the startup command:
```bash
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```

#### Access Web UI

Open your browser and visit [`http://localhost:7777`](http://localhost:7777)
<p align="left">
  <img src="./assets/index.jpg" width="100%" />
</p>

### Usage Modes
* **AI-SRE (OpenRCA)**
  - Notice: We use the OpenRCA Dataset [Bank Dataset](https://drive.usercontent.google.com/download?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R&export=download&confirm=t&uuid=42621058-41af-45bf-88a6-64c00bfd2f2e)
  - Download: `gdown https://drive.google.com/uc?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R`
  - Place datasets in `${derisk}/pilot/datasets`
* **Flame Graph Assistant**
  - Upload flame graphs (Java/Python) from your local application for analysis
* **DataExpert**
  - Upload metrics, logs, traces, or Excel data for conversational analysis

### Development
* **Agent Development**
  - Refer to implementations under `derisk-ext.agent.agents`
* **Tool Development**
  - Skills
  - MCP (Model Context Protocol)
* **DeRisk-Skills**
  - [derisk-skills](https://github.com/derisk-ai/derisk_skills)

#### Execution Results
<p align="left">
  <img src="./assets/scene_demo.png" width="100%" />
</p>

### Citation
If you find this repository helpful, please cite:
```
@misc{di2025openderiskindustrialframeworkaidriven,
      title={OpenDerisk: An Industrial Framework for AI-Driven SRE, with Design, Implementation, and Case Studies}, 
      author={Peng Di and Faqiang Chen and Xiao Bai and Hongjun Yang and Qingfeng Li and Ganglin Wei and Jian Mou and Feng Shi and Keting Chen and Peng Tang and Zhitao Shen and Zheng Li and Wenhui Shi and Junwei Guo and Hang Yu},
      year={2025},
      eprint={2510.13561},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2510.13561}, 
}
```

### Acknowledgement 
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT)
- [GPT-Vis](https://github.com/antvis/GPT-Vis)
- [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
- [OpenRCA](https://github.com/microsoft/OpenRCA)

The OpenDeRisk-AI community is dedicated to building AI-native risk intelligence systems. 🛡️ We hope our community can provide you with better services, and we also hope that you can join us to create a better future together. 🤝

[![Star History Chart](https://api.star-history.com/svg?repos=derisk-ai/OpenDerisk&type=Date)](https://star-history.com/#derisk-ai/OpenDerisk)


### Community Group

Join our DingTalk group and share your experience with other developers!

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDeRisk-AI Community" width="300" />
</div>