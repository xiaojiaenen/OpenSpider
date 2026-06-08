"""全局配置"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """OpenSpider 全局配置，从环境变量或 .env 文件读取"""

    # 数据库类型: sqlite 或 mysql
    db_type: str = "sqlite"

    # SQLite 配置
    sqlite_path: str = "./data/openspider.db"

    # MySQL 配置（db_type=mysql 时生效）
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "openspider"

    # 服务
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 爬虫
    spiders_dir: Path = Path("./spiders")
    crawl_data_dir: Path = Path("./crawl_data")
    max_concurrent_spiders: int = 10

    # 前端
    frontend_dir: Path = Path("./web/dist")

    # 日志
    log_level: str = "INFO"
    log_file: Path = Path("./logs/openspider.log")

    # 认证
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    # 沙箱
    sandbox_mode: str = "subprocess"   # "subprocess" | "docker" | "none"
    sandbox_docker_image: str = "openspider-runtime:latest"  # Docker 沙箱镜像
    sandbox_memory_mb: int = 512       # 内存限制 (MB)
    sandbox_cpu_seconds: int = 120     # CPU 时间限制 (秒)
    sandbox_timeout: int = 600         # 墙钟超时 (秒)

    @property
    def database_url(self) -> str:
        """异步数据库连接 URL"""
        if self.db_type == "sqlite":
            return f"sqlite+aiosqlite:///{self.sqlite_path}"
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        """同步数据库连接 URL（用于 Alembic 迁移）"""
        if self.db_type == "sqlite":
            return f"sqlite:///{self.sqlite_path}"
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()