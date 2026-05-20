import logging
import logging.handlers
import os
from pathlib import Path

from .config import AppConfig


def setup_logging(cfg: AppConfig) -> logging.Logger:
    logger = logging.getLogger("memorygame")
    logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    log_dir = Path(cfg.log_path).parent
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            cfg.log_path,
            maxBytes=cfg.log_max_size_mb * 1024 * 1024,
            backupCount=cfg.log_backup_count,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except (OSError, PermissionError):
        pass

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger
