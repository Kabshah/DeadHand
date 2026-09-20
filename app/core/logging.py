"""app/core/logging.py — Structured logging setup.

Rules (§11):
- No print() anywhere in the codebase.
- Never log secret_message plaintext or raw OTP codes.
- Log switch_id, user_id, purpose — never secrets.
"""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a consistent format."""
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Use module __name__ as the name."""
    return logging.getLogger(name)
