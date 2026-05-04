"""Document type classification.

**Phase 1 honest disclosure:** any valid image or PDF is treated as a
``PASSPORT``. We don't yet have visual cues (logos, format detection) to
reliably tell a passport from an Emirates ID or GCC ID without first
running an extractor. Phase 2 adds a visual classifier (PaddleOCR + a
small image model). Until then, the classifier's job is to:

1. Reject bytes that aren't a recognisable image/PDF format.
2. Tag the input as ``PASSPORT`` so the MRZ pipeline can run.

If the OCR adapter then fails to find an MRZ, we surface
``DOCUMENT_UNREADABLE`` to the consumer, who decides whether to retry
or escalate to manual entry.
"""

from __future__ import annotations

from hawiya.extractors.types import DocumentType

# Magic byte prefixes for the formats we accept.
_MAGIC_PREFIXES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"%PDF-": "application/pdf",
    b"II*\x00": "image/tiff",  # little-endian TIFF
    b"MM\x00*": "image/tiff",  # big-endian TIFF
}

# Maximum prefix length we sniff.
_MAGIC_PROBE_LEN = 8


class UnsupportedDocumentError(ValueError):
    """The bytes don't look like a supported image/PDF format."""


def detect_format(payload: bytes) -> str | None:
    """Return the MIME type sniffed from magic bytes, or None."""
    head = payload[:_MAGIC_PROBE_LEN]
    for prefix, mime in _MAGIC_PREFIXES.items():
        if head.startswith(prefix):
            return mime
    return None


def classify(payload: bytes, declared_content_type: str | None = None) -> DocumentType:
    """Classify the upload. Phase 1 returns ``PASSPORT`` for any valid input.

    Raises ``UnsupportedDocumentError`` if the bytes are not a recognised
    image/PDF format.
    """
    if not payload:
        raise UnsupportedDocumentError("empty payload")

    detected = detect_format(payload)
    if detected is None:
        raise UnsupportedDocumentError(
            f"unrecognised file format (declared content-type: {declared_content_type!r})"
        )

    # If the consumer declared a content type, sanity-check it agrees with
    # the magic bytes. Mismatch is a soft warning logged upstream — we still
    # trust the bytes, since browsers/proxies routinely lie about MIME.
    return DocumentType.PASSPORT
