#!/bin/bash
# ==============================================================================
# G1-Cognition MVP NAS 一键部署与环境验证脚本 (飞牛私有云 fnOS / Debian Linux)
# ==============================================================================

set -e

echo "================================================================="
echo "  [AI 认知复盘交易系统] NAS Docker 生产环境一键部署与验证"
echo "  生产发布版本: v0.8.5"
echo "================================================================="

# 1. 检查 Docker 与 Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ 错误: 未检测到 docker 命令，请在飞牛应用中心安装 Docker 并在 SSH 启用。"
    exit 1
fi

if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
    echo "❌ 错误: 未检测到 docker compose 支持。"
    exit 1
fi

COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

# 2. 确保持久化目录存在
echo "--> 检查数据持久化目录..."
mkdir -p ./data ./logs
chmod 777 ./data ./logs || true

# 3. 构建并启动容器
echo "--> 开始构建与拉起容器 (构建前端生产包与后端环境)..."
$COMPOSE_CMD down --remove-orphans || true
$COMPOSE_CMD build --no-cache
$COMPOSE_CMD up -d

# 4. 等待后端健康检查
echo "--> 等待后端服务健康检查通过..."
sleep 5
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/docs > /dev/null; then
        echo "✅ 后端 FastAPI 服务健康就绪 (http://127.0.0.1:8000)！"
        break
    fi
    echo "    等待后端就绪中... ($i/30)"
    sleep 2
done

# 5. 等待前端就绪
echo "--> 等待前端 Next.js 服务就绪..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:3000 > /dev/null; then
        echo "✅ 前端 Web 服务健康就绪 (http://127.0.0.1:3000)！"
        break
    fi
    echo "    等待前端就绪中... ($i/30)"
    sleep 2
done

echo "================================================================="
echo "🎉 部署完成！"
echo "   前端 Web 看板: http://<NAS_IP>:3000"
echo "   后端 API 文档: http://<NAS_IP>:8000/docs"
echo "================================================================="
