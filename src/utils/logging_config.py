import sys

from loguru import logger


def setup_logger(log_level: str = "INFO"):
    """Configure synchronous sinks for the single-worker CLI runtime."""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True,
        enqueue=False,
    )
    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        enqueue=False,
    )
    return logger
