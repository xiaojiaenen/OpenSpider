ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

WORKDIR /app

# 安装系统依赖（Playwright/Chromium 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc default-libmysqlclient-dev curl \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 \
    libasound2 libxcomposite1 libxrandr2 libxdamage1 libxfixes3 \
    libpango-1.0-0 libcairo2 libcups2 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=

ENV PIP_NO_INPUT=1 PIP_PROGRESS_BAR=off

COPY pyproject.toml ./
RUN pip install --no-cache-dir --progress-bar off -i ${PIP_INDEX_URL} hatchling && \
    pip install --no-cache-dir --progress-bar off -i ${PIP_INDEX_URL} --no-build-isolation .

COPY . .

RUN mkdir -p /app/logs /app/data

# 标记为 Docker 容器（Chromium 自动 --no-sandbox）
ENV DOCKER_CONTAINER=1

EXPOSE 8088

CMD ["python", "-m", "openspider.main"]
