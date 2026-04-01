"""Utilities for locating and configuring the Tesseract executable."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_CONFIGURED = False
_AVAILABLE = False
_PATH: str | None = None
_ERROR: str | None = None
_TESSDATA_DIR: str | None = None


def _custom_tessdata_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "tessdata"


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []

    env_path = os.getenv("TESSERACT_CMD")
    if env_path:
        candidates.append(Path(env_path))

    which_path = shutil.which("tesseract")
    if which_path:
        candidates.append(Path(which_path))

    candidates.extend(
        [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        ]
    )
    return candidates


def configure_tesseract() -> tuple[bool, str | None, str | None]:
    """Configure pytesseract if available and return availability details."""
    global _CONFIGURED, _AVAILABLE, _PATH, _ERROR, _TESSDATA_DIR

    if _CONFIGURED:
        return _AVAILABLE, _PATH, _ERROR

    _CONFIGURED = True

    try:
        import pytesseract
    except ImportError:
        _AVAILABLE = False
        _ERROR = "pytesseract is not installed"
        return _AVAILABLE, _PATH, _ERROR

    custom_tessdata = _custom_tessdata_dir()
    custom_tessdata.mkdir(parents=True, exist_ok=True)
    os.environ["TESSDATA_PREFIX"] = str(custom_tessdata)
    _TESSDATA_DIR = str(custom_tessdata)

    last_error: str | None = None
    for candidate in _candidate_paths():
        if not candidate.exists():
            continue

        try:
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            pytesseract.get_tesseract_version()
            _AVAILABLE = True
            _PATH = str(candidate)
            _ERROR = None
            return _AVAILABLE, _PATH, _ERROR
        except Exception as exc:
            last_error = str(exc)

    try:
        pytesseract.get_tesseract_version()
        _AVAILABLE = True
        _PATH = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
        _ERROR = None
    except Exception as exc:
        _AVAILABLE = False
        _ERROR = last_error or str(exc)

    return _AVAILABLE, _PATH, _ERROR


def refresh_tesseract() -> tuple[bool, str | None, str | None]:
    """Re-run detection after a new install or PATH change."""
    global _CONFIGURED, _AVAILABLE, _PATH, _ERROR, _TESSDATA_DIR
    _CONFIGURED = False
    _AVAILABLE = False
    _PATH = None
    _ERROR = None
    _TESSDATA_DIR = None
    return configure_tesseract()


def get_tessdata_dir() -> str | None:
    if not _CONFIGURED:
        configure_tesseract()
    return _TESSDATA_DIR
