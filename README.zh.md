### OpenDeRisk

OpenDeRisk AI 原生风险智能系统 —— 7×24 小时应用系统 AI 数字运维助手 (AI-SRE)。我们的愿景是为每个应用系统提供一个 7×24 小时的 AI 系统数字管家，能够与真人协同工作，7×24 小时处理业务问题，构建深度护航与防护网。

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


### 最新动态
- [2025/10] 🔥 我们发布了 OpenDerisk V0.2 版本。[OpenDerisk V0.2 ReleaseNote](./docs/docs/OpenDerisk_v0.2.md) 

### 核心特性
<p align="left">
  <img src="./assets/feature_zh.png" width="100%" />
</p>

1. **DeepResearch RCA**: 通过深度分析日志、Trace、代码进行问题根因的快速定位。
2. **可视化证据链**: 诊断过程与证据链全部可视化展示，诊断过程一目了然，可快速判断定位准确性。
3. **多智能体协同**: SRE-Agent、Code-Agent、ReportAgent、Vis-Agent、Data-Agent 协同工作。
4. **开源开放架构**: OpenDerisk 采用完全开源、开放的方式构建，相关框架、代码在开源项目中可开箱即用。

### 架构方案 
<p align="left">
  <img src="./assets/arch_zh.png" width="100%" />
</p>

#### 项目介绍
系统采用多 Agent 架构，目前代码主要实现了高亮部分。告警感知基于微软开源的 [OpenRCA 数据集](https://github.com/microsoft/OpenRCA)，数据集解压后约 26GB。在该数据集上，我们通过多 Agent 协同实现根因分析诊断，Code-Agent 动态编写代码进行最终分析。

#### 技术实现
1. **数据层**: 从 GitHub 拉取大规模 OpenRCA 数据集 (20GB)，本地解压处理分析。
2. **逻辑层**: Multi-Agent 架构，通过 SRE-Agent、Code-Agent、ReportAgent、VisAgent、Data-Agent 协同合作，进行深度的 DeepResearch RCA (Root Cause Analysis) 根因分析。
3. **可视化层**: 采用 Vis 协议动态渲染整个处理流程与证据链，以及多角色协同切换的过程。

OpenDeRisk 中的数字员工 (Agent)
<p align="left">
  <img src="./assets/ai-agent.png" width="100%" />
</p>

### 安装（推荐）

#### 使用 curl 安装

```shell
# 下载并安装最新版本
curl -fsSL https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/install.sh | bash
```

#### 配置文件
安装完成后，需要配置系统。创建配置文件：
编辑 `~/.openderisk/derisk-proxy-aliyun.toml` 并设置您的 API 密钥。

#### 启动
```
openderisk-server
```

### 从源码安装（开发环境）

安装 uv（必需）：
```shell

git clone https://github.com/derisk-ai/OpenDerisk.git

cd OpenDerisk

# 安装依赖
sh scripts/prepare_release.sh
```

#### 启动服务

在 `derisk-proxy-aliyun.toml` 中配置 API_KEY，然后运行：

> 注意：默认使用 OpenRCA 的 Telecom 数据集。通过以下链接或命令下载：
> `gdown https://drive.google.com/uc?id=1cyOKpqyAP4fy-QiJ6a_cKuwR7D46zyVe`

下载后，将数据集移动到 `pilot/datasets/` 目录。

运行启动命令：
```bash
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```

#### 访问 Web 界面

打开浏览器访问 [`http://localhost:7777`](http://localhost:7777)

##### 2. 内置场景快速使用
* **AI-SRE (OpenRCA 根因定位)**
  - 注意: 默认使用 OpenRCA 数据集中的 [Bank 数据集](https://drive.usercontent.google.com/download?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R&export=download&confirm=t&uuid=42621058-41af-45bf-88a6-64c00bfd2f2e)
  - 下载命令: `gdown https://drive.google.com/uc?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R`
  - 下载后解压到 `${derisk项目}/pilot/datasets`
* **火焰图助手**
  - 上传本地应用服务进程的火焰图 (Java/Python) 进行分析
* **DataExpert**
  - 上传指标、日志、Trace 等各种 Excel 表格数据进行对话分析

##### 3. 快速开发
* **Agent 开发**
  - 参考 `derisk-ext.agent.agents` 下的实现逻辑
* **工具开发**
  - Skills 
  - MCP (Model Context Protocol)
* **DeRisk-Skills 开发**
  - [derisk-skills](https://github.com/derisk-ai/derisk_skills)

#### 运行效果
多智能体协同处理复杂运维诊断任务场景:
<p align="left">
  <img src="./assets/scene_demo.png" width="100%" />
</p>

### 引用
如对您的工作有帮助，请引用以下论文:
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

### 致谢 
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT)
- [GPT-Vis](https://github.com/antvis/GPT-Vis)
- [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
- [OpenRCA](https://github.com/microsoft/OpenRCA)

OpenDeRisk-AI 社区致力于构建 AI 原生的风险智能系统。🛡️ 我们希望社区能够为您提供更好的服务，同时也期待您的加入，共同创造更美好的未来。🤝


[![Star History Chart](https://api.star-history.com/svg?repos=derisk-ai/OpenDerisk&type=Date)](https://star-history.com/#derisk-ai/OpenDerisk)

### 社区 

加入钉钉群，与我们一起交流讨论:

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDeRisk-AI 交流群" width="300" />
</div>