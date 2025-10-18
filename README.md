### OpenDeRisk

OpenDeRisk AI-Native Risk Intelligence Systems —— Your application system risk intelligent manager provides 7 * 24-hour comprehensive and in-depth protection.

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
  </p>

[**English**](README.md) | [**简体中文**](README.zh.md) | [**日本語**](README.ja.md) | [**视频教程**](https://www.youtube.com/watch?v=1qDIu-Jwdf0)
</div>


### News
- [2025/10] 🔥 We released OpenDerisk v0.2. [OpenDerisk V0.2 ReleaseNote](./docs/docs/OpenDerisk_v0.2.md) 


### Features
1. **DeepResearch RCA:** Quickly locate the root cause of issues through in-depth analysis of logs, traces, and code.
2. **Visualized Evidence Chain:** Fully visualize the diagnostic process and evidence chain, making the diagnosis clear and enabling quick judgment of accuracy.
3. **Multi-Agent Collaboration:** Collaboration among SRE-Agent, Code-Agent, ReportAgent, Vis-Agent, and Data-Agent.
4. **Open and Open-Source Architecture:** OpenDeRisk is built with a completely open and open-source architecture, allowing related frameworks and code to be used out of the box in open-source projects.

<p align="left">
  <img src="./assets/features.jpg" width="100%" />
</p>

### Architure
<p align="left">
  <img src="./assets/arch_en.jpg" width="100%" />
</p>

#### Introduction

- [OpenDerisk Documents](https://deepwiki.com/derisk-ai/OpenDerisk)

- [OpenDerisk DeepWiki](https://deepwiki.com/derisk-ai/OpenDerisk)


The system adopts a multi-agent architecture. Currently, the code mainly implements the green-highlighted parts. Alert awareness is based on Microsoft's open-source [OpenRCA dataset](https://github.com/microsoft/OpenRCA). The dataset size is approximately 26GB after decompression. On this dataset, we achieve root cause analysis and diagnosis through multi-agent collaboration, where the Code-Agent dynamically writes code for final analysis.

#### Technical Implementation
**Data Layer:** Pull the large-scale OpenRCA dataset (20GB) from GitHub, decompress it locally, and process it for analysis.

**Logic Layer:** Multi-agent architecture, with collaboration among SRE-Agent, Code-Agent, ReportAgent, Vis-Agent, and Data-Agent to perform in-depth DeepResearch RCA (Root Cause Analysis).

**Visualization Layer:** Use the Vis protocol to dynamically render the entire processing flow and evidence chain, as well as the process of multi-role collaboration and switching.

Digital Employees (Agents) in OpenDeRisk
<p align="left">
  <img src="./assets/ai-agent.png" width="100%" />
</p>

### Quick Start

Install uv

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

####  Install Packages

```
uv sync --all-packages --frozen \
--extra "base" \
--extra "proxy_openai" \
--extra "rag" \
--extra "storage_chromadb" \
--extra "derisks" \
--extra "storage_oss2" \
--extra "client"  \
--extra "ext_base"
```

#### Start

Configure the API_KEY in the `derisk-proxy-aliyun.toml` file, then run the following command to start.


> Note: By default, we use the Telecom dataset from the OpenRCA dataset. You can download it via the link or the following command:

> gdown https://drive.google.com/uc?id=1cyOKpqyAP4fy-QiJ6a_cKuwR7D46zyVe

After downloading, move the datasets to the path `pilot/datasets/`

Run the startup command:
```
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```

#### Visit Website

Open your browser and visit [`http://localhost:7777`](http://localhost:7777)
<p align="left">
  <img src="./assets/index.jpg" width="100%" />
</p>

### How to Use?
* AI-SRE(OpenRCA)
  -  !Notice, We Use the OpenRCA Datasets[Bank Dataset](https://drive.usercontent.google.com/download?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R&export=download&confirm=t&uuid=42621058-41af-45bf-88a6-64c00bfd2f2e),
  -  You can download the dataset using next link:
    ```
      gdown https://drive.google.com/uc?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R
    ```
  - Put the datasets to the path ${derisk}/pilot/datasets。
* Flame Graph Assistant
  - Upload the flame graph (Java/Python) of your local application service process to the assistant for analysis and inquiries.
* DataExpert
  - Upload your metrics, logs, traces, or various Excel data sheets for conversational analysis.


### Rapid Development
* Agent Development
    Refer to the implementation logic under `derisk-ext.agent.agents`.
* Tool Development
    * Local tool
    * MCP
* Other Development
    Documentation is under preparation...

#### Execution Results
As shown in the figure below, this demonstrates a scenario where multiple agents collaborate to handle a complex operational diagnostic task.

<p align="left">
  <img src="./assets/scene_demo.png" width="100%" />
</p>

### RoadMap
- [x] 0530 V0.1 Version: Based on domain knowledge and MCP services, achieving anomaly awareness -> autonomous decision-making -> adaptive execution and issue resolution.
  - [x] Domain knowledge engine for technical risks
  - [x] Reasoning engine driven by large models for anomaly awareness -> decision-making -> execution
  - [x] Automated troubleshooting and fixes

- [x] 0830 V0.2 Version
  - [x] MCP services and management for technical risks
  - [x] Support for custom binding of knowledge and MCP tools
  - [x] Support for 3+ DevOps domain MCP services

- [ ] 0930 V0.3 Version
  - [ ] Support for integration with production environments
  - [ ] Provide a complete production environment deployment solution, supporting production issue diagnosis.

- [ ] 1230 V0.4 Version
  - [ ] End-to-end AIOps online Agentic RL
  - [ ] End-to-end evaluation capabilities

### Citation
The code (training, serving, and evaluation) in this repository is mostly developed for or derived from the paper below. Please cite it if you find the repository helpful.
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

Join our networking group on Dingding and share your experience with other developers!

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDeRisk-AI 交流群" width="300" />
</div>
