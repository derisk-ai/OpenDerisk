### OpenDeRisk

OpenDeRisk は AI ネイティブリスクインテリジェンスシステムです。アプリケーションシステムのリスクインテリジェントマネージャーとして、24 時間 365 日の包括的で徹底的な保護を提供します。

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

[**English**](README.md) | [**简体中文**](README.zh.md) | [**日本語**](README.ja.md) | [**動画チュートリアル**](https://www.youtube.com/watch?v=1qDIu-Jwdf0)
</div>

### ニュース 
- [2025/10] 🔥 OpenDerisk V0.2 をリリースしました。[OpenDerisk V0.2 ReleaseNote](./docs/docs/OpenDerisk_v0.2.md) 


### 機能特徴
1. **DeepResearch RCA:** ログ、トレース、コードの詳細な分析により、問題の根本原因を迅速に特定します。
2. **可視化された証拠チェーン:** 診断プロセスと証拠チェーンを完全に可視化し、診断を明確にして精度を迅速に判断できます。
3. **マルチエージェント協調:** SRE-Agent、Code-Agent、ReportAgent、Vis-Agent、Data-Agent の協調作業。
4. **オープンソースアーキテクチャ:** OpenDeRisk は完全にオープンソースのアーキテクチャで構築されており、関連フレームワークとコードをオープンソースプロジェクトですぐに使用できます。

<p align="left">
  <img src="./assets/features.jpg" width="100%" />
</p>

### アーキテクチャ
<p align="left">
  <img src="./assets/arch_en.jpg" width="100%" />
</p>

#### 紹介文書
このシステムはマルチエージェントアーキテクチャを採用しています。現在、コードは主にハイライトされた部分を実装しています。アラート認識は Microsoft のオープンソース [OpenRCA データセット](https://github.com/microsoft/OpenRCA) に基づいています。データセットのサイズは解压後約 26GB です。このデータセット上で、マルチエージェントの協調により根本原因分析と診断を実現し、Code-Agent が最終分析のために動的にコードを作成します。

#### 技術実装
**データ層:** GitHub から大規模な OpenRCA データセット (20GB) を取得し、ローカルで解压して分析用に処理します。

**ロジック層:** マルチエージェントアーキテクチャで、SRE-Agent、Code-Agent、ReportAgent、Vis-Agent、Data-Agent が協調して詳細な DeepResearch RCA（根本原因分析）を実行します。

**可視化層:** Vis プロトコルを使用して、全体の処理フローと証拠チェーン、およびマルチロールの協調とスイッチングプロセスを動的にレンダリングします。

OpenDeRisk のデジタル従業員（エージェント）
<p align="left">
  <img src="./assets/ai-agent.png" width="100%" />
</p>

### インストール（推奨）

#### curl でのインストール

```shell
# 最新バージョンのダウンロードとインストール
curl -fsSL https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/install.sh | bash
```

#### 設定ファイル
インストール後、システムを設定する必要があります。設定ファイルを作成してください：
`~/.openderisk/derisk-proxy-aliyun.toml` を編集し、API キーを設定してください。

#### 起動
```
openderisk-server
```

### ソースからのインストール（開発用）

uv のインストール（必須）：
```shell

git clone https://github.com/derisk-ai/OpenDerisk.git

cd OpenDerisk

# 依存関係のインストール
sh scripts/prepare_release.sh
```

#### サーバーの起動

`derisk-proxy-aliyun.toml` で API_KEY を設定し、実行：

> 注意：デフォルトでは、OpenRCA データセットの Telecom データセットを使用します。リンクまたは以下のコマンドでダウンロードできます：
> `gdown https://drive.google.com/uc?id=1cyOKpqyAP4fy-QiJ6a_cKuwR7D46zyVe`

ダウンロード後、データセットを `pilot/datasets/` パスに移動します。

起動コマンドを実行：
```bash
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```

#### ウェブサイトへのアクセス

ブラウザを開いて [`http://localhost:7777`](http://localhost:7777) にアクセス


### 使用方法
* **AI-SRE (OpenRCA)**
  - 注意: OpenRCA データセットの [Bank データセット](https://drive.usercontent.google.com/download?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R&export=download&confirm=t&uuid=42621058-41af-45bf-88a6-64c00bfd2f2e) を使用しています
  - ダウンロード: `gdown https://drive.google.com/uc?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R`
  - データセットを `${derisk}/pilot/datasets` パスに配置します
* **フレームグラフアシスタント**
  - ローカルアプリケーションサービスプロセスのフレームグラフ (Java/Python) をアシスタントにアップロードして分析を行います
* **DataExpert**
  - メトリクス、ログ、トレース、または様々な Excel データシートをアップロードして対話型分析を行います

### 高速開発
* **エージェント開発**
  - `derisk-ext.agent.agents` 配下の実装ロジックを参照してください
* **ツール開発**
  * ローカルツール
  * MCP (Model Context Protocol)
* **DeRisk-Skills 開発**
  - [derisk-skills](https://github.com/derisk-ai/derisk_skills)

#### 実行結果
下图に示すように、複数のエージェントが協調して複雑な運用診断タスクを処理するシナリオを示しています。

<p align="left">
  <img src="./assets/scene_demo.png" width="100%" />
</p>

### 引用
このリポジトリのコードについては、以下の論文で詳細な紹介をしています。もし、あなたの研究に役立ったと思われる場合は、ぜひ引用してください。
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

### 謝辞
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT)
- [GPT-Vis](https://github.com/antvis/GPT-Vis)
- [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
- [OpenRCA](https://github.com/microsoft/OpenRCA)

OpenDeRisk-AI コミュニティは、AI ネイティブなリスクインテリジェンスシステムの構築に専念しています。🛡️ 私たちのコミュニティがより良いサービスを提供できることを願い、また皆様が私たちに参加してより良い未来を共に創造することを願っています。🤝


[![Star History Chart](https://api.star-history.com/svg?repos=derisk-ai/OpenDerisk&type=Date)](https://star-history.com/#derisk-ai/OpenDerisk)


### コミュニティグループ

DingTalk グループに参加して、他の開発者と経験を共有しましょう！

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDeRisk-AI 交流群" width="200" />
</div>