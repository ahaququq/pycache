"""Database logging handler for capturing application logs."""
from __future__ import annotations

import json
import logging
from typing import Optional

from .db import db


class DBLogHandler(logging.Handler):
    """Logging handler that stores log records in the database."""

    def __init__(self, level: int = logging.WARNING) -> None:
        super().__init__(level)
        self.module_filter = "pycache"

    def emit(self, record: logging.LogRecord) -> None:
        """Store the log record in the database."""
        try:
            # Get module name
            module = record.name
            if module.startswith("app."):
                module = module[4:]  # Remove "app." prefix
            elif module.startswith("routes."):
                module = module[7:]
            elif module.startswith("modules."):
                module = module[8:]

            # Extract extra details if available
            details = {}
            for key, value in record.__dict__.items():
                if key not in (
                    "name", "msg", "args", "levelname", "levelno", "pathname",
                    "filename", "module", "exc_info", "exc_text", "stack_info",
                    "lineno", "funcName", "created", "msecs", "relativeCreated",
                    "thread", "threadName", "processName", "process", "message",
                    "asctime"
                ):
                    details[key] = value

            # Format the message
            message = self.format(record) if self.formatter else record.getMessage()

            # Insert into database
            db.execute(
                """
                INSERT INTO log_entries (level, module, message, details)
                VALUES (?, ?, ?, ?)
                """,
                (
                    record.levelname,
                    module,
                    message,
                    json.dumps(details) if details else None,
                ),
            )
            db._conn().commit()
        except Exception:
            # Silently ignore logging errors to avoid infinite loops
            self.handleError(record)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records by module prefix."""
        return record.name.startswith("app") or record.name.startswith("routes") or record.name.startswith("modules") or record.name.startswith("download") or record.name.startswith("cache") or record.name.startswith("sources")