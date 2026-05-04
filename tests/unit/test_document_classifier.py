"""Document classifier tests."""

from __future__ import annotations

import pytest

from hawiya.extractors.document_classifier import (
    UnsupportedDocumentError,
    classify,
    detect_format,
)
from hawiya.extractors.types import DocumentType


def test_detects_jpeg() -> None:
    assert detect_format(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"


def test_detects_png() -> None:
    assert detect_format(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR") == "image/png"


def test_detects_pdf() -> None:
    assert detect_format(b"%PDF-1.7\n") == "application/pdf"


def test_detects_tiff_little_endian() -> None:
    assert detect_format(b"II*\x00\x08\x00") == "image/tiff"


def test_detects_tiff_big_endian() -> None:
    assert detect_format(b"MM\x00*\x00\x00") == "image/tiff"


def test_unknown_format_returns_none() -> None:
    assert detect_format(b"NOTAFILE") is None


def test_classify_passport_for_jpeg() -> None:
    assert classify(b"\xff\xd8\xff\xe0\x00\x10JFIF") is DocumentType.PASSPORT


def test_classify_passport_for_pdf() -> None:
    assert classify(b"%PDF-1.7\nfoo") is DocumentType.PASSPORT


def test_classify_rejects_empty() -> None:
    with pytest.raises(UnsupportedDocumentError):
        classify(b"")


def test_classify_rejects_unknown() -> None:
    with pytest.raises(UnsupportedDocumentError):
        classify(b"this is plain text, not an image")


def test_declared_content_type_does_not_override_bytes() -> None:
    # Even if the consumer claims image/jpeg, we trust the bytes.
    with pytest.raises(UnsupportedDocumentError):
        classify(b"hello world", declared_content_type="image/jpeg")
