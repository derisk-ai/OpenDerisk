# 零配置快速启动指南

## 快速启动

### 方式一：使用 `derisk quickstart` 命令（推荐）

```bash
# 零配置启动（无需任何配置文件）
derisk quickstart

# 指定端口启动
derisk quickstart -p 8888

# 使用旧配置文件启动
derisk quickstart -c configs/my/dev.toml
```

启动后访问: http://localhost:7777

### 方式二：使用 `derisk start webserver` 命令

```bash
# 零配置启动
derisk start webserver

# 使用配置文件启动
derisk start webserver -c configs/my/dev.toml

# 后台启动
derisk start webserver -d
```

### 方式三：直接运行 Python 脚本

```bash
# 零配置启动
python -m derisk_app.derisk_server

# 使用配置文件启动
python -m derisk_app.derisk_server -c configs/derisk-minimal.toml
```

## 配置说明

### 零配置模式

零配置模式下，服务会使用默认配置启动：
- **服务端口**: 7777
- **数据库**: SQLite (pilot/meta_data/derisk.db)
- **向量存储**: Chroma (pilot/data)
- **语言**: 中文

启动后通过 Web UI 配置：
1. 访问 http://localhost:7777
2. 进入"系统配置"页面
3. 添加模型配置（LLM、Embedding、Reranker）
4. 配置其他功能

### 使用配置文件

旧的 TOML 配置文件仍然完全支持：

```bash
# 使用阿里云配置
derisk quickstart -c configs/derisk-proxy-aliyun.toml

# 使用 OpenAI 配置
derisk quickstart -c configs/derisk-proxy-openai.toml

# 使用自定义配置
derisk quickstart -c configs/my/dev.toml
```

### 配置优先级

1. **命令行参数**（最高优先级）
   - `-p/--port`: 服务端口
   - `-h/--host`: 服务主机

2. **TOML 配置文件**
   - 如果指定了 `-c` 参数，使用指定的 TOML 文件

3. **默认配置**（最低优先级）
   - 如果未指定配置文件，使用零配置模式

## 数据持久化

### 数据库存储

- **位置**: `pilot/meta_data/derisk.db`
- **内容**: 用户配置、模型配置、对话历史等
- **备份**: 直接复制该文件即可

### 向量数据存储

- **位置**: `pilot/data/`
- **内容**: 向量索引、文档片段等

### JSON 配置存储

- **位置**: `~/.derisk/derisk.json`
- **内容**: 应用配置（可通过 UI 修改）

## 停止服务

```bash
# 如果是前台运行
Ctrl+C

# 如果是后台运行
derisk stop webserver
```

## 常见问题

### 1. 端口被占用

```bash
# 使用其他端口
derisk quickstart -p 8888
```

### 2. 数据库迁移警告

首次启动时可能会看到数据库迁移警告，这是正常的。数据库会自动创建和迁移。

### 3. 如何配置模型

启动服务后：
1. 访问 http://localhost:7777
2. 进入"模型管理"页面
3. 添加你的模型配置（支持 OpenAI、阿里云、智谱等）
4. 配置会自动保存到数据库

### 4. 如何恢复默认配置

```bash
# 删除数据库（会清除所有配置）
rm pilot/meta_data/derisk.db

# 重新启动
derisk quickstart
```

## 开发模式

### 使用最小配置文件开发

```bash
# 创建最小配置文件
# configs/derisk-minimal.toml 已存在

# 使用最小配置启动
derisk quickstart -c configs/derisk-minimal.toml
```

### 查看帮助

```bash
derisk quickstart --help
derisk start webserver --help
derisk --help
```