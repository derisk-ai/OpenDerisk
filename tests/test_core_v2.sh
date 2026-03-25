#!/bin/bash
# Core_v2 Agent 完整测试脚本

set -e

cd "$(dirname "$0")"
ROOT_DIR=$(pwd)
CONFIG_FILE="$ROOT_DIR/configs/derisk-test.toml"

echo "=========================================="
echo "Core_v2 Agent 完整功能测试"
echo "=========================================="

# 1. 检查环境
echo ""
echo "[1/6] 检查环境..."
echo "Python: $(which python)"
echo "Version: $(python --version)"

# 2. 检查配置文件
echo ""
echo "[2/6] 检查配置文件..."
if [ -f "$CONFIG_FILE" ]; then
    echo "配置文件存在: $CONFIG_FILE"
else
    echo "错误: 配置文件不存在"
    exit 1
fi

# 3. 创建必要目录
echo ""
echo "[3/6] 创建必要目录..."
mkdir -p pilot/meta_data
mkdir -p logs

# 4. 启动服务
echo ""
echo "[4/6] 启动服务..."
echo "命令: python -m derisk_app.derisk_server -c $CONFIG_FILE"
echo ""
echo "服务启动中... (后台运行)"
echo "日志输出到: logs/server.log"

nohup python -m derisk_app.derisk_server -c "$CONFIG_FILE" > logs/server.log 2>&1 &
SERVER_PID=$!
echo "服务 PID: $SERVER_PID"

# 等待服务启动
echo ""
echo "等待服务启动 (20秒)..."
sleep 20

# 5. 检查服务状态
echo ""
echo "[5/6] 检查服务状态..."
if ps -p $SERVER_PID > /dev/null 2>&1; then
    echo "✓ 服务正在运行 (PID: $SERVER_PID)"
else
    echo "✗ 服务启动失败"
    echo "查看日志: tail -100 logs/server.log"
    exit 1
fi

# 检查端口
echo ""
echo "检查端口 8888..."
if lsof -i :8888 > /dev/null 2>&1; then
    echo "✓ 端口 8888 已监听"
else
    echo "✗ 端口 8888 未监听"
fi

# 6. 测试 API
echo ""
echo "[6/6] 测试 API..."
echo ""
echo "--- 测试 V1 API ---"
curl -s -X POST http://localhost:8888/api/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"user_input": "你好", "app_code": "test"}' 2>&1 | head -20

echo ""
echo ""
echo "--- 测试 V2 Session API ---"
SESSION_RESPONSE=$(curl -s -X POST http://localhost:8888/api/v2/session \
    -H "Content-Type: application/json" \
    -d '{"agent_name": "simple_chat"}')
echo "Session Response: $SESSION_RESPONSE"

echo ""
echo "--- 测试 V2 Status API ---"
curl -s http://localhost:8888/api/v2/status | python -m json.tool 2>/dev/null || echo "Status API 返回非 JSON"

echo ""
echo "=========================================="
echo "测试完成!"
echo "=========================================="
echo ""
echo "服务已启动，你可以:"
echo "1. 访问 http://localhost:8888 打开 Web UI"
echo "2. 访问 http://localhost:8888/doc 查看 API 文档"
echo "3. 查看日志: tail -f logs/server.log"
echo "4. 停止服务: kill $SERVER_PID"
echo ""
echo "保存此 PID 以便停止服务: $SERVER_PID"
echo $SERVER_PID > /tmp/derisk_server.pid