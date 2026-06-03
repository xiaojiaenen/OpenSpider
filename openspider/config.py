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

    # 日志
    log_level: str = "INFO"
    log_file: Path = Path("./logs/openspider.log")

    @property
    def database_url(self) -> str:
        """异步 MySQL 连接 URL"""
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        """同步 MySQL 连接 URL（用于 Alembic 迁移）"""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
