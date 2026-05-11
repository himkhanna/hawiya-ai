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
import contextlib
import io
import os
import tempfile
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
    """Production OCR adapter using PassportEye (Tesseract under the hood).

    **Known limitation on real-world passport scans.** PassportEye 2.2.2
    calls Tesseract with the default ``eng`` LSTM model plus a character
    whitelist (``A-Z 0-9 < >``). That works well on clean scanner output
    but mis-reads OCR-B glyphs on phone-camera shots:

    - ``<`` filler chars get read as ``K`` / ``X`` (LSTM bias)
    - ``I`` gets read as ``1`` in nationality codes
    - ``O`` ↔ ``0`` substitutions

    Three known mitigation paths, none of which are in Phase 1:

    1. A Tesseract-5-format ``mrz.traineddata`` (the bundled PassportEye
       file is Tesseract 3 era and 5's loader rejects it).
    2. Image preprocessing (deskew + contrast enhancement) before OCR.
    3. Switch to PaddleOCR for the MRZ region (Phase 2 visual zone work).

    For the pilot, the customer's Regula scanner gives clean MRZ output
    and avoids the issue end-to-end. Phone-camera shots are best-effort.
    """

    def __init__(self, *, extra_tesseract_args: str = "") -> None:
        self._extra = extra_tesseract_args

    async def read_mrz(self, payload: bytes, content_type: str) -> tuple[str, str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_sync, payload, content_type)

    def _read_sync(self, payload: bytes, _content_type: str) -> tuple[str, str]:
        try:
            from passporteye import read_mrz  # noqa: PLC0415
            from PIL import (  # noqa: PLC0415
                Image,
                ImageOps,
                UnidentifiedImageError,
            )
        except ImportError as e:
            raise OCRUnavailableError(
                "PassportEye is not installed. Install with `pip install hawiya-ai[ocr]` "
                "and ensure Tesseract is on PATH."
            ) from e

        # If the upload is a PDF (e.g. a scanned passport from an office
        # scanner), rasterise its first page to JPEG bytes before the
        # normal image pipeline. Passport scans are essentially always
        # single-page; multi-page PDF support is a Phase 2 follow-up.
        from hawiya.extractors.document_classifier import is_pdf  # noqa: PLC0415

        if is_pdf(payload):
            payload = self._rasterise_pdf(payload)

        # PassportEye 2.2.2's Loader needs a path-like input it can
        # sniff a format from (BytesIO and numpy arrays both fail). We
        # write to a short-lived temp file in all cases.
        #
        # For phone-camera shots we honour the EXIF orientation tag so
        # the MRZ isn't sideways. JPEG re-encoding for EVERY upload
        # introduces compression artefacts that visibly degrade OCR on
        # already-clean scanner output, so we only re-encode when EXIF
        # actually says to rotate — otherwise the original bytes go
        # straight to the temp file untouched.
        try:
            with Image.open(io.BytesIO(payload)) as pil_img:
                pil_img.load()
                exif = pil_img.getexif()
                orientation = exif.get(0x0112, 1)  # EXIF Orientation tag
                if orientation != 1:
                    oriented = ImageOps.exif_transpose(pil_img) or pil_img
                    rgb = (
                        oriented if oriented.mode == "RGB" else oriented.convert("RGB")
                    )
                    buf = io.BytesIO()
                    rgb.save(buf, format="JPEG", quality=95)
                    normalised = buf.getvalue()
                else:
                    normalised = payload
        except (UnidentifiedImageError, OSError) as e:
            raise NoMRZFoundError(
                f"could not decode image bytes (format unsupported or file corrupt): {e}"
            ) from e

        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 — closed below
            suffix=".jpg", delete=False
        )
        try:
            tmp.write(normalised)
            tmp.close()
            try:
                result = read_mrz(tmp.name, extra_cmdline_params=self._extra)
            except Exception as e:  # PassportEye wraps subprocess errors loosely.
                raise OCRUnavailableError(f"OCR backend failed: {e}") from e
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp.name)

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

        # Fix character-class OCR mistakes (e.g. nationality "1ND" -> "IND",
        # DOB "9001I2" -> "900112"). See mrz.repair_mrz_chars for scope.
        from hawiya.extractors.mrz import repair_mrz_chars  # noqa: PLC0415

        return repair_mrz_chars(line1, line2)

    @staticmethod
    def _rasterise_pdf(payload: bytes) -> bytes:
        """Render the first page of a PDF to JPEG bytes at 200 DPI.

        200 DPI gives the MRZ region enough resolution for Tesseract on
        most scanned passports. Multi-page PDFs only have their first
        page processed — passport scans are single-page in practice.
        """
        try:
            import fitz  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError as e:
            raise OCRUnavailableError(
                "PDF input requires pymupdf — install with "
                "`pip install hawiya-ai[ocr]`."
            ) from e

        try:
            with fitz.open(stream=payload, filetype="pdf") as doc:
                if doc.page_count == 0:
                    raise NoMRZFoundError("PDF has no pages")
                page = doc[0]
                pix = page.get_pixmap(dpi=200)
                return bytes(pix.tobytes("jpeg"))
        except NoMRZFoundError:
            raise
        except Exception as e:
            raise NoMRZFoundError(
                f"could not rasterise PDF (file may be encrypted or corrupt): {e}"
            ) from e
