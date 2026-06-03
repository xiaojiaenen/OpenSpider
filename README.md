# OpenSpider

爬虫管理平台 — 管理多个爬虫的生命周期，暴露标准化 API 供外部 AI 集成。

## 功能

- **多爬虫管理**：注册、启停、暂停恢复、失败重试
- **热加载**：`spiders/` 目录新增文件自动注册
- **定时调度**：支持 cron 表达式定时触发
- **崩溃恢复**：平台重启后自动检测并恢复
- **断点续爬**：利用 Scrapling 的 crawldir 机制
- **数据导出**：JSON / JSONL / CSV
- **反爬绕过**：Cloudflare 破解、浏览器指纹控制、代理轮换
- **全站兼容**：支持 ASP/JSP/PHP 老旧站点，自动编码检测
- **AI 集成**：标准化 API + Skill 描述，外部 AI 可直接调用

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/xiaojiaenen/OpenSpider.git
cd OpenSpider

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -e ".[dev]"

# 下载浏览器依赖（用于 stealth 模式）
scrapling install --force
```

### 配置

复制并编辑配置文件：

```bash
# MySQL 连接信息
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=openspider
```

### 启动

```bash
# 启动 API 服务
openspider serve

# 或直接运行
python -m openspider.main
```

API 文档：http://localhost:8000/docs

### 写一个爬虫

在 `openspider/spiders/` 目录下创建 `.py` 文件：

```python
from openspider.spiders.base import BaseSpider

class MySpider(BaseSpider):
    name = "my_spider"
    description = "我的爬虫"
    start_urls = ["https://example.com"]

    async def run(self):
        page = await self.get(self.start_urls[0])
        for item in page.css(".article"):
            if self.should_stop:
                break
            yield {
                "title": item.css("h2::text").get(""),
                "link": item.css("a::attr(href)").get(""),
            }
```

文件保存后自动注册，通过 API 启动：

```bash
curl -X POST http://localhost:8000/spiders/my_spider/start
```

## CLI 命令

```bash
openspider serve                      # 启动平台
openspider list                       # 列出所有爬虫
openspider start <name>               # 启动爬虫
openspider stop <name>                # 停止爬虫
openspider info <name>                # 查看详情
openspider add <file.py>              # 注册新爬虫
openspider validate <file.py>         # 验证爬虫文件
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/capabilities` | 能力描述（给 AI 用） |
| GET | `/spiders` | 爬虫列表 |
| POST | `/spiders/{name}/start` | 启动爬虫 |
| POST | `/spiders/{name}/stop` | 停止爬虫 |
| GET | `/tasks` | 任务列表 |
| GET | `/items` | 数据查询 |
| GET | `/export/{name}` | 数据导出 |
| POST | `/spiders/upload` | 上传爬虫文件 |

## 项目结构

```
OpenSpider/
├── openspider/
│   ├── core/           # 核心引擎、注册表、调度器、恢复
│   ├── spiders/        # 爬虫基类、模板、示例
│   ├── api/            # FastAPI 路由
│   ├── models/         # 数据模型
│   ├── storage/        # 数据库连接
│   └── utils/          # 工具（编码、表单、URL、选择器）
├── skill/              # AI 集成 Skill 描述
├── docs/               # 设计文档
└── tests/              # 测试
```

## 技术栈

- **爬虫引擎**：Scrapling
- **API 框架**：FastAPI
- **任务调度**：APScheduler
- **数据库**：MySQL + SQLAlchemy
- **文件监控**：watchdog
- **编码检测**：charset-normalizer

## License

MIT
