FROM node:20-slim AS frontend

WORKDIR /app/web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN npm run build


FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc default-libmysqlclient-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache ".[dev]"

COPY . .

# 复制前端构建产物
COPY --from=frontend /app/web/dist ./web/dist

RUN scrapling install --force 2>/dev/null || true
RUN mkdir -p /app/logs

EXPOSE 8088

CMD ["python", "-m", "openspider.main"]
