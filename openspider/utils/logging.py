"""统一日志配置"""

from loguru import logger

from openspider.config import settings


def setup_logger():
    """配置 loguru 日志"""
    logger.remove()
    logger.add(
        "stderr",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    logger.add(
        str(settings.log_file),
        level=settings.log_level,
        rotation="10 MB",
        retention="7 days",
    )
