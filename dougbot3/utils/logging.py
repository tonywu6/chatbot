import logging
import sys
from pathlib import Path

import loguru


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = loguru.logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe().f_back, 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru.logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


def configure_logging(
    log_file: str | Path | None = None,
    level: int | str = logging.INFO,
):
    def formatter(record: "loguru.Record") -> str:
        prefix = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS ZZ}</green>"
            " <bold><level>{level: <8}</level></bold>"
        )
        suffix = "<cyan>[{name}:{function}:{line}]</cyan>"
        if record["level"].no < logging.WARNING:
            return f"{prefix} {{message}} {suffix}\n"
        return f"{prefix} <level>{{message}}</level> {suffix}\n"

    loguru.logger.configure(
        handlers=[
            {
                "sink": log_file or sys.stderr,
                "level": level,
                "format": formatter,
            },
        ],
        levels=[
            {"name": "DEBUG", "color": "<magenta>"},
            {"name": "DEBUG", "color": "<magenta>"},
            {"name": "INFO", "color": "<blue>"},
            {"name": "SUCCESS", "color": "<bold><green>"},
            {"name": "WARNING", "color": "<yellow>"},
            {"name": "ERROR", "color": "<red>"},
            {"name": "CRITICAL", "color": "<bold><red>"},
        ],
    )
    logging.basicConfig(handlers=[InterceptHandler()], level=0)
