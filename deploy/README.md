# OpenSpider Docker 部署指南

## 快速开始

### 1. 准备配置文件

```bash
cd deploy
cp .env.example .env
```

编辑 `.env` 文件，修改以下配置：
- `JWT_SECRET_KEY` — 生产环境必须替换为随机 64 字符字符串
- `MYSQL_PASSWORD` — 修改 MySQL 密码
- `DB_TYPE` — 选择 `sqlite` 或 `mysql`

### 2. 打包前端

```bash
cd web
npm install
npm run build
```

产物在 `web/dist/` 目录，Nginx 会自动挂载。

### 3. 启动服务

**使用 SQLite（默认，无需 MySQL）：**

```bash
cd deploy
# 确保 .env 中 DB_TYPE=sqlite
docker compose up -d openspider frontend
```

**使用 MySQL：**

```bash
cd deploy
# 确保 .env 中 DB_TYPE=mysql
docker compose up -d
```

### 4. 访问服务

- **前端**: http://localhost:10009
- **API 文档**: http://localhost:10010/docs
- **健康检查**: http://localhost:10010/health

## 端口说明

| 服务 | 容器端口 | 宿主机端口 | 说明 |
|------|----------|------------|------|
| 前端 Nginx | 10009 | 10009 | 静态文件 + 反向代理 |
| 后端 API | 8088 | 10010 | FastAPI 服务 |
| MySQL | 3306 | 3306 | 数据库（可选） |

## 目录结构

```
OpenSpider/
├── openspider/          # 后端源码（不包含爬虫）
├── spiders/             # 爬虫代码（独立目录，挂载到容器）
├── web/dist/            # 前端打包产物
├── deploy/              # Docker 部署配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf
│   ├── .env.example
│   └── .env
├── data/                # SQLite 数据库（运行时生成）
├── logs/                # 日志（运行时生成）
└── crawl_data/          # 爬虫数据（运行时生成）
```

## 内网部署

编辑 `.env`，指向内网镜像仓库和 PyPI 源：

```env
# 内网镜像仓库
BASE_IMAGE=harbor.internal.com/base/python:3.13-slim
NGINX_IMAGE=harbor.internal.com/base/nginx:alpine

# 内网 PyPI 源
PIP_INDEX_URL=http://pypi.internal.com/simple
PIP_TRUSTED_HOST=pypi.internal.com

# 数据库（宿主机 MySQL 或内网 MySQL）
MYSQL_HOST=192.168.1.100
```

其余步骤（打包前端 → `docker compose up -d --build`）不变。

## 常用命令

```bash
# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f openspider

# 停止服务
docker compose down

# 重新构建后端并启动
docker compose up -d --build openspider

# 前端更新后重启 Nginx
docker compose restart frontend

# 进入容器
docker exec -it openspider bash
```

## 配置说明

### 数据库配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `DB_TYPE` | 数据库类型 | `sqlite` |
| `SQLITE_PATH` | SQLite 文件路径 | `./data/openspider.db` |
| `MYSQL_HOST` | MySQL 主机 | `mysql` |
| `MYSQL_PORT` | MySQL 端口 | `3306` |
| `MYSQL_USER` | MySQL 用户 | `root` |
| `MYSQL_PASSWORD` | MySQL 密码 | `123456` |
| `MYSQL_DATABASE` | MySQL 数据库 | `openspider` |

### JWT 配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `JWT_SECRET_KEY` | JWT 密钥（必填） | - |
| `JWT_ALGORITHM` | JWT 算法 | `HS256` |
| `JWT_ACCESS_EXPIRE_MINUTES` | Access Token 过期时间 | `30` |
| `JWT_REFRESH_EXPIRE_DAYS` | Refresh Token 过期时间 | `7` |

## 前端更新流程

```bash
# 1. 拉取最新代码
git pull

# 2. 重新打包前端
cd web
npm install
npm run build

# 3. 重启 Nginx（自动加载新的 dist）
cd ../deploy
docker compose restart frontend
```

## 浏览器模式（Stealth）

使用 `use_stealth = True` 的爬虫需要 Chromium 浏览器。Docker 镜像已内置：

- Chromium 通过 `scrapling install --force` 安装
- Docker 容器内自动添加 `--no-sandbox` 参数（通过 `DOCKER_CONTAINER=1` 环境变量检测）
- 系统依赖（libnss3、libgbm1 等）已在 Dockerfile 中安装

**注意**：如果爬虫同时使用了 `real_chrome = True`，需要在容器内安装 Chrome，建议改用 CDP 远程连接：

```python
class MySpider(BaseSpider):
    use_stealth = True
    cdp_url = "ws://chrome-server:9222"  # 连接外部 Chrome
```

## 生产环境建议

1. **修改 JWT 密钥**: 使用随机 64 字符字符串
2. **修改 MySQL 密码**: 使用强密码
3. **限制端口访问**: 只暴露必要端口
4. **配置 HTTPS**: 生产环境必须使用 HTTPS
5. **定期备份**: 定期备份数据库和爬虫数据

## 故障排查

### 查看日志

```bash
# 查看所有日志
docker compose logs

# 查看 OpenSpider 日志
docker compose logs openspider

# 实时查看日志
docker compose logs -f openspider
```

### 进入容器调试

```bash
# 进入 OpenSpider 容器
docker exec -it openspider bash

# 查看进程
ps aux

# 查看网络
netstat -tlnp
```

### 重置数据

```bash
# 停止服务
docker compose down

# 删除数据卷
docker volume rm deploy_mysql_data

# 删除本地数据
rm -rf deploy/data/* deploy/logs/* deploy/crawl_data/*

# 重新启动
docker compose up -d
```
