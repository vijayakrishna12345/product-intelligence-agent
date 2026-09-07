"""Stdlib logging setup for pia."""

from __future__ import annotations

import logging
from typing import Final

_CONFIGURED: Final = "_pia_configured"


def configure_logging(level: str = "INFO") -> None:
    """Attach a single stream handler; safe to call more than once."""
    root = logging.getLogger("pia")
    if getattr(root, _CONFIGURED, False):
        root.setLevel(level.upper())
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S%z")
    )
    root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False
    setattr(root, _CONFIGURED, True)


def get_logger(name: str) -> logging.Logger:
    if not name.startswith("pia"):
        name = f"pia.{name}"
    return logging.getLogger(name)
