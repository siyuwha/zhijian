FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/python:3.12-slim

WORKDIR /app

# 设置环境变量：Python 输出无缓冲、不写 pyc、设置时区、设置 PYTHONPATH
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PYTHONPATH="/:/app"

# 建立软链接让 /backend 指向 /app，实现 backend.app 与 app 双向绝对兼容
RUN ln -s /app /backend 2>/dev/null || true

# 配置阿里云国内 apt 源加速下载
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true

# 安装系统级必要依赖（时区与基础工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

# 拷贝后端应用代码
COPY . .

# 确保存放 SQLite 数据库和日志的目录存在
RUN mkdir -p /app/data /app/logs

# 暴露 FastAPI 默认端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
