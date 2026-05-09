"""OCR adapter — image bytes → raw MRZ text lines.

Phase 1 implementation wraps PassportEye + Tesseract per CLAUDE.md §3.
The adapter is fronted by a Protocol so the rest of the pipeline can be
unit-tested with a mock without needing Tesseract installed.

Tesseract is a system binary, not a Python package. Installation:
- Linux:    apt-get install tesseract-ocr
- macOS:    brew install tesseract
- Windows:  https://github.com/UB-Mannheim/tesseract/wiki

PassportEye itself is an optional extra (``pip install hawiya-ai[ocr]``)
so dev environments without Tesseract can still install and run the
unit suite.
"""

from __future__ import annotations

import asyncio
import io
from typing import Protocol

TD3_LINE_COUNT = 2


class OCRUnavailableError(RuntimeError):
    """PassportEye / Tesseract isn't available in this environment."""


class NoMRZFoundError(RuntimeError):
    """OCR ran but couldn't locate an MRZ region in the image."""


class OCRAdapter(Protocol):
    """Anything that turns image bytes into a 2-line TD3 MRZ tuple."""

    async def read_mrz(
        self,
        payload: bytes,
        content_type: str,
    ) -> tuple[str, str]:
        """Return ``(line1, line2)``. Raises NoMRZFoundError on miss."""
        ...


class PassportEyeAdapter:
    """Production OCR adapter using PassportEye (Tesseract under the hood)."""

    def __init__(self, *, extra_tesseract_args: str = "") -> None:
        self._extra = extra_tesseract_args

    async def read_mrz(self, payload: bytes, content_type: str) -> tuple[str, str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_sync, payload, content_type)

    def _read_sync(self, payload: bytes, _content_type: str) -> tuple[str, str]:
        try:
            from passporteye import read_mrz  # noqa: PLC0415
        except ImportError as e:
            raise OCRUnavailableError(
                "PassportEye is not installed. Install with `pip install hawiya-ai[ocr]` "
                "and ensure Tesseract is on PATH."
            ) from e

        try:
            result = read_mrz(io.BytesIO(payload), extra_cmdline_params=self._extra)
        except Exception as e:  # PassportEye wraps subprocess errors loosely.
            raise OCRUnavailableError(f"OCR backend failed: {e}") from e

        if result is None:
            raise NoMRZFoundError("no MRZ region found in image")

        # PassportEye stows the raw 2-line OCR output on result.aux. The
        # MRZ object itself doesn't expose it as a top-level attribute.
        # Older releases shipped `.mrz_code`; we keep that as a fallback.
        aux = getattr(result, "aux", None) or {}
        raw = (
            aux.get("raw_text")
            or aux.get("text")
            or getattr(result, "mrz_code", None)
        )
        if not raw:
            raise NoMRZFoundError("OCR returned no MRZ text")

        lines = [line for line in raw.splitlines() if line.strip()]
        if len(lines) < TD3_LINE_COUNT:
            raise NoMRZFoundError(f"expected {TD3_LINE_COUNT} MRZ lines, got {len(lines)}")

        # PassportEye does its own length normalisation, but be defensive:
        # pad/trim each line to 44 chars so the parser can do its job.
        line1 = lines[0].ljust(44, "<")[:44]
        line2 = lines[1].ljust(44, "<")[:44]
        return line1, line2
