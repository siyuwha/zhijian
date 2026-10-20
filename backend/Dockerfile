ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

WORKDIR /app

# 设置环境变量：Python 输出无缓冲、不写 pyc、设置时区、设置 PYTHONPATH
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PYTHONPATH="/:/app"

# 建立软链接让 /backend 指向 /app，实现 backend.app 与 app 双向绝对兼容
RUN ln -s /app /backend 2>/dev/null || true

# 替换国内镜像源加速 apt-get（兼容 Debian 12 debian.sources 与旧版 sources.list）
RUN (sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
     sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true)

# 安装系统级必要依赖（时区与基础工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（使用阿里云与清华高速镜像，解决 NAS 构建超时卡死）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 拷贝后端应用代码
COPY . .

# 确保存放 SQLite 数据库和日志的目录存在
RUN mkdir -p /app/data /app/logs

# 暴露 FastAPI 默认端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
