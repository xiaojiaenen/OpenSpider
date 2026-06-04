"""全局配置"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """OpenSpider 全局配置，从环境变量或 .env 文件读取"""

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "openspider"

    # 服务
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 爬虫
    spiders_dir: Path = Path("./openspider/spiders")
    crawl_data_dir: Path = Path("./crawl_data")
    max_concurrent_spiders: int = 10

    # 前端
    frontend_dir: Path = Path("./web/dist")

    # 日志
    log_level: str = "INFO"
    log_file: Path = Path("./logs/openspider.log")

    # 认证
    jwt_secret_key: str = ""          # 必填，否则启动报错
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    @property
    def database_url(self) -> str:
        """异步数据库连接 URL（MySQL 或 SQLite）"""
        if self.mysql_host == "sqlite":
            return "sqlite+aiosqlite:///./openspider.db"
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        """同步数据库连接 URL（用于 Alembic 迁移）"""
        if self.mysql_host == "sqlite":
            return "sqlite:///./openspider.db"
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
