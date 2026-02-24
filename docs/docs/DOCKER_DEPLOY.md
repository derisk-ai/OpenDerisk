# OpenDerisk Docker 部署指南

本文档提供基于 Docker 和 Docker Compose 的完整部署方案，涵盖快速部署、生产环境配置、多 LLM 提供商切换、MySQL 数据库部署等场景。

## 目录

- [架构概览](#架构概览)
- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [配置详解](#配置详解)
- [部署场景](#部署场景)
- [数据持久化](#数据持久化)
- [生产环境部署](#生产环境部署)
- [运维操作](#运维操作)
- [故障排查](#故障排查)
- [FAQ](#faq)

---

## 架构概览

Docker 部署包含以下三个容器化服务：

```
                    ┌─────────────────────┐
                    │    用户浏览器         │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │   Frontend (nginx)   │
                    │   Port: 3000         │
                    │   Next.js 静态导出    │
                    └─────────┬───────────┘
                              │ /api/* 反向代理
                    ┌─────────▼───────────┐
                    │   Backend (FastAPI)   │
                    │   Port: 7777         │
                    │   Python + uvicorn    │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼──┐  ┌────────▼────┐  ┌───────▼───────┐
    │  SQLite /   │  │  ChromaDB   │  │  LLM API      │
    │  MySQL      │  │  (向量存储)  │  │  (OpenAI /    │
    │  (元数据)    │  │             │  │   DeepSeek /  │
    │             │  │             │  │   Claude 等)   │
    └─────────────┘  └─────────────┘  └───────────────┘
```

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `backend` | 自建 (Python 3.11 + uv) | 7777 | API 服务器，处理所有业务逻辑 |
| `frontend` | 自建 (Node.js 构建 + nginx) | 3000 | Web UI，静态文件 + API 反向代理 |
| `db` | mysql:8.0 (可选) | 3306 | MySQL 数据库，生产环境推荐 |

---

## 前置条件

### 必需软件

| 软件 | 最低版本 | 安装指引 |
|------|---------|---------|
| Docker | 24.0+ | [安装 Docker](https://docs.docker.com/get-docker/) |
| Docker Compose | v2.20+ | Docker Desktop 自带，或 [单独安装](https://docs.docker.com/compose/install/) |

### 硬件要求

| 场景 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 最低要求（使用云端 LLM API） | 2 核 | 4 GB | 20 GB |
| 推荐配置 | 4 核 | 8 GB | 50 GB |
| 含本地 LLM 推理 | 8+ 核 | 32+ GB | 100+ GB + GPU |

### API Key

至少需要一个 LLM 提供商的 API Key：

- **OpenAI**: https://platform.openai.com/api-keys
- **DeepSeek**: https://platform.deepseek.com/api_keys
- **Anthropic Claude**: https://console.anthropic.com/settings/keys
- **SiliconFlow**: https://cloud.siliconflow.cn/account/ak

---

## 快速开始

### 1. 克隆代码

```bash
git clone https://github.com/derisk-ai/OpenDerisk.git
cd OpenDerisk
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.template .env

# 编辑 .env 文件，填入你的 API Key
vi .env
```

最小配置只需修改一行：

```env
OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 3. 启动服务

```bash
# 构建并启动所有服务（后台运行）
docker compose up -d --build
```

### 4. 访问服务

- **Web UI**: http://localhost:3000
- **Backend API**: http://localhost:7777
- **API 文档**: http://localhost:7777/docs

### 5. 查看日志

```bash
# 查看所有服务日志
docker compose logs -f

# 只看后端日志
docker compose logs -f backend
```

### 6. 停止服务

```bash
docker compose down
```

---

## 配置详解

### 环境变量 (.env)

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `OPENAI_API_KEY` | - | 是* | OpenAI API 密钥 |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | 否 | OpenAI API 地址（可用于兼容接口） |
| `LLM_MODEL_NAME` | `gpt-4o` | 否 | LLM 模型名称 |
| `LLM_MODEL_PROVIDER` | `proxy/openai` | 否 | LLM 提供商标识 |
| `EMBEDDING_MODEL_NAME` | `text-embedding-3-small` | 否 | Embedding 模型名称 |
| `EMBEDDING_MODEL_PROVIDER` | `proxy/openai` | 否 | Embedding 提供商标识 |
| `EMBEDDING_MODEL_API_URL` | `https://api.openai.com/v1/embeddings` | 否 | Embedding API 地址 |
| `DERISK_LANG` | `en` | 否 | 界面语言：`en` 或 `zh` |
| `WEB_SERVER_PORT` | `7777` | 否 | 后端端口映射 |
| `DB_TYPE` | `sqlite` | 否 | 数据库类型：`sqlite` 或 `mysql` |
| `DERISK_CONFIG_FILE` | `configs/derisk-docker.toml` | 否 | 配置文件路径 |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:7777` | 否 | 前端构建时的 API 地址 |

> \* 使用其他 LLM 提供商时，设置对应的 API Key 即可。

### TOML 配置文件

后端通过 TOML 配置文件控制核心行为，位于 `configs/` 目录。Docker 部署默认使用 `configs/derisk-docker.toml`。

可用配置文件：

| 配置文件 | 说明 |
|----------|------|
| `derisk-docker.toml` | Docker 部署专用（推荐） |
| `derisk-proxy-openai.toml` | OpenAI 配置 |
| `derisk-proxy-deepseek.toml` | DeepSeek 配置 |
| `derisk-proxy-claude.toml` | Anthropic Claude 配置 |
| `derisk-proxy-gemini.toml` | Google Gemini 配置 |
| `derisk-proxy-kimi.toml` | Moonshot Kimi 配置 |
| `derisk-proxy-tongyi.toml` | 通义千问配置 |
| `derisk-proxy-ollama.toml` | Ollama 本地模型配置 |
| `derisk-siliconflow.toml` | SiliconFlow 配置 |

切换配置文件：

```bash
# 在 .env 中修改
DERISK_CONFIG_FILE=configs/derisk-proxy-deepseek.toml
```

---

## 部署场景

### 场景一：使用 OpenAI（默认）

```env
# .env
OPENAI_API_KEY=sk-your-key
LLM_MODEL_NAME=gpt-4o
```

```bash
docker compose up -d --build
```

### 场景二：使用 DeepSeek

```env
# .env
DEEPSEEK_API_KEY=sk-your-deepseek-key
OPENAI_API_KEY=${DEEPSEEK_API_KEY}
OPENAI_API_BASE=https://api.deepseek.com/v1
LLM_MODEL_NAME=deepseek-chat
LLM_MODEL_PROVIDER=proxy/openai
DERISK_CONFIG_FILE=configs/derisk-proxy-deepseek.toml
```

```bash
docker compose up -d --build
```

### 场景三：使用 Anthropic Claude

```env
# .env
ANTHROPIC_API_KEY=sk-ant-your-key
DERISK_CONFIG_FILE=configs/derisk-proxy-claude.toml
```

```bash
docker compose up -d --build
```

### 场景四：使用 MySQL 数据库

适用于生产环境或需要更强数据管理能力的场景：

```env
# .env
DB_TYPE=mysql
LOCAL_DB_HOST=db
LOCAL_DB_PORT=3306
LOCAL_DB_USER=root
LOCAL_DB_PASSWORD=your-secure-password
LOCAL_DB_NAME=derisk
MYSQL_ROOT_PASSWORD=your-secure-password
```

```bash
# 使用 --profile mysql 激活 MySQL 服务
docker compose --profile mysql up -d --build
```

### 场景五：仅部署后端（前端单独部署或不需要）

```bash
docker compose up -d backend
```

### 场景六：使用中文界面

```env
# .env
DERISK_LANG=zh
```

```bash
docker compose up -d --build
```

---

## 数据持久化

所有数据通过 Docker Named Volumes 持久化，即使容器被删除，数据也不会丢失。

| Volume 名称 | 容器挂载路径 | 说明 |
|-------------|-------------|------|
| `derisk-metadata` | `/app/pilot/meta_data` | SQLite 数据库、元数据 |
| `derisk-vectordata` | `/app/pilot/data` | ChromaDB 向量存储 |
| `derisk-messages` | `/app/pilot/message` | 对话消息数据 |
| `derisk-logs` | `/app/logs` | 应用日志 |
| `derisk-mysql-data` | `/var/lib/mysql` | MySQL 数据（仅 mysql profile） |

### 备份数据

```bash
# 备份所有数据卷
docker run --rm \
  -v derisk-metadata:/data/metadata \
  -v derisk-vectordata:/data/vectordata \
  -v derisk-messages:/data/messages \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/derisk-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### 恢复数据

```bash
# 先停止服务
docker compose down

# 恢复数据
docker run --rm \
  -v derisk-metadata:/data/metadata \
  -v derisk-vectordata:/data/vectordata \
  -v derisk-messages:/data/messages \
  -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/derisk-backup-20250224.tar.gz -C /data

# 重新启动
docker compose up -d
```

### 清除所有数据（谨慎操作）

```bash
docker compose down -v
```

---

## 生产环境部署

### 安全加固

1. **修改默认密码**：

```env
LOCAL_DB_PASSWORD=your-very-secure-password-here
MYSQL_ROOT_PASSWORD=your-very-secure-password-here
ENCRYPT_KEY=your-random-encryption-key
```

2. **限制端口暴露**：

在 `docker-compose.yml` 中，将端口绑定到 `127.0.0.1`：

```yaml
ports:
  - "127.0.0.1:7777:7777"  # 仅本地访问
```

3. **使用 HTTPS**：

在前端 nginx 前面部署反向代理（如 Traefik、Caddy 或额外的 nginx），配置 SSL 证书。

### 使用外部反向代理（Traefik 示例）

创建 `docker-compose.override.yml`：

```yaml
services:
  frontend:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.derisk.rule=Host(`derisk.yourdomain.com`)"
      - "traefik.http.routers.derisk.tls.certresolver=letsencrypt"
      - "traefik.http.services.derisk.loadbalancer.server.port=3000"
    ports: []  # 不直接暴露端口
    networks:
      - derisknet
      - traefik

  backend:
    ports: []  # 不直接暴露端口

networks:
  traefik:
    external: true
```

### 资源限制

在 `docker-compose.override.yml` 中添加资源限制：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

  frontend:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
```

### 日志管理

```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
```

---

## 运维操作

### 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看日志（实时跟踪）
docker compose logs -f backend
docker compose logs -f frontend

# 重启单个服务
docker compose restart backend

# 重新构建并启动（代码更新后）
docker compose up -d --build

# 仅重新构建后端
docker compose up -d --build backend

# 进入容器调试
docker compose exec backend /bin/bash
docker compose exec frontend /bin/sh

# 查看资源使用情况
docker compose top
docker stats
```

### 更新部署

```bash
# 拉取最新代码
git pull origin main

# 重新构建并启动
docker compose up -d --build

# 如果依赖有变化，清除构建缓存
docker compose build --no-cache
docker compose up -d
```

### 扩缩容

```bash
# 扩展后端为 3 个实例（需配合负载均衡）
docker compose up -d --scale backend=3
```

---

## 故障排查

### 常见问题

#### 1. 后端启动失败：`Module not found`

**原因**：`PYTHONPATH` 未正确设置。

**排查**：

```bash
docker compose exec backend env | grep PYTHONPATH
docker compose exec backend python -c "import derisk; print(derisk.__file__)"
```

#### 2. 前端无法连接后端 API

**原因**：`NEXT_PUBLIC_API_BASE_URL` 配置不正确，或后端尚未启动完成。

**排查**：

```bash
# 检查后端健康状态
curl http://localhost:7777/api/health

# 检查前端 nginx 日志
docker compose logs frontend

# 检查网络连通性
docker compose exec frontend wget -qO- http://backend:7777/api/health
```

#### 3. MySQL 连接失败

**原因**：MySQL 容器未启动或未使用 `--profile mysql`。

**排查**：

```bash
# 确认使用了 mysql profile
docker compose --profile mysql ps

# 检查 MySQL 日志
docker compose --profile mysql logs db

# 测试连接
docker compose exec db mysql -u root -p -e "SELECT 1"
```

#### 4. 构建过程中 `uv sync` 失败

**原因**：网络问题或依赖冲突。

**排查**：

```bash
# 清除 Docker 构建缓存后重试
docker builder prune
docker compose build --no-cache backend
```

#### 5. 磁盘空间不足

```bash
# 清理未使用的 Docker 资源
docker system prune -a --volumes

# 查看磁盘使用
docker system df
```

### 查看详细日志

```bash
# 后端完整日志
docker compose logs --tail=100 backend

# 带时间戳
docker compose logs -t backend

# 导出日志到文件
docker compose logs backend > backend.log 2>&1
```

---

## FAQ

### Q: 首次构建需要多长时间？

A: 取决于网络速度。首次构建大约需要 5-15 分钟（主要时间在安装 Python 依赖和前端 node_modules）。后续构建由于 Docker 层缓存，通常在 1-3 分钟内完成。

### Q: 可以只用后端不用前端吗？

A: 可以。直接启动后端即可：

```bash
docker compose up -d backend
```

后端自身也内嵌了静态 Web 文件（如果存在 `packages/derisk-app/src/derisk_app/static/web/`）。

### Q: 如何使用自定义 TOML 配置文件？

A: 将自定义配置文件放在 `configs/` 目录下，然后在 `.env` 中指定：

```env
DERISK_CONFIG_FILE=configs/my-custom-config.toml
```

### Q: 如何在 Docker 中使用 Ollama 本地模型？

A: 需要确保 Ollama 服务对 Docker 网络可达。使用 host 网络模式或指定 Ollama 的外部 IP：

```env
OPENAI_API_BASE=http://host.docker.internal:11434/v1
LLM_MODEL_NAME=qwen2.5:7b
LLM_MODEL_PROVIDER=proxy/openai
DERISK_CONFIG_FILE=configs/derisk-proxy-ollama.toml
```

在 `docker-compose.override.yml` 中添加：

```yaml
services:
  backend:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### Q: 如何升级到新版本？

A:

```bash
git pull origin main
docker compose up -d --build
```

数据卷中的数据会自动保留。

### Q: 支持 ARM 架构（Apple Silicon / ARM64）吗？

A: 支持。Docker 的多平台构建会自动处理。所有使用的基础镜像（`python:3.11-slim`、`node:20-alpine`、`nginx:1.27-alpine`、`mysql:8.0`）均支持 `linux/amd64` 和 `linux/arm64`。

---

## 文件结构

部署相关文件在项目中的位置：

```
OpenDerisk/
├── docker-compose.yml          # Docker Compose 编排文件
├── .env.template               # 环境变量模板
├── .dockerignore               # Docker 构建排除文件
├── configs/
│   ├── derisk-docker.toml      # Docker 专用配置
│   ├── derisk-proxy-openai.toml
│   ├── derisk-proxy-deepseek.toml
│   ├── derisk-proxy-claude.toml
│   └── ...
├── docker/
│   ├── Dockerfile.backend      # 后端镜像构建
│   ├── Dockerfile.frontend     # 前端镜像构建
│   ├── entrypoint.sh           # 后端启动脚本
│   └── nginx/
│       └── default.conf        # nginx 配置
└── assets/
    └── schema/
        └── derisk.sql          # MySQL 初始化 schema
```
