### OpenDeRisk

OpenDeRisk AI-Native Risk Intelligence Systems —— AIネイティブなリスクインテリジェンスシステム。アプリケーションシステムのリスクインテリジェントマネージャーとして、24時間365日の包括的で徹底的な保護を提供します。

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

[**English**](README.md) | [**简体中文**](README.zh.md) | [**日本語**](README.ja.md) | [**視頻チュートリアル**](https://www.youtube.com/watch?v=1qDIu-Jwdf0)
</div>

### ニュース 
- [2025/10] 🔥 OpenDerisk V0.2をリリースしました. [OpenDerisk V0.2 ReleaseNote](./docs/docs/OpenDerisk_v0.2.md) 


### 機能特徴
1. **DeepResearch RCA:** ログ、トレース、コードの詳細な分析により、問題の根本原因を迅速に特定します。
2. **可視化された証拠チェーン:** 診断プロセスと証拠チェーンを完全に可視化し、診断を明確にして精度を迅速に判断できます。
3. **マルチエージェント協調:** SRE-Agent、Code-Agent、ReportAgent、Vis-Agent、Data-Agentの協調作業。
4. **オープンソースアーキテクチャ:** OpenDeRiskは完全にオープンソースのアーキテクチャで構築されており、関連フレームワークとコードをオープンソースプロジェクトですぐに使用できます。

<p align="left">
  <img src="./assets/features.jpg" width="100%" />
</p>

### アーキテクチャ
<p align="left">
  <img src="./assets/arch_en.jpg" width="100%" />
</p>

#### 紹介文書
- [OpenDerisk DeepWikiドキュメント](https://deepwiki.com/derisk-ai/OpenDerisk)

このシステムはマルチエージェントアーキテクチャを採用しています。現在、コードは主に緑色でハイライトされた部分を実装しています。アラート認識はMicrosoftのオープンソース[OpenRCAデータセット](https://github.com/microsoft/OpenRCA)に基づいています。データセットのサイズは解凍後約26GBです。このデータセット上で、マルチエージェントの協調により根本原因分析と診断を実現し、Code-Agentが最終分析のために動的にコードを作成します。

#### 技術実装
**データ層:** GitHubから大規模なOpenRCAデータセット（20GB）を取得し、ローカルで解凍して分析用に処理します。

**ロジック層:** マルチエージェントアーキテクチャで、SRE-Agent、Code-Agent、ReportAgent、Vis-Agent、Data-Agentが協調して詳細なDeepResearch RCA（根本原因分析）を実行します。

**可視化層:** Visプロトコルを使用して、全体の処理フローと証拠チェーン、およびマルチロールの協調とスイッチングプロセスを動的にレンダリングします。

OpenDeRiskのデジタル従業員（エージェント）
<p align="left">
  <img src="./assets/ai-agent.png" width="100%" />
</p>

### クイックスタート

uvのインストール

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### パッケージのインストール

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

#### 起動

`derisk-proxy-aliyun.toml`ファイルでAPI_KEYを設定し、次のコマンドを実行して起動します。

> 注意：デフォルトでは、OpenRCAデータセットのTelecomデータセットを使用します。リンクまたは以下のコマンドでダウンロードできます：

> gdown https://drive.google.com/uc?id=1cyOKpqyAP4fy-QiJ6a_cKuwR7D46zyVe

ダウンロード後、データセットを`pilot/datasets/`パスに移動します。

起動コマンドを実行：
```
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-aliyun.toml
```

#### ウェブサイトへのアクセス

ブラウザを開いて[`http://localhost:7777`](http://localhost:7777)にアクセス
<p align="left">
  <img src="./assets/index.jpg" width="100%" />
</p>

### 使用方法
* AI-SRE(OpenRCA)
  - 注意：OpenRCAデータセット[Bankデータセット](https://drive.usercontent.google.com/download?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R&export=download&confirm=t&uuid=42621058-41af-45bf-88a6-64c00bfd2f2e)を使用しています
  - 次のリンクでデータセットをダウンロードできます：
    ```
      gdown https://drive.google.com/uc?id=1enBrdPT3wLG94ITGbSOwUFg9fkLR-16R
    ```
  - データセットを`${derisk}/pilot/datasets`パスに配置します。
* フレームグラフアシスタント
  - ローカルアプリケーションサービスプロセスのフレームグラフ（Java/Python）をアシスタントにアップロードして分析と問い合わせを行います。
* DataExpert
  - メトリクス、ログ、トレース、または様々なExcelデータシートをアップロードして対話型分析を行います。

### 高速開発
* エージェント開発
    `derisk-ext.agent.agents`配下の実装ロジックを参照してください。
* ツール開発
    * ローカルツール
    * MCP
* その他の開発
    ドキュメント準備中...

* DeRisk-Skills 発達
  - [derisk-skills](https://github.com/derisk-ai/derisk_skills)

#### 実行結果
下図に示すように、複数のエージェントが協調して複雑な運用診断タスクを処理するシナリオを示しています。

<p align="left">
  <img src="./assets/scene_demo.png" width="100%" />
</p>

### ロードマップ
- [x] 0530 V0.1バージョン：ドメイン知識とMCPサービスに基づき、異常認識→自律的意思決定→適応的実行と問題解決を実現。
  - [x] 技術リスクのためのドメイン知識エンジン
  - [x] 異常認識→意思決定→実行のための大規模モデル駆動推論エンジン
  - [x] 自動トラブルシューティングと修正

- [x] 0830 V0.2バージョン
  - [x] 技術リスクのためのMCPサービスと管理
  - [x] 知識とMCPツールのカスタムバインディングサポート
  - [x] 3つ以上のDevOpsドメインMCPサービスのサポート

- [ ] 0930 V0.3バージョン
  - [ ] 本番環境との統合サポート
  - [ ] 本番環境デプロイメントの完全なソリューションを提供し、本番の問題診断をサポート。

- [ ] 1230 V0.4バージョン
  - [ ] エンドツーエンドAIOpsオンラインAgentic RL
  - [ ] エンドツーエンド評価機能

### いんよう
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

OpenDeRisk-AIコミュニティは、AIネイティブなリスクインテリジェンスシステムの構築に専念しています。🛡️ 私たちのコミュニティがより良いサービスを提供できることを願い、また皆様が私たちに参加してより良い未来を共に創造することを願っています。🤝

[![Star History Chart](https://api.star-history.com/svg?repos=derisk-ai/OpenDerisk&type=Date)](https://star-history.com/#derisk-ai/OpenDerisk)


### コミュニティグループ

DingDingのネットワーキンググループに参加して、他の開発者と経験を共有しましょう！

<div align="center" style="display: flex; gap: 20px;">
    <img src="assets/derisk-ai.jpg" alt="OpenDeRisk-AI 交流群" width="200" />
</div>