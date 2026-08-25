"""Directory-installable entry point for Hermes Agent."""

import sys
from pathlib import Path

_SOURCE_DIR = str(Path(__file__).resolve().parent / "src")
sys.path.insert(0, _SOURCE_DIR)
try:
    from profile_builder import register
finally:
    sys.path.remove(_SOURCE_DIR)

__all__ = ["register"]
