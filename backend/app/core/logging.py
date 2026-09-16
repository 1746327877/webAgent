"""统一日志配置：应用日志走 stdout，`docker logs <backend>` 直接可见。"""

import logging
import sys

from app.core.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MARKER = "_webagent_handler"


def configure_logging() -> None:
    """幂等地给 root logger 装一个带格式的 stdout handler。

    只配置 root；`uvicorn.*` 的 logger 让它向上传播，格式与业务日志保持一致。
    """
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in [h for h in root.handlers if getattr(h, _MARKER, False)]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    setattr(handler, _MARKER, True)
    root.addHandler(handler)

    # uvicorn 自带 handler 会绕过 root 格式；清掉并改为传播，保证输出一致
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # 第三方库把每个请求都打在 INFO，日志会很吵；只保留 warning 以上
    for name in ("httpx", "httpx2", "httpcore", "httpcore2", "mcp", "anyio"):
        logging.getLogger(name).setLevel(logging.WARNING)
