FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY pyproject.toml ./

# 安装 Python 依赖
RUN uv pip install --system --no-cache ".[dev]"

# 复制源码
COPY . .

# 安装浏览器依赖（Scrapling stealth 模式需要）
RUN scrapling install --force 2>/dev/null || true

# 创建日志目录
RUN mkdir -p /app/logs

EXPOSE 8088

CMD ["python", "-m", "openspider.main"]
